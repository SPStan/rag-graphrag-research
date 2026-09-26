"""Export and verify a completed HippoRAG 2 run in local MLflow and Langfuse."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.track_dense import export_langfuse, export_mlflow

TRACE_NAME = "hipporag2-rag-run"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_payload(run_path, metrics_path=None, manifest_path=None):
    run_path = Path(run_path).resolve()
    metrics_path = Path(metrics_path).resolve() if metrics_path else run_path.with_suffix(".metrics.json")
    manifest_path = Path(manifest_path).resolve() if manifest_path else run_path.with_suffix(".manifest.json")
    rows = [json.loads(line) for line in run_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    metrics = read_json(metrics_path)
    manifest = read_json(manifest_path)
    if not rows:
        raise ValueError("HippoRAG JSONL is empty")
    run_id = rows[0].get("run_id")
    if (not run_id or metrics.get("run_id") != run_id or manifest.get("run_id") != run_id
            or any(row.get("run_id") != run_id for row in rows)):
        raise ValueError("JSONL, metrics and manifest must share one run_id")
    if manifest.get("status") != "completed":
        raise ValueError("Only completed runs can be exported")
    expected_hash = manifest.get("results_sha256")
    if not expected_hash or hashlib.sha256(run_path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError("HippoRAG JSONL does not match its manifest hash")
    expected_ids = manifest.get("expected_question_ids")
    actual_ids = [row.get("question_id") for row in rows]
    if not expected_ids or actual_ids != expected_ids:
        raise ValueError("JSONL questions do not exactly match the manifest's planned IDs")
    if any(not row.get("done") or row.get("done_reason") not in ("stop", "length")
           for row in rows):
        raise ValueError("Every exported question must have a completed generation")
    if metrics.get("questions_evaluated") != len(rows) or metrics.get("dataset") != rows[0].get("dataset"):
        raise ValueError("Metrics do not match the JSONL question count and dataset")
    if metrics.get("run_id") != run_id or manifest.get("dataset") != rows[0].get("dataset"):
        raise ValueError("Metrics or manifest dataset/run_id mismatch")
    manifest["generation"].setdefault("reader_prompt_version", rows[0]["reader_prompt_version"])
    questions = []
    for row in rows:
        docs = row.get("retrieved")
        if not docs or any(not doc.get("id") or not doc.get("text") for doc in docs):
            raise ValueError("Every question must include retrieved passage IDs and full text")
        questions.append({"row": row, "retrieved_passages": docs})
    return {
        "run_id": run_id, "rows": rows, "questions": questions,
        "metrics": metrics, "manifest": manifest,
        "dataset": rows[0]["dataset"], "system": "hipporag2",
        "trace_name": TRACE_NAME,
        "run_path": run_path, "metrics_path": metrics_path,
        "manifest_path": manifest_path,
    }


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="completed HippoRAG JSONL")
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = load_payload(args.run, args.metrics, args.manifest)
        import mlflow
        mlflow_result = export_mlflow(payload, mlflow)
        langfuse_result = export_langfuse(payload)
        print(json.dumps({"status": "verified", "run_id": payload["run_id"],
                          "mlflow": mlflow_result, "langfuse": langfuse_result},
                         ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"HippoRAG run export failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
