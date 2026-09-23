"""Export a completed local Dense RAG run and evaluation to MLflow and Langfuse."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
MLFLOW_URI = "http://127.0.0.1:5000"
EXPERIMENT_NAME = "rag-graphrag-research"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_payload(run_path, metrics_path, manifest_path, corpus_path):
    rows = [json.loads(line) for line in run_path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    metrics = read_json(metrics_path)
    manifest = read_json(manifest_path)
    if not rows:
        raise ValueError("Run JSONL is empty")
    run_id = rows[0].get("run_id")
    if (not run_id or metrics.get("run_id") != run_id or manifest.get("run_id") != run_id
            or any(row.get("run_id") != run_id for row in rows)):
        raise ValueError("JSONL, metrics and manifest must share one run_id")
    if manifest.get("status") != "completed":
        raise ValueError("Only completed runs can be exported")
    expected_results_hash = manifest.get("results_sha256")
    if expected_results_hash and hashlib.sha256(run_path.read_bytes()).hexdigest() != expected_results_hash:
        raise ValueError("Run JSONL does not match the results hash in its manifest")
    expected_corpus_hash = manifest.get("inputs", {}).get("corpus_sha256")
    if expected_corpus_hash and hashlib.sha256(corpus_path.read_bytes()).hexdigest() != expected_corpus_hash:
        raise ValueError("Corpus does not match the pinned hash in the run manifest")
    if metrics.get("questions_evaluated") not in (None, len(rows)):
        raise ValueError("Metrics question count does not match the JSONL")
    if metrics.get("dataset") not in (None, rows[0].get("dataset")):
        raise ValueError("Metrics dataset does not match the JSONL")
    corpus = read_json(corpus_path)
    passages = {passage["id"]: passage for passage in corpus}
    questions = []
    for row in rows:
        retrieved = []
        for result in row.get("retrieved", []):
            passage = passages.get(result["id"])
            if passage is None:
                raise ValueError(f"Retrieved passage is absent from corpus: {result['id']}")
            retrieved.append({**passage, "score": result.get("score")})
        questions.append({"row": row, "retrieved_passages": retrieved})
    return {"run_id": run_id, "rows": rows, "questions": questions,
            "metrics": metrics, "manifest": manifest,
            "dataset": rows[0].get("dataset")}


def export_mlflow(payload, mlflow):
    if not os.environ.get("MLFLOW_TRACKING_URI"):
        mlflow.set_tracking_uri(MLFLOW_URI)
    if not os.environ.get("MLFLOW_EXPERIMENT_ID"):
        mlflow.set_experiment(EXPERIMENT_NAME)

    manifest = payload["manifest"]
    run = payload["rows"]
    metrics = payload["metrics"]
    with mlflow.start_run(run_name=f"dense-{payload['dataset']}-{payload['run_id'][:8]}") as active:
        mlflow.set_tags({
            "project": "rag-graphrag",
            "purpose": "dense-rag-evaluation",
            "rag.run_id": payload["run_id"],
            "rag.dataset": payload["dataset"],
            "rag.mode": "local-poc",
            "rag.token_scope": "local_ollama_usage_not_billed_api_cost",
        })
        params = {
            "run_id": payload["run_id"],
            "dataset": payload["dataset"],
            "questions": str(metrics["questions_evaluated"]),
            "top_k": str(metrics["top_k"]),
            "embedding_model": manifest["embedding"]["model"]["name"],
            "embedding_digest": manifest["embedding"]["model"]["digest"],
            "generation_model": manifest["generation"]["model"]["name"],
            "generation_digest": manifest["generation"]["model"]["digest"],
            "reader_prompt_version": manifest["generation"]["reader_prompt_version"],
            "mode": "local-poc",
        }
        mlflow.log_params(params)
        mlflow.log_metrics({key: float(metrics[key]) for key in ("em", "token_f1", "recall_at_k")})

        # MLflow's trace is a retrospective run record; timings are the measured values
        # saved by the runner, not the duration of this export operation.
        with mlflow.start_span(name="dense-rag-run", span_type="CHAIN") as root_span:
            root_span.set_inputs({"run_id": payload["run_id"], "dataset": payload["dataset"],
                                  "questions": len(run)})
            root_span.set_attribute("rag.run_id", payload["run_id"])
            root_span.set_outputs({"metrics": {key: metrics[key] for key in
                                                ("em", "token_f1", "recall_at_k")}})
            for item in payload["questions"]:
                row = item["row"]
                with mlflow.start_span(name="question", span_type="CHAIN") as question_span:
                    question_span.set_inputs({"question_id": row["question_id"],
                                              "question": row["question"]})
                    with mlflow.start_span(name="query-embedding", span_type="EMBEDDING") as span:
                        span.set_inputs({"question": row["question"],
                                         "model": row["embedding_model"]["name"]})
                        span.set_outputs({"prompt_tokens": row.get("query_embedding_prompt_tokens"),
                                          "client_seconds": row.get("query_embedding_client_seconds")})
                    with mlflow.start_span(name="retrieval", span_type="RETRIEVER") as span:
                        span.set_inputs({"question": row["question"], "top_k": row["top_k"]})
                        span.set_outputs({"documents": item["retrieved_passages"]})
                    with mlflow.start_span(name="generation", span_type="LLM") as span:
                        span.set_inputs({"question": row["question"],
                                         "documents": item["retrieved_passages"],
                                         "model": row["generation_model"]["name"],
                                         "prompt_version": row["reader_prompt_version"]})
                        span.set_outputs({"answer": row.get("answer"),
                                          "raw_answer": row.get("raw_answer"),
                                          "done_reason": row.get("done_reason"),
                                          "prompt_tokens": row.get("prompt_tokens"),
                                          "completion_tokens": row.get("completion_tokens"),
                                          "client_seconds": row.get("generation_wall_seconds")})
                    question_span.set_outputs({"answer": row.get("answer"),
                                               "answer_extraction_status": row.get("answer_extraction_status")})

        mlflow.flush_trace_async_logging()
        for name in ("run_path", "metrics_path", "manifest_path"):
            mlflow.log_artifact(str(payload[name]), artifact_path="run-data")
        experiment_id = active.info.experiment_id
        mlflow_run_id = active.info.run_id

    traces = mlflow.search_traces(locations=[experiment_id], max_results=100)
    trace_ids = traces["trace_id"].tolist() if "trace_id" in traces else []
    matching = []
    for trace_id in trace_ids:
        trace = mlflow.get_trace(trace_id)
        span_names = [span.name for span in trace.data.spans]
        if "dense-rag-run" in span_names:
            matching.append({"trace_id": trace_id, "span_names": span_names})
    if not matching:
        raise RuntimeError("MLflow run was logged, but its trace was not found after flushing")
    return {"experiment_id": experiment_id, "mlflow_run_id": mlflow_run_id,
            "trace": matching[0]}


def export_langfuse(payload, base_dir=ROOT):
    from langfuse import Langfuse

    settings = dotenv_values(base_dir / ".env")
    required = ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    missing = [key for key in required if not settings.get(key)]
    if missing:
        raise ValueError("Missing local Langfuse settings: " + ", ".join(missing))
    base_url = settings["LANGFUSE_BASE_URL"].rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Dense run export is restricted to local Langfuse")
    client = Langfuse(public_key=settings["LANGFUSE_PUBLIC_KEY"],
                      secret_key=settings["LANGFUSE_SECRET_KEY"],
                      base_url=base_url, timeout=10)
    try:
        if not client.auth_check():
            raise RuntimeError("Langfuse authentication failed")
        with client.start_as_current_observation(
            as_type="chain", name="dense-rag-run",
            input={"run_id": payload["run_id"], "dataset": payload["dataset"],
                   "questions": len(payload["rows"])},
            metadata={"run_id": payload["run_id"], "mode": "local-poc",
                      "recording_mode": "posthoc_export"},
        ) as root:
            trace_id = client.get_current_trace_id()
            root.update(output={"metrics": {key: payload["metrics"][key] for key in
                                             ("em", "token_f1", "recall_at_k")}})
            for item in payload["questions"]:
                row = item["row"]
                with client.start_as_current_observation(
                    as_type="chain", name="question",
                    input={"question_id": row["question_id"], "question": row["question"]},
                    metadata={"run_id": payload["run_id"]},
                ) as question:
                    with client.start_as_current_observation(
                        as_type="embedding", name="query-embedding",
                        input={"question": row["question"]},
                        output={"prompt_tokens": row.get("query_embedding_prompt_tokens"),
                                "client_seconds": row.get("query_embedding_client_seconds")},
                        model=row["embedding_model"]["name"],
                    ):
                        pass
                    with client.start_as_current_observation(
                        as_type="retriever", name="retrieval",
                        input={"question": row["question"], "top_k": row["top_k"]},
                        output={"documents": item["retrieved_passages"]},
                    ):
                        pass
                    with client.start_as_current_observation(
                        as_type="generation", name="generation",
                        input={"question": row["question"],
                               "documents": item["retrieved_passages"],
                               "prompt_version": row["reader_prompt_version"]},
                        output={"answer": row.get("answer"), "raw_answer": row.get("raw_answer"),
                                "done_reason": row.get("done_reason"),
                                "client_wall_seconds": row.get("generation_wall_seconds"),
                                "ollama_total_seconds": row.get("generation_seconds")},
                        model=row["generation_model"]["name"],
                        usage_details={key: value for key, value in (
                            ("input", row.get("prompt_tokens")),
                            ("output", row.get("completion_tokens")),
                        ) if isinstance(value, int)},
                    ):
                        pass
                    question.update(output={"answer": row.get("answer"),
                                            "answer_extraction_status": row.get("answer_extraction_status")})
        client.flush()
        deadline = time.monotonic() + 45
        expected = {"dense-rag-run", "question", "query-embedding", "retrieval", "generation"}
        while time.monotonic() < deadline:
            observations = client.api.observations.get_many(trace_id=trace_id, limit=100)
            names = {observation.name for observation in observations.data}
            if expected.issubset(names):
                return {"trace_id": trace_id, "observation_names": sorted(names),
                        "trace_url": client.get_trace_url(trace_id=trace_id)}
            time.sleep(2)
        raise RuntimeError("Langfuse trace did not expose the expected observations within 45 seconds")
    finally:
        client.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="completed Dense RAG JSONL")
    parser.add_argument("--metrics", type=Path, help="metrics JSON; defaults next to run")
    parser.add_argument("--manifest", type=Path, help="manifest JSON; defaults next to run")
    args = parser.parse_args()
    run_path = args.run if args.run.is_absolute() else ROOT / args.run
    metrics_path = args.metrics or run_path.with_suffix(".metrics.json")
    manifest_path = args.manifest or run_path.with_suffix(".manifest.json")
    dataset = run_path.name.split("-")[1]
    corpus_path = ROOT / "data" / "processed" / dataset / "corpus.json"
    try:
        payload = prepare_payload(run_path, metrics_path, manifest_path, corpus_path)
        payload.update(run_path=run_path, metrics_path=metrics_path, manifest_path=manifest_path)
        import mlflow
        mlflow_result = export_mlflow(payload, mlflow)
        langfuse_result = export_langfuse(payload)
        print(json.dumps({"status": "verified", "run_id": payload["run_id"],
                          "mlflow": mlflow_result, "langfuse": langfuse_result}, indent=2))
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"Dense run export failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
