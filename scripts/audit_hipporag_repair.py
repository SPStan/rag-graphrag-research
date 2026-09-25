"""Read-only feasibility audit for repairing a failed HippoRAG index in a clone.

This script never contacts a model or mutates the source manifest/index. Its
optional JSON output contains only aggregate counts, artifact hashes and run IDs.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

try:
    from scripts.run_hipporag import canonical_key, sha256_bytes
except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
    from run_hipporag import canonical_key, sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ID = "e78eff08-532a-40b3-a359-49a6b08b32a7"
VALID = {"valid_empty", "valid_nonempty"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def expected_openie_vector_ids(state_docs):
    """Reproduce pinned HippoRAG entity/fact IDs without exposing source text."""
    entities, facts = set(), set()
    for document in state_docs:
        for triple in document["extracted_triples"]:
            if not isinstance(triple, list) or len(triple) != 3:
                raise ValueError("OpenIE state contains an invalid triple")
            normalized = tuple(" ".join(
                "".join(c if c.isalnum() or c.isspace() else " "
                        for c in value.casefold()).split()
            ) for value in triple)
            entities.update((normalized[0], normalized[2]))
            facts.add(normalized)
    entity_ids = {"entity-" + hashlib.md5(value.encode()).hexdigest()
                  for value in entities}
    fact_ids = {"fact-" + hashlib.md5(str(value).encode()).hexdigest()
                for value in facts}
    return entity_ids, fact_ids


def producer_identity(manifest):
    pipeline = {
        "endpoint": "/api/embed", "truncate": False,
        "text_preprocessing": "replace-newlines-with-space-v1",
        "vector_validation": "finite-nonzero-row-v1",
    }
    payload = {
        "generation": manifest["generation"]["model"]["digest"],
        "embedding": manifest["embedding"]["model"]["digest"],
        "embedding_pipeline": pipeline,
        "upstream": manifest["upstream"]["commit"],
    }
    return "ollama:" + sha256_bytes(
        (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        .encode("utf-8")
    )


def summarize_attempts(attempts):
    grouped = {}
    for item in attempts:
        key = (item.get("passage_id"), item.get("stage"))
        grouped.setdefault(key, []).append(item)
    latest = {}
    for (passage_id, stage), rows in grouped.items():
        rows.sort(key=lambda row: row.get("attempt", -1))
        latest[(passage_id, stage)] = rows[-1]

    unresolved = {
        stage: {pid: row for (pid, row_stage), row in latest.items()
                if row_stage == stage and row.get("status") not in VALID}
        for stage in ("openie_ner", "openie_triples")
    }
    ner_ids = set(unresolved["openie_ner"])
    triple_ids = set(unresolved["openie_triples"])
    overlap = ner_ids & triple_ids
    ner_retry_numbers = Counter(row.get("attempt")
                                for row in unresolved["openie_ner"].values())
    triple_retry_numbers = Counter(row.get("attempt")
                                   for row in unresolved["openie_triples"].values())
    dependent_triple_refreshes = len(ner_ids - triple_ids)
    return {
        "unresolved_by_stage": {stage: len(rows) for stage, rows in unresolved.items()},
        "unresolved_terminal_attempt_numbers": {
            "openie_ner": dict(sorted(ner_retry_numbers.items())),
            "openie_triples": dict(sorted(triple_retry_numbers.items())),
        },
        "passages_with_both_stages_unresolved": len(overlap),
        "ner_repairs_requiring_dependent_triple_refresh": dependent_triple_refreshes,
        "estimated_targeted_generation_calls_if_dependency_refresh_is_required":
            sum(map(len, unresolved.values())) + dependent_triple_refreshes,
        "recorded_attempts": len(attempts),
    }


def audit_run(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = read_json(manifest_path)
    run_id = manifest.get("run_id")
    if not run_id or not manifest_path.name.endswith(f"{run_id}.manifest.json"):
        raise ValueError("Manifest filename and run_id do not match")
    index = manifest.get("index") or {}
    if index.get("openie_acceptance_gate", {}).get("eligible") is not False:
        raise ValueError("Source run is not a failed OpenIE-gate run")

    storage_dir = Path(manifest["storage_dir"]).resolve()
    if not storage_dir.is_dir():
        raise ValueError("Source index storage directory is missing")
    states = list(storage_dir.rglob("openie_state.json"))
    if len(states) != 1:
        raise ValueError("Expected exactly one persisted OpenIE state")
    state_path = states[0]
    working_dir = state_path.parent
    artifact_paths = {
        "openie_state": state_path,
        "graph": working_dir / "graph.pickle",
        "chunk_metadata": working_dir / "chunk_metadata.json",
        "chunk_embeddings": working_dir / "chunk_embeddings" / "vdb_chunk.parquet",
        "entity_embeddings": working_dir / "entity_embeddings" / "vdb_entity.parquet",
        "fact_embeddings": working_dir / "fact_embeddings" / "vdb_fact.parquet",
        "index_manifest": working_dir / "index_manifest.json",
    }
    if any(not path.is_file() for path in artifact_paths.values()):
        raise ValueError("One or more persisted index artifacts are missing")

    state = read_json(state_path)
    expected_passages = index.get("openie_acceptance_gate", {}).get("expected_passages")
    if len(state.get("docs", [])) != expected_passages:
        raise ValueError("Persisted OpenIE state does not match expected passage count")
    attempts = index.get("openie_attempts")
    if not isinstance(attempts, list):
        raise ValueError("Manifest has no attempt ledger")
    import pyarrow.parquet as parquet
    from pyarrow.parquet import ParquetFile

    artifact_summary = {}
    for name, path in artifact_paths.items():
        item = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        if name.endswith("embeddings"):
            item["rows"] = ParquetFile(path).metadata.num_rows
        artifact_summary[name] = item
    row_counts = {name: artifact_summary[name]["rows"]
                  for name in ("chunk_embeddings", "entity_embeddings", "fact_embeddings")}
    if row_counts["chunk_embeddings"] != expected_passages:
        raise ValueError("Chunk vector count does not match expected passage count")

    index_manifest = read_json(artifact_paths["index_manifest"])
    current_ids = {
        name: set(parquet.read_table(path, columns=["hash_id"])
                  .column("hash_id").to_pylist())
        for name, path in (("chunk", artifact_paths["chunk_embeddings"]),
                           ("entity", artifact_paths["entity_embeddings"]),
                           ("fact", artifact_paths["fact_embeddings"]))
    }
    expected_entity_ids, expected_fact_ids = expected_openie_vector_ids(state["docs"])
    expected_chunk_ids = {document["idx"] for document in state["docs"]}
    index_identity_matches = (
        index_manifest.get("components", {}).get("explicit_identity")
        == producer_identity(manifest)
    )
    expected_embedding_label = manifest["embedding"]["model"]["name"].replace(
        ":", "_").replace("/", "_")
    embedding_identity_matches = (
        index_manifest.get("embedding", {}).get("model_name") == expected_embedding_label
        and index_manifest.get("embedding", {}).get("normalized") is True
    )
    openie_identity = index_manifest.get("openie", {}).get("identity", {})
    options = manifest["generation"]["options"]
    expected_generation_label = manifest["generation"]["model"]["name"].replace(
        ":", "_").replace("/", "_")
    openie_identity_matches = (
        openie_identity.get("model_name") == expected_generation_label
        and openie_identity.get("temperature") == options.get("temperature")
        and openie_identity.get("seed") == options.get("seed")
        and openie_identity.get("response_format") == {"type": "json_object"}
        and openie_identity.get("ner_max_tokens") == 512
        and openie_identity.get("triple_max_tokens") == 2048
        and openie_identity.get("prompt_schema") == "hipporag_openie_v1"
    )
    vector_match = {
        "chunk_ids_match_openie_state": current_ids["chunk"] == expected_chunk_ids,
        "entity_ids_match_openie_state": current_ids["entity"] == expected_entity_ids,
        "fact_ids_match_openie_state": current_ids["fact"] == expected_fact_ids,
    }
    corpus_path = Path(manifest["inputs"]["corpus_path"])
    corpus_hash_matches = (corpus_path.is_file()
                           and sha256_file(corpus_path) == manifest["inputs"]["corpus_sha256"])
    corpus = read_json(corpus_path) if corpus_hash_matches else []
    expected_passage_texts = {
        f"{title}\n{text}"
        for item in corpus
        for title, text in [canonical_key(item["title"], item["text"])]
    }
    source_passages_match = (
        len(expected_passage_texts) == len(state["docs"])
        and expected_passage_texts == {item["passage"] for item in state["docs"]}
    )
    compatible = (index_identity_matches and embedding_identity_matches
                  and openie_identity_matches and source_passages_match
                  and corpus_hash_matches and all(vector_match.values()))

    return {
        "schema_version": 1,
        "source_run_id": run_id,
        "source_status": manifest.get("status"),
        "index_eligible": False,
        "qa_started": bool(manifest.get("qa", {}).get("started"))
            if isinstance(manifest.get("qa"), dict) else False,
        "expected_passages": expected_passages,
        "persisted_openie_passages": len(state["docs"]),
        "persisted_graph_present": True,
        "existing_embedding_rows": row_counts,
        "reuse_compatibility": {
            "producer_identity_matches": index_identity_matches,
            "embedding_identity_matches": embedding_identity_matches,
            "openie_identity_matches": openie_identity_matches,
            "source_corpus_sha256_matches_manifest": corpus_hash_matches,
            "source_passages_match_openie_state": source_passages_match,
            **vector_match,
            "current_state_artifacts_consistent": compatible,
            "post_repair_graph_rebuild_ready": False,
            "embedding_ids_missing_or_stale": {
                "chunks": len(expected_chunk_ids ^ current_ids["chunk"]),
                "entities": len(expected_entity_ids ^ current_ids["entity"]),
                "facts": len(expected_fact_ids ^ current_ids["fact"]),
            },
        },
        "artifacts": artifact_summary,
        "repair_analysis": summarize_attempts(attempts),
        "reuse_assessment": {
            "full_passage_reembedding_appears_unnecessary": compatible,
            "requires_cloned_storage_namespace": True,
            "requires_openie_state_patch_and_graph_reconstruction": True,
            "requires_exact_post_repair_vector_id_filter": True,
            "audit_sent_model_calls": False,
            "repair_requires_targeted_model_calls": True,
            "repair_wall_time_estimate": None,
            "notes": [
                "Reuse is conditional on verifying exact producer, corpus, embedding and vector-store compatibility.",
                "Only newly introduced entity/fact strings should need new embeddings after targeted extraction repair.",
                "Corrected extractions can remove old entity/fact IDs. Filter cloned vector stores to the exact corrected OpenIE ID sets before graph construction; an unfiltered clone is not graph-ready.",
                "The source diagnostic index must remain immutable; perform repair in a verified copy.",
                "No QA run or benchmark is authorized by this audit."
            ]
        },
        "historical_build_wall_seconds": (manifest.get("index") or {}).get("build_seconds"),
        "interpretation": [
            "This is an artifact-readiness audit, not a repaired or eligible benchmark result.",
            "A corrected NER result requires refreshing its dependent triple extraction unless that triple is already being repaired.",
            "Attempt estimates exclude retries if targeted calls fail and therefore are not a guaranteed upper bound."
        ]
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results" / "summary" /
                                "hipporag-repair-readiness-candidate.json")
    args = parser.parse_args(argv)
    manifest_path = ROOT / "results" / "raw" / f"hipporag2-musique-{args.run_id}.manifest.json"
    report = audit_run(manifest_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({"status": "audited", "report": args.output.name,
                      "source_run_id": report["source_run_id"],
                      "existing_vectors": report["existing_embedding_rows"],
                      "targeted_calls_estimate": report["repair_analysis"][
                          "estimated_targeted_generation_calls_if_dependency_refresh_is_required"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
