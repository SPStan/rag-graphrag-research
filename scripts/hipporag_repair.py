"""Safe, side-effect-free primitives for planning HippoRAG index repair."""

from copy import deepcopy
import hashlib
import re
import shutil
from pathlib import Path
import uuid
import json


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


def openie_values_sha256(state):
    """Hash extraction values independent of pinned state serialization."""
    rows = [{key: doc[key] for key in ("idx", "passage", "extracted_entities",
                                       "extracted_triples")}
            for doc in state["docs"]]
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def plan_openie_repairs(expected_passage_ids, source_attempts):
    """Plan bounded extraction repairs without making model requests.

    Every passage/stage must already have an attributable attempt history.
    NER repairs are ordered before triples, and triples for a passage with an
    unresolved NER outcome are explicitly marked as dependency refreshes.
    """
    try:
        from scripts.openie_protocol import (
            OPENIE_STAGES, VALID_STATUSES, UNRESOLVED_STATUSES)
    except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
        from openie_protocol import OPENIE_STAGES, VALID_STATUSES, UNRESOLVED_STATUSES

    expected = list(expected_passage_ids)
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("Expected passage IDs must be non-empty and unique")
    expected_set = set(expected)
    grouped = {(pid, stage): [] for pid in expected
               for stage in OPENIE_STAGES}
    for row in source_attempts:
        pid, stage = row.get("passage_id"), row.get("stage")
        if (pid, stage) not in grouped:
            raise ValueError("Source attempt ledger contains an unexpected stage")
        grouped[(pid, stage)].append(row)

    latest = {}
    for key, rows in grouped.items():
        rows.sort(key=lambda item: item.get("attempt", -1))
        if not rows:
            raise ValueError("Cannot plan repair with a missing stage history")
        numbers = [item.get("attempt") for item in rows]
        if (any(not isinstance(number, int) or isinstance(number, bool)
                for number in numbers)
                or numbers != list(range(1, len(rows) + 1))
                or len(rows) > 3):
            raise ValueError("Source attempt history is not consecutive or exceeds limit")
        if any(item.get("source_provenance_complete") is not True for item in rows):
            raise ValueError("Cannot plan repair from incomplete attempt provenance")
        if any(item.get("status") not in VALID_STATUSES | UNRESOLVED_STATUSES
               for item in rows):
            raise ValueError("Source attempt history has an unknown status")
        latest[key] = rows[-1]

    unresolved_ner = {
        pid for pid in expected
        if latest[(pid, "openie_ner")].get("status") not in VALID_STATUSES
    }
    targets = []
    for stage in OPENIE_STAGES:
        for pid in expected:
            previous = latest[(pid, stage)]
            dependent_refresh = stage == "openie_triples" and pid in unresolved_ner
            if (previous.get("status") in VALID_STATUSES
                    and not dependent_refresh):
                continue
            attempt = previous["attempt"] + 1
            if attempt > 3:
                raise ValueError("A repair would exceed the three-attempt limit")
            if (dependent_refresh and previous.get("status") in VALID_STATUSES
                    and attempt > 2):
                raise ValueError(
                    "A dependency refresh after a valid second triple attempt is not authorized"
                )
            row = {
                "passage_id": pid,
                "stage": stage,
                "attempt": attempt,
                "retry_of_attempt": previous["attempt"],
                "remedial_retry": attempt == 3,
            }
            if dependent_refresh:
                row.update({
                    "operation": "dependency_refresh",
                    "dependency_stage": "openie_ner",
                    "dependency_attempt_pending": True,
                })
            targets.append(row)
    return {
        "targets": targets,
        "summary": {
            "expected_passages": len(expected_set),
            "planned_stage_outcomes": len(targets),
            "planned_by_stage": {
                stage: sum(row["stage"] == stage for row in targets)
                for stage in OPENIE_STAGES
            },
            "dependency_refreshes": sum(
                row.get("operation") == "dependency_refresh" for row in targets
            ),
            "remedial_attempts": sum(row["remedial_retry"] for row in targets),
            "model_requests_made": 0,
        },
    }


def expected_openie_vector_ids(state_docs):
    """Return pinned HippoRAG entity/fact IDs for an OpenIE state."""
    entities, facts = set(), set()
    for document in state_docs:
        for triple in document.get("extracted_triples", []):
            if not isinstance(triple, list) or len(triple) != 3:
                raise ValueError("OpenIE state contains an invalid triple")
            normalized = tuple(" ".join(
                "".join(char if char.isalnum() or char.isspace() else " "
                        for char in value.casefold()).split()
            ) for value in triple)
            entities.update((normalized[0], normalized[2]))
            facts.add(normalized)
    entity_ids = {"entity-" + hashlib.md5(value.encode("utf-8")).hexdigest()
                  for value in entities}
    fact_ids = {"fact-" + hashlib.md5(str(value).encode("utf-8")).hexdigest()
                for value in facts}
    return entity_ids, fact_ids


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


def reconcile_embedding_table(table, expected_ids, new_rows=None, *, id_column="hash_id"):
    """Filter stale vectors and append exactly the missing expected vector rows."""
    filtered, plan = filter_embedding_table_to_ids(
        table, expected_ids, id_column=id_column)
    missing_ids = set(expected_ids) - set(filtered.column(id_column).to_pylist())
    if missing_ids:
        if new_rows is None or new_rows.schema != table.schema:
            raise ValueError("New embedding rows with the exact store schema are required")
        additions = new_rows.column(id_column).to_pylist()
        if len(additions) != len(set(additions)) or set(additions) != missing_ids:
            raise ValueError("New embedding IDs must exactly match the missing ID set")
        import pyarrow as pa
        filtered = pa.concat_tables([filtered, new_rows])
    elif new_rows is not None and new_rows.num_rows:
        raise ValueError("Unexpected embedding rows were supplied")
    actual_ids = filtered.column(id_column).to_pylist()
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
        raise ValueError("Reconciled embedding IDs do not exactly match OpenIE state")
    import pyarrow.compute as pc
    order = pc.sort_indices(filtered, sort_keys=[(id_column, "ascending")])
    filtered = filtered.take(order)
    plan["added_rows"] = len(missing_ids)
    plan["complete"] = True
    return filtered, plan


def prepare_repair_clone(source_dir, destination_dir, expected_hashes, *,
                         source_run_id, source_compatibility,
                         source_attempts, repair_attempts, expected_passage_ids,
                         state_updates, passage_id_to_index,
                         checkpoint_rows,
                         new_entity_rows=None, new_fact_rows=None,
                         repair_protocol):
    """Build a verified repair clone from already completed, validated outputs.

    This function makes no model or embedding requests. It refuses incomplete
    gates or vector sets and publishes the destination only after all files in
    the fresh staging copy are consistent.
    """
    from scripts.openie_protocol import build_openie_acceptance_gate
    import pyarrow.parquet as parquet

    required_protocol = {
        "model_digest", "prompt_schema_version", "response_format",
        "temperature", "seed", "num_ctx", "ner_max_new_tokens",
        "triples_max_new_tokens",
    }
    if not isinstance(repair_protocol, dict) or not required_protocol <= set(repair_protocol):
        raise ValueError("Repair protocol must be complete and frozen")
    from scripts.hipporag_repair_journal import RepairJournal
    if not isinstance(checkpoint_rows, list) or len(checkpoint_rows) != len(repair_attempts):
        raise ValueError("Repair requires exact private checkpoint rows")
    for stored, attempt in zip(checkpoint_rows, repair_attempts):
        RepairJournal._validate_output(stored)
        if stored.get("attempt") != attempt:
            raise ValueError("Checkpoint attempt differs from repair ledger")
    checkpoint_updates = [
        {"passage_id": row["task"]["passage_id"],
         "stage": row["task"]["stage"], "status": row["attempt"]["status"],
         "values": row["values"]}
        for row in checkpoint_rows if row["values"] is not None
    ]
    if checkpoint_updates != state_updates:
        raise ValueError("State updates differ from checkpoint values")
    required_compatibility = {
        "producer_identity_matches", "embedding_identity_matches",
        "openie_identity_matches", "source_corpus_sha256_matches_manifest",
        "source_passages_match_openie_state", "chunk_ids_match_openie_state",
        "entity_ids_match_openie_state", "fact_ids_match_openie_state",
        "current_state_artifacts_consistent",
    }
    if (not isinstance(source_run_id, str) or not source_run_id
            or not isinstance(source_compatibility, dict)
            or any(source_compatibility.get(key) is not True
                   for key in required_compatibility)):
        raise ValueError("Source run and all read-only reuse checks must be verified")
    source = Path(source_dir).resolve(strict=True)
    destination = Path(destination_dir).resolve()
    if destination.exists() or destination == source or source in destination.parents:
        raise ValueError("Repair clone destination must be new and outside the source")

    original_state_path = source / REPAIR_ARTIFACTS["openie_state"]
    if sha256_file(original_state_path) != expected_hashes.get("openie_state"):
        raise ValueError("Source OpenIE state SHA-256 changed since read-only audit")
    original_state = json.loads(original_state_path.read_text(encoding="utf-8"))
    patched_state, state_summary = apply_openie_updates(
        original_state, passage_id_to_index, state_updates)
    merged_attempts = merge_attempt_ledgers(
        source_attempts, repair_attempts, expected_passage_ids)
    latest_repair_status = {}
    for row in repair_attempts:
        key = (row.get("passage_id"), row.get("stage"))
        old = latest_repair_status.get(key)
        if old is None or row.get("attempt", 0) > old.get("attempt", 0):
            latest_repair_status[key] = row
    expected_keys = {key: row.get("status")
                     for key, row in latest_repair_status.items()
                     if row.get("status") in {"valid_empty", "valid_nonempty"}}
    update_keys = {(row.get("passage_id"), row.get("stage")): row.get("status")
                   for row in state_updates}
    if expected_keys != update_keys:
        raise ValueError("Repair attempt ledger and state updates must match exactly")
    gate = build_openie_acceptance_gate(expected_passage_ids, merged_attempts)
    if not gate["eligible"]:
        raise ValueError("Repaired attempt ledger does not pass OpenIE gate")

    entity_ids, fact_ids = expected_openie_vector_ids(patched_state["docs"])
    chunk_ids = {document["idx"] for document in patched_state["docs"]}
    store_specs = (
        ("chunk_embeddings", chunk_ids, None),
        ("entity_embeddings", entity_ids, new_entity_rows),
        ("fact_embeddings", fact_ids, new_fact_rows),
    )
    prepared_tables, vector_plans = {}, {}
    for name, target_ids, new_rows in store_specs:
        source_path = source / REPAIR_ARTIFACTS[name]
        current_table = parquet.read_table(source_path)
        prepared_tables[name], vector_plans[name] = reconcile_embedding_table(
            current_table, target_ids, new_rows)

    # Keep a repair staging directory private until all updated files verify.
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.preparing-{uuid.uuid4().hex}")
    try:
        create_verified_index_copy(source, staging, expected_hashes)
        # The pinned constructor requires the unchanged config manifest to open
        # retained vectors. Only the diagnostic graph must be removed.
        (staging / REPAIR_ARTIFACTS["graph"]).unlink()
        state_bytes = (json.dumps(patched_state, ensure_ascii=False, indent=2) + "\n")\
            .encode("utf-8")
        (staging / REPAIR_ARTIFACTS["openie_state"]).write_bytes(state_bytes)
        for name, table in prepared_tables.items():
            parquet.write_table(table, staging / REPAIR_ARTIFACTS[name])
        provenance = {
            "status": "graph_pending",
            "source_run_id": source_run_id,
            "checkpoint_sha256": RepairJournal._output_sha(checkpoint_rows),
            "source_openie_state_sha256": expected_hashes["openie_state"],
            "source_index_manifest_sha256": expected_hashes["index_manifest"],
            "repaired_openie_state_sha256": hashlib.sha256(state_bytes).hexdigest(),
            "repaired_openie_values_sha256": openie_values_sha256(patched_state),
            "repair_protocol": repair_protocol,
            "gate": {key: gate[key] for key in
                     ("eligible", "expected_passages", "expected_stage_outcomes",
                      "recorded_attempts")},
            "updated_passage_stages": state_summary["updated_passage_stages"],
            "updated_by_stage": state_summary["updated_by_stage"],
            "vector_plans": vector_plans,
        }
        (staging / "repair_provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        staging.rename(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {"provenance": provenance, "merged_attempts": merged_attempts}


def finalize_repair_graph(destination_dir, source_hashes):
    """Publish graph readiness only after the pinned index path writes new files."""
    import pyarrow.parquet as parquet

    destination = Path(destination_dir).resolve(strict=True)
    provenance_path = destination / "repair_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if provenance.get("status") != "graph_pending" or provenance.get("gate", {}).get("eligible") is not True:
        raise ValueError("Repair graph is not pending or extraction gate failed")
    state_path = destination / REPAIR_ARTIFACTS["openie_state"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if openie_values_sha256(state) != provenance["repaired_openie_values_sha256"]:
        raise ValueError("Repaired OpenIE extraction values changed after clone")
    entity_ids, fact_ids = expected_openie_vector_ids(state["docs"])
    for name, expected in (("chunk_embeddings", {row["idx"] for row in state["docs"]}),
                           ("entity_embeddings", entity_ids), ("fact_embeddings", fact_ids)):
        actual = parquet.read_table(destination / REPAIR_ARTIFACTS[name]).column("hash_id").to_pylist()
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError(f"Repaired {name} IDs differ from OpenIE state")
    new_hashes = {}
    for name in ("graph", "index_manifest"):
        path = destination / REPAIR_ARTIFACTS[name]
        if not path.is_file():
            raise ValueError(f"Pinned index has not written {name}")
        new_hashes[name] = sha256_file(path)
        if name == "graph" and new_hashes[name] == source_hashes[name]:
            raise ValueError(f"Diagnostic {name} cannot be accepted as repaired")
    if new_hashes["index_manifest"] != source_hashes["index_manifest"]:
        raise ValueError("Pinned index configuration manifest changed")
    provenance["status"] = "graph_ready"
    provenance["graph_sha256"] = new_hashes["graph"]
    provenance["index_manifest_sha256"] = new_hashes["index_manifest"]
    temporary = provenance_path.with_suffix(".json.part")
    temporary.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    temporary.replace(provenance_path)
    return provenance
