"""Safe, side-effect-free primitives for planning HippoRAG index repair."""

from copy import deepcopy
import hashlib
import re
import shutil
from pathlib import Path
import uuid


REPAIR_ARTIFACTS = {
    "openie_state": "openie_state.json",
    "graph": "graph.pickle",
    "chunk_metadata": "chunk_metadata.json",
    "index_manifest": "index_manifest.json",
    "chunk_embeddings": "chunk_embeddings/vdb_chunk.parquet",
    "entity_embeddings": "entity_embeddings/vdb_entity.parquet",
    "fact_embeddings": "fact_embeddings/vdb_fact.parquet",
}


def create_verified_index_copy(source_dir, destination_dir, expected_hashes):
    """Copy only known index artifacts after checking their expected hashes.

    The destination must not exist. The source is never modified; files are
    copied to a fresh staging directory and renamed into place after rehashing.
    """
    source = Path(source_dir).resolve(strict=True)
    destination = Path(destination_dir).resolve()
    if not source.is_dir() or destination.exists():
        raise ValueError("Source must be a directory and destination must be new")
    if destination == source or source in destination.parents:
        raise ValueError("Destination cannot be the source or inside it")
    if set(expected_hashes) != set(REPAIR_ARTIFACTS):
        raise ValueError("Expected hashes must name every required repair artifact")

    paths = {name: source / relative for name, relative in REPAIR_ARTIFACTS.items()}
    for name, path in paths.items():
        expected = expected_hashes[name]
        if not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
            raise ValueError(f"Invalid expected SHA-256 for {name}")
        cursor = source
        has_symlink_component = False
        for part in Path(REPAIR_ARTIFACTS[name]).parts:
            cursor = cursor / part
            has_symlink_component |= cursor.is_symlink()
        if (has_symlink_component or not path.is_file()
                or sha256_file(path) != expected):
            raise ValueError(f"Source artifact failed SHA-256 verification: {name}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.staging-{uuid.uuid4().hex}")
    try:
        staging.mkdir()
        for name, relative in REPAIR_ARTIFACTS.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(paths[name], target)
            if sha256_file(target) != expected_hashes[name]:
                raise ValueError(f"Copied artifact failed SHA-256 verification: {name}")
        staging.rename(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {name: REPAIR_ARTIFACTS[name] for name in REPAIR_ARTIFACTS}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def merge_attempt_ledgers(source_attempts, repair_attempts, expected_passage_ids):
    """Append attributable consecutive repair attempts without rewriting history."""
    merged = deepcopy(source_attempts)
    by_stage_passage = {}
    expected = set(expected_passage_ids)
    for row in merged:
        pid, stage, number = (row.get("passage_id"), row.get("stage"), row.get("attempt"))
        if (pid not in expected or stage not in ("openie_ner", "openie_triples")
                or not isinstance(number, int) or isinstance(number, bool)):
            raise ValueError("Source ledger contains an invalid passage, stage, or attempt")
        key = (row.get("passage_id"), row.get("stage"))
        by_stage_passage.setdefault(key, []).append(row)
    for rows in by_stage_passage.values():
        rows.sort(key=lambda row: row.get("attempt", -1))
        numbers = [row["attempt"] for row in rows]
        if len(rows) > 3 or numbers != list(range(1, len(rows) + 1)):
            raise ValueError("Source ledger has a duplicate or incomplete attempt sequence")

    additions = sorted(repair_attempts, key=lambda row: (
        row.get("passage_id", ""), row.get("stage", ""), row.get("attempt", -1)))
    seen_keys = {(row.get("passage_id"), row.get("stage"), row.get("attempt"))
                 for row in merged}
    for row in additions:
        pid, stage, number = (row.get("passage_id"), row.get("stage"), row.get("attempt"))
        if pid not in expected or stage not in ("openie_ner", "openie_triples"):
            raise ValueError("Repair attempt has an unexpected passage or stage")
        if not isinstance(number, int) or isinstance(number, bool) or not 2 <= number <= 3:
            raise ValueError("Repair attempt number must be 2 or 3")
        key = (pid, stage, number)
        if key in seen_keys:
            raise ValueError("Repair attempt duplicates an existing ledger key")
        previous = by_stage_passage.get((pid, stage), [])
        expected_number = (previous[-1]["attempt"] + 1) if previous else 1
        if number != expected_number:
            raise ValueError("Repair attempts must continue the existing attempt sequence")
        if not previous or row.get("retry_of_attempt") != previous[-1]["attempt"]:
            raise ValueError("Repair attempt must link to the immediately preceding attempt")
        if row.get("source_provenance_complete") is not True:
            raise ValueError("Repair attempt must have complete source provenance")
        if number == 3 and row.get("remedial_retry") is not True:
            raise ValueError("Attempt 3 must be explicitly marked remedial")
        copied = deepcopy(row)
        merged.append(copied)
        by_stage_passage.setdefault((pid, stage), []).append(copied)
        seen_keys.add(key)
    return merged


def apply_openie_updates(state, passage_id_to_index, updates):
    """Apply validated extraction outputs to a deep copy of OpenIE state."""
    repaired = deepcopy(state)
    docs = repaired.get("docs") if isinstance(repaired, dict) else None
    if not isinstance(docs, list):
        raise ValueError("OpenIE state must contain a docs list")
    docs_by_index = {row.get("idx"): row for row in docs
                     if isinstance(row, dict) and row.get("idx") is not None}
    if len(docs_by_index) != len(docs):
        raise ValueError("OpenIE state contains missing or duplicate document indices")
    if len(set(passage_id_to_index.values())) != len(passage_id_to_index):
        raise ValueError("Passage mapping points multiple IDs to the same OpenIE document")
    updated = set()
    updated_by_stage = {"openie_ner": 0, "openie_triples": 0}
    for item in updates:
        pid, stage = item.get("passage_id"), item.get("stage")
        key = (pid, stage)
        if key in updated:
            raise ValueError("OpenIE repair payload contains a duplicate passage/stage")
        index = passage_id_to_index.get(pid)
        if index not in docs_by_index:
            raise ValueError("OpenIE repair payload references an unknown passage")
        values = item.get("values")
        if not isinstance(values, list):
            raise ValueError("OpenIE repair output must be a validated list")
        expected_status = "valid_empty" if not values else "valid_nonempty"
        if item.get("status") != expected_status:
            raise ValueError("Only complete, valid extraction attempts can patch OpenIE state")
        if stage == "openie_ner":
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError("Repaired entities must be non-empty strings")
            field = "extracted_entities"
        elif stage == "openie_triples":
            if any(not isinstance(value, (list, tuple)) or len(value) != 3
                   or any(not isinstance(part, str) or not part.strip()
                          for part in value) for value in values):
                raise ValueError("Repaired triples must contain three non-empty strings")
            values = [list(value) for value in values]
            field = "extracted_triples"
        else:
            raise ValueError("OpenIE repair payload has an unknown extraction stage")
        docs_by_index[index][field] = values
        updated.add(key)
        updated_by_stage[stage] += 1
    return repaired, {
        "updated_passage_stages": len(updated),
        "updated_by_stage": updated_by_stage,
    }


def filter_embedding_table_to_ids(table, expected_ids, *, id_column="hash_id"):
    """Keep reusable vector rows and report vectors that must be added/removed.

    This function does not write files, embed text, or touch an index. Missing
    rows are reported so a caller cannot mistake the filtered partial table for
    a complete vector store.
    """
    if id_column not in table.column_names:
        raise ValueError(f"Embedding table is missing {id_column!r}")
    current = table.column(id_column).to_pylist()
    if len(current) != len(set(current)):
        raise ValueError("Embedding table contains duplicate vector IDs")
    expected = set(expected_ids)
    present = set(current)
    retained_ids = present & expected
    obsolete_ids = present - expected
    missing_ids = expected - present
    mask = [value in expected for value in current]
    filtered = table.filter(mask)
    return filtered, {
        "source_rows": len(current),
        "target_rows": len(expected),
        "retained_rows": len(retained_ids),
        "obsolete_rows": len(obsolete_ids),
        "missing_rows": len(missing_ids),
        "complete": not obsolete_ids and not missing_ids,
    }
