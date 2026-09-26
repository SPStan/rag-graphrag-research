"""Run the pinned reader on contexts saved by a completed cosine Dense RAG run."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import sys
import time
import uuid

import numpy as np
import requests

try:
    from scripts.run_dense import (GENERATION_OPTIONS, OLLAMA_URL, PROMPT_SOURCE,
                                   PROMPT_SOURCE_COMMIT, PROMPT_SOURCE_PATH,
                                   READER_PROMPT_VERSION, ROOT, build_reader_messages,
                                   reader_template_sha256,
                                   git_snapshot, model_info, post_json,
                                   require_completed_generation, sha256_file,
                                   write_json_atomic)
    from scripts.track_dense import prepare_payload
    from scripts.answer_parser import extract_reader_answer
except ModuleNotFoundError:  # Direct execution puts the scripts directory on sys.path.
    from run_dense import (GENERATION_OPTIONS, OLLAMA_URL, PROMPT_SOURCE,
                           PROMPT_SOURCE_COMMIT, PROMPT_SOURCE_PATH,
                           READER_PROMPT_VERSION, ROOT, build_reader_messages,
                           reader_template_sha256,
                           git_snapshot, model_info, post_json,
                           require_completed_generation, sha256_file,
                           write_json_atomic)
    from track_dense import prepare_payload
    from answer_parser import extract_reader_answer


def validate_replay_source(payload):
    """Require a complete, compatible source run and preserve its exact top-k order."""
    manifest = payload["manifest"]
    if manifest.get("status") != "completed":
        raise ValueError("Context source manifest must be completed")
    if payload.get("dataset") != "musique":
        raise ValueError("The pinned HippoRAG one-shot reader is validated only for MuSiQue")
    retrieval = manifest.get("retrieval", {})
    if retrieval.get("method") != "cosine":
        raise ValueError("Context source must be an original cosine Dense RAG run")
    generation = manifest.get("generation", {})
    source_prompt_version = generation.get("reader_prompt_version")
    if not isinstance(source_prompt_version, str) or not source_prompt_version:
        raise ValueError("Context source must declare its reader prompt version")
    if generation.get("options") != GENERATION_OPTIONS:
        raise ValueError("Context source must use the fixed generation options")

    expected_ids = manifest.get("expected_question_ids")
    rows = payload["rows"]
    if not isinstance(expected_ids, list) or not expected_ids:
        raise ValueError("Context source must contain ordered expected question IDs")
    if [row.get("question_id") for row in rows] != expected_ids:
        raise ValueError("Context source rows must exactly match ordered expected IDs")
    if any(row.get("planned_question_ids") != expected_ids for row in rows):
        raise ValueError("Context source rows disagree with manifest expected question IDs")
    top_k = retrieval.get("top_k")
    if not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("Context source must have a positive top_k")

    embedding_models = {json.dumps(row.get("embedding_model"), sort_keys=True)
                        for row in rows}
    if len(embedding_models) != 1:
        raise ValueError("Context source contains mixed embedding models")
    for item in payload["questions"]:
        row = item["row"]
        if row.get("reader_prompt_version") != source_prompt_version:
            raise ValueError("Context source rows disagree with the manifest reader prompt")
        if row.get("generation_options") != GENERATION_OPTIONS:
            raise ValueError("Context source rows contain different generation options")
        if row.get("top_k") != top_k or len(row.get("retrieved", [])) != top_k:
            raise ValueError("Each context source row must contain the full ordered top_k")
        if len(item["retrieved_passages"]) != top_k:
            raise ValueError("Could not reconstruct every retrieved passage from the corpus")
        for saved, passage in zip(row["retrieved"], item["retrieved_passages"]):
            if saved.get("id") != passage.get("id"):
                raise ValueError("Reconstructed contexts do not preserve saved retrieval order")
            score = saved.get("score")
            if not isinstance(score, (int, float)) or not np.isfinite(score):
                raise ValueError("Saved retrieval scores must be finite numbers")
    return top_k


def run(source_path, generation_model="qwen2.5:7b"):
    source_path = source_path if source_path.is_absolute() else ROOT / source_path
    source_metrics = source_path.with_suffix(".metrics.json")
    source_manifest_path = source_path.with_suffix(".manifest.json")
    corpus_path = ROOT / "data" / "processed" / "musique" / "corpus.json"
    source = prepare_payload(source_path, source_metrics, source_manifest_path, corpus_path)
    top_k = validate_replay_source(source)
    source_manifest = source["manifest"]
    source_run_id = source["run_id"]
    source_results_sha = source_manifest["results_sha256"]
    if not isinstance(source_results_sha, str) or len(source_results_sha) != 64:
        raise ValueError("Context source manifest must contain a SHA256 for its JSONL")
    source_manifest_sha = sha256_file(source_manifest_path)
    queries_path = ROOT / "data" / "processed" / "musique" / "queries.json"
    if sha256_file(queries_path) != source_manifest["inputs"]["queries_sha256"]:
        raise ValueError("Queries do not match the context source manifest")
    queries = {query["id"]: query["question"] for query in json.loads(
        queries_path.read_text(encoding="utf-8"))}
    if any(queries.get(row["question_id"]) != row["question"] for row in source["rows"]):
        raise ValueError("Context source questions do not match the pinned query data")
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    output_dir = ROOT / "results" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"dense-musique-reader-replay-{run_id}.jsonl"
    temporary = output_path.with_suffix(".jsonl.part")
    manifest_path = output_path.with_suffix(".manifest.json")
    source_index = source_manifest.get("index_embedding", {})
    source_embedding = source_manifest["embedding"]
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "starting",
        "mode": "local-poc-reader-replay",
        "dataset": source["dataset"],
        "started_at": started_at,
        "expected_question_ids": source_manifest["expected_question_ids"],
        "inputs": {
            "queries_sha256": source_manifest["inputs"]["queries_sha256"],
            "corpus_sha256": source_manifest["inputs"]["corpus_sha256"],
            "corpus_fingerprint": source_manifest["inputs"]["corpus_fingerprint"],
            "context_source_run_id": source_run_id,
            "context_source_results_sha256": source_results_sha,
            "context_source_manifest_sha256": source_manifest_sha,
        },
        "code": git_snapshot(),
        "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                    "numpy": np.__version__, "requests": requests.__version__},
        "embedding": source_embedding,
        "index_embedding": {
            "reused_from_run_id": source_run_id,
            "build_seconds_this_run": None,
            "cache_read_seconds": None,
            "cache_build_provenance": source_index.get("cache_build_provenance"),
            "note": "Reader replay reuses saved contexts; no embedding or index read was performed.",
        },
        "retrieval": {"method": "cosine_replay", "top_k": top_k,
                      "context_source_run_id": source_run_id,
                      "context_source_results_sha256": source_results_sha},
        "generation": {
            "requested_model": generation_model,
            "options": GENERATION_OPTIONS,
            "reader_prompt_version": READER_PROMPT_VERSION,
            "reader_prompt_source": PROMPT_SOURCE,
            "reader_prompt_source_commit": PROMPT_SOURCE_COMMIT,
            "reader_prompt_source_path": PROMPT_SOURCE_PATH,
            "reader_template_sha256": reader_template_sha256(),
        },
        "results_file": output_path.name,
    }
    write_json_atomic(manifest_path, manifest)
    session = requests.Session()
    try:
        version = session.get(f"{OLLAMA_URL}/api/version", timeout=30)
        version.raise_for_status()
        generation_info = model_info(session, generation_model)
        manifest["ollama_version"] = version.json().get("version")
        manifest["generation"]["model"] = generation_info
        manifest["status"] = "running"
        write_json_atomic(manifest_path, manifest)
        print(f"Replay source run: {source_run_id}; questions: {len(source['rows'])}; top-k: {top_k}")
        print(f"Generator: {generation_info['name']} ({generation_info['digest']}); "
              f"prompt: {READER_PROMPT_VERSION}")

        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            for position, item in enumerate(source["questions"], start=1):
                row = item["row"]
                started = time.perf_counter()
                messages = build_reader_messages(row["question"], item["retrieved_passages"])
                message_hash = hashlib.sha256(
                    json.dumps(messages, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                generation_started = time.perf_counter()
                response = post_json(session, "/api/chat", {
                    "model": generation_model, "messages": messages, "stream": False,
                    "options": GENERATION_OPTIONS,
                })
                generation_wall = time.perf_counter() - generation_started
                raw_answer = response.get("message", {}).get("content", "")
                answer, answer_status = extract_reader_answer(raw_answer)
                replay_row = {
                    "schema_version": 1, "run_id": run_id, "started_at": started_at,
                    "mode": "local-poc-reader-replay", "dataset": source["dataset"],
                    "question_id": row["question_id"],
                    "planned_question_ids": source_manifest["expected_question_ids"],
                    "question": row["question"],
                    "embedding_model": row["embedding_model"],
                    "generation_model": generation_info,
                    "reader_prompt_version": READER_PROMPT_VERSION,
                    "generation_options": GENERATION_OPTIONS,
                    "reader_prompt_source": PROMPT_SOURCE,
                    "reader_prompt_source_commit": PROMPT_SOURCE_COMMIT,
                    "reader_prompt_sha256": message_hash,
                    "context_source_run_id": source_run_id,
                    "context_source_results_sha256": source_results_sha,
                    "top_k": top_k,
                    "retrieved": row["retrieved"],
                    "answer": answer, "answer_extraction_status": answer_status,
                    "raw_answer": raw_answer,
                    "prompt_tokens": response.get("prompt_eval_count"),
                    "completion_tokens": response.get("eval_count"),
                    "query_embedding_prompt_tokens": None,
                    "query_embedding_client_seconds": None,
                    "retrieval_seconds": None,
                    "generation_wall_seconds": generation_wall,
                    "question_end_to_end_seconds": time.perf_counter() - started,
                    "generation_total_duration_ns": response.get("total_duration"),
                    "generation_load_duration_ns": response.get("load_duration"),
                    "generation_eval_duration_ns": response.get("eval_duration"),
                    "generation_seconds": (response["total_duration"] / 1_000_000_000
                                           if response.get("total_duration") is not None else None),
                    "generation_tokens_per_second": (
                        response["eval_count"] * 1_000_000_000 / response["eval_duration"]
                        if response.get("eval_count") and response.get("eval_duration") else None
                    ),
                    "done_reason": response.get("done_reason"),
                    "done": response.get("done"),
                }
                output.write(json.dumps(replay_row, ensure_ascii=False) + "\n")
                output.flush()
                require_completed_generation(response, row["question_id"])
                print(f"[{position}/{len(source['rows'])}] {row['question_id']}: {answer}")
        temporary.replace(output_path)
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["results_sha256"] = sha256_file(output_path)
        write_json_atomic(manifest_path, manifest)
        return output_path
    except (OSError, ValueError, KeyError, RuntimeError, requests.RequestException) as exc:
        manifest["status"] = "failed"
        manifest["failed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["error"] = {"type": type(exc).__name__, "message": str(exc),
                              "partial_results_file": temporary.name}
        write_json_atomic(manifest_path, manifest)
        raise
    finally:
        session.close()


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="completed Dense RAG JSONL with saved retrievals")
    parser.add_argument("--generation-model", default="qwen2.5:7b")
    args = parser.parse_args()
    try:
        output = run(args.source, args.generation_model)
        print(f"Replay results: {output.relative_to(ROOT)}")
        print(f"Manifest: {output.with_suffix('.manifest.json').relative_to(ROOT)}")
    except (OSError, ValueError, KeyError, RuntimeError, requests.RequestException) as exc:
        print(f"Reader replay failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
