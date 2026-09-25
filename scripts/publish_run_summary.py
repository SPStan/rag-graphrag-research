"""Create a safe public summary from ignored local run artifacts."""

import argparse
import hashlib
import json
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def result_question_ids(path):
    """Return result IDs in their recorded order without retaining raw rows."""
    identifiers = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Result JSONL is invalid at line {line_number}") from error
        question_id = row.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise ValueError(f"Result JSONL has no non-empty question_id at line {line_number}")
        identifiers.append(question_id)
    return identifiers


def validate_configuration(manifest, metrics):
    """Reject artifacts that cannot identify a comparable RAG configuration."""
    run_kind = manifest.get("mode") or manifest.get("runner")
    retrieval_method = manifest.get("retrieval", {}).get("method") or manifest.get("runner")
    required_manifest_fields = (
        ("dataset", manifest.get("dataset")),
        ("mode or runner", run_kind),
        ("generation.model", manifest.get("generation", {}).get("model")),
        ("retrieval.method or runner", retrieval_method),
        ("retrieval.top_k", manifest.get("retrieval", {}).get("top_k")),
    )
    missing = [name for name, value in required_manifest_fields if value is None or value == ""]
    if missing:
        raise ValueError("Manifest lacks comparable configuration: " + ", ".join(missing))
    if metrics.get("dataset") != manifest["dataset"]:
        raise ValueError("Manifest and metrics must share the dataset")
    if metrics.get("top_k") != manifest["retrieval"]["top_k"]:
        raise ValueError("Manifest and metrics must share retrieval.top_k")


def public_summary(run_path, metrics_path, manifest_path, limitations):
    run_path, metrics_path, manifest_path = map(Path, (run_path, metrics_path, manifest_path))
    manifest = read_json(manifest_path)
    metrics = read_json(metrics_path)
    run_hash = sha256_file(run_path)
    run_id = manifest.get("run_id")
    if not run_id or metrics.get("run_id") != run_id:
        raise ValueError("Manifest and metrics must share a non-empty run_id")
    if manifest.get("status") != "completed":
        raise ValueError("Only completed runs may be published")
    if manifest.get("results_sha256") != run_hash:
        raise ValueError("Run JSONL does not match manifest results_sha256")
    expected_ids = manifest.get("expected_question_ids")
    if not isinstance(expected_ids, list) or not expected_ids or any(not isinstance(item, str) or not item for item in expected_ids):
        raise ValueError("Manifest must have non-empty expected_question_ids")
    if result_question_ids(run_path) != expected_ids:
        raise ValueError("Run JSONL question_id sequence does not match manifest")
    validate_configuration(manifest, metrics)
    run_kind = manifest.get("mode") or manifest.get("runner")
    retrieval_method = manifest.get("retrieval", {}).get("method") or manifest.get("runner")
    return {
        "schema_version": 1,
        "kind": "local_rag_run_public_summary",
        "run": {
            "run_id": run_id,
            "dataset": manifest.get("dataset"),
            "mode": run_kind,
            "status": manifest.get("status"),
            "results_sha256": run_hash,
            "manifest_sha256": sha256_file(manifest_path),
            "metrics_sha256": sha256_file(metrics_path),
            "expected_questions": len(manifest.get("expected_question_ids", [])),
        },
        "inputs": {
            key: manifest.get("inputs", {}).get(key)
            for key in ("queries_sha256", "corpus_sha256", "corpus_fingerprint", "labels_sha256")
            if manifest.get("inputs", {}).get(key)
        },
        "source": manifest.get("source") or manifest.get("code"),
        "models": {
            "generation": manifest.get("generation", {}).get("model"),
            "embedding": manifest.get("embedding", {}).get("model"),
        },
        "configuration": {
            "reader_prompt_version": manifest.get("generation", {}).get("reader_prompt_version"),
            "reader_template_sha256": manifest.get("generation", {}).get("reader_template_sha256"),
            "generation_options": manifest.get("generation", {}).get("options"),
            "top_k": manifest.get("retrieval", {}).get("top_k"),
            "retrieval_method": retrieval_method,
        },
        "metrics": {
            key: metrics.get(key)
            for key in ("metric_version", "questions_evaluated", "top_k", "em", "token_f1", "recall_at_k", "generation_stopped_normally", "usage")
        },
        "limitations": limitations,
        "privacy": "No raw answers, prompts, passages, local paths, secrets or tracker URLs are included.",
    }


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limitation", action="append", default=[])
    args = parser.parse_args(argv)
    write_json(args.output, public_summary(args.run, args.metrics, args.manifest, args.limitation))


if __name__ == "__main__":
    main()
