"""Resume only a hash-bound Dense run interrupted after writing complete rows."""

import hashlib
import json
from pathlib import Path
import time
from datetime import datetime, timezone

import requests

from scripts.evaluation_view import load_view, select_in_view
from scripts.run_dense import (
    BATCH_SIZE, EMBED_CACHE_SCHEMA_VERSION, EMBED_MODEL, EMBED_TEXT_VERSION,
    EMBED_TRUNCATE, GENERATION_OPTIONS, OLLAMA_URL, PROMPT_SOURCE,
    PROMPT_SOURCE_COMMIT, PROMPT_SOURCE_PATH, READER_PROMPT_VERSION, ROOT,
    build_reader_messages, corpus_fingerprint, embed_corpus, extract_reader_answer,
    model_info, post_json, read_json, require_completed_generation,
    safe_print, sha256_file, top_k, validate_processed_data, write_json_atomic,
)


def validate_resume_prefix(rows, expected_ids, run_id):
    ids = [row.get("question_id") for row in rows]
    if ids != expected_ids[:len(rows)]:
        raise ValueError("Partial JSONL is not an ordered prefix of the frozen view")
    if len(set(ids)) != len(ids):
        raise ValueError("Partial JSONL contains duplicate question IDs")
    for row in rows:
        if (row.get("run_id") != run_id
                or row.get("planned_question_ids") != expected_ids
                or row.get("done") is not True
                or not row.get("done_reason")):
            raise ValueError("Partial row does not match the failed run or is incomplete")
    return len(rows)


def _read_jsonl(path):
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid partial result on line {line_number}") from exc
    return rows


def resume(manifest_path):
    manifest_path = Path(manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    output_dir = ROOT / "results" / "raw"
    manifest_path = manifest_path.resolve()
    if manifest_path.parent != output_dir.resolve():
        raise ValueError("Resume manifest must be directly under results/raw")
    manifest = read_json(manifest_path)
    if manifest.get("status") != "failed" or manifest.get("error", {}).get("type") != "UnicodeEncodeError":
        raise ValueError("Only the recorded Windows console Unicode interruption can be resumed")

    dataset = manifest.get("dataset")
    data_dir = ROOT / "data" / "processed" / dataset
    queries_path, corpus_path = data_dir / "queries.json", data_dir / "corpus.json"
    labels_path = data_dir / "labels.json"
    queries, corpus = read_json(queries_path), read_json(corpus_path)
    provenance = validate_processed_data(dataset, data_dir, queries, corpus, labels_path)
    inputs = manifest.get("inputs", {})
    if (inputs.get("queries_sha256") != sha256_file(queries_path)
            or inputs.get("corpus_sha256") != sha256_file(corpus_path)
            or inputs.get("output_sha256") != provenance.get("output_sha256")
            or inputs.get("corpus_fingerprint") != corpus_fingerprint(corpus)):
        raise ValueError("Pinned run inputs changed since the interruption")

    view_path = ROOT / "data" / "ids" / "musique_independent100_candidate.json"
    view_info = load_view(view_path, dataset, labels_path)
    recorded_view = manifest.get("evaluation_view") or {}
    for key in ("name", "path", "file_sha256", "ordered_question_ids_sha256"):
        if recorded_view.get(key) != view_info.get(key):
            raise ValueError("Frozen evaluation view changed since the interruption")
    expected_ids = manifest.get("expected_question_ids")
    if expected_ids != view_info["question_ids"] or len(expected_ids) != 100:
        raise ValueError("Failed run does not target the frozen candidate 100-question view")
    queries = select_in_view(queries, expected_ids, "query")

    generation = manifest.get("generation", {})
    if (generation.get("options") != GENERATION_OPTIONS
            or generation.get("reader_prompt_version") != READER_PROMPT_VERSION
            or generation.get("reader_template_sha256") is None
            or manifest.get("retrieval", {}).get("top_k") != 5):
        raise ValueError("Run configuration no longer matches the Dense reader protocol")
    if generation.get("requested_model") != "qwen2.5:3b":
        raise ValueError("Resume is restricted to the authorized Qwen2.5 3B run")

    partial_name = manifest.get("partial_results_file")
    result_name = manifest.get("results_file")
    if (not isinstance(partial_name, str) or Path(partial_name).name != partial_name
            or not partial_name.endswith(".jsonl.part")
            or not isinstance(result_name, str) or Path(result_name).name != result_name):
        raise ValueError("Manifest result paths are not safe raw-directory filenames")
    temporary = output_dir / partial_name
    output_path = output_dir / result_name
    if not temporary.is_file() or output_path.exists():
        raise ValueError("Partial result must exist and final result must not already exist")
    rows = _read_jsonl(temporary)
    start = validate_resume_prefix(rows, expected_ids, manifest["run_id"])
    if not 0 < start < len(expected_ids):
        raise ValueError("Partial run has no resumable suffix")

    session = requests.Session()
    try:
        version_response = session.get(f"{OLLAMA_URL}/api/version", timeout=30)
        version_response.raise_for_status()
        if version_response.json().get("version") != manifest.get("ollama_version"):
            raise ValueError("Ollama version changed since the interruption")
        embedding_info = model_info(session, EMBED_MODEL)
        generation_info = model_info(session, generation["requested_model"])
        if (embedding_info.get("digest") != manifest.get("embedding", {}).get("model", {}).get("digest")
                or generation_info.get("digest") != manifest.get("generation", {}).get("model", {}).get("digest")):
            raise ValueError("Ollama model digest changed since the interruption")
        cache_path = ROOT / manifest["embedding"]["cache_file"]
        vectors, cache_stats = embed_corpus(
            session, corpus, cache_path, corpus_fingerprint(corpus),
            embedding_info["digest"], dataset=dataset,
            build_run_id=manifest["run_id"],
        )
        if cache_stats.get("cache_hit") is not True:
            raise ValueError("Dense embedding cache was not a read-only hit; refusing resume")

        resumption = {
            "resumed_at": datetime.now(timezone.utc).isoformat(),
            "previously_completed_questions": start,
            "remaining_questions": len(expected_ids) - start,
            "partial_prefix_sha256": sha256_file(temporary),
            "cache_revalidated_as_hit": True,
            "resume_runner_sha256": sha256_file(Path(__file__)),
        }
        manifest.setdefault("resumptions", []).append(resumption)
        manifest["status"] = "running"
        manifest.pop("error", None)
        write_json_atomic(manifest_path, manifest)

        with temporary.open("a", encoding="utf-8", newline="\n") as output:
            for position, query in enumerate(queries[start:], start=start + 1):
                question_started = time.perf_counter()
                embed_started = time.perf_counter()
                query_result = post_json(session, "/api/embed", {
                    "model": EMBED_MODEL, "input": query["question"], "truncate": EMBED_TRUNCATE,
                })
                query_embed_seconds = time.perf_counter() - embed_started
                vectors_for_query = query_result.get("embeddings")
                if not isinstance(vectors_for_query, list) or len(vectors_for_query) != 1:
                    raise RuntimeError(f"Ollama returned an invalid query embedding for {query['id']}")
                retrieval_started = time.perf_counter()
                ranked = top_k(vectors_for_query[0], vectors, 5)
                passages = [corpus[index] for index, _score in ranked]
                retrieval_seconds = time.perf_counter() - retrieval_started
                messages = build_reader_messages(query["question"], passages)
                prompt_hash = hashlib.sha256(json.dumps(
                    messages, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")).hexdigest()
                generation_started = time.perf_counter()
                response = post_json(session, "/api/chat", {
                    "model": generation["requested_model"], "messages": messages,
                    "stream": False, "options": GENERATION_OPTIONS,
                })
                generation_seconds = time.perf_counter() - generation_started
                raw_answer = response.get("message", {}).get("content", "")
                answer, answer_status = extract_reader_answer(raw_answer)
                row = {
                    "schema_version": 1, "run_id": manifest["run_id"],
                    "started_at": manifest["started_at"], "mode": "local-poc",
                    "dataset": dataset, "question_id": query["id"],
                    "planned_question_ids": expected_ids, "question": query["question"],
                    "embedding_model": embedding_info, "generation_model": generation_info,
                    "reader_prompt_version": READER_PROMPT_VERSION,
                    "generation_options": GENERATION_OPTIONS,
                    "reader_prompt_source": PROMPT_SOURCE,
                    "reader_prompt_source_commit": PROMPT_SOURCE_COMMIT,
                    "reader_prompt_sha256": prompt_hash, "top_k": 5,
                    "retrieved": [
                        {"id": passage["id"], "score": score}
                        for passage, (_index, score) in zip(passages, ranked)
                    ],
                    "answer": answer, "answer_extraction_status": answer_status,
                    "raw_answer": raw_answer,
                    "prompt_tokens": response.get("prompt_eval_count"),
                    "completion_tokens": response.get("eval_count"),
                    "query_embedding_prompt_tokens": query_result.get("prompt_eval_count"),
                    "query_embedding_total_duration_ns": query_result.get("total_duration"),
                    "query_embedding_load_duration_ns": query_result.get("load_duration"),
                    "query_embedding_client_seconds": query_embed_seconds,
                    "retrieval_seconds": retrieval_seconds,
                    "generation_wall_seconds": generation_seconds,
                    "question_end_to_end_seconds": time.perf_counter() - question_started,
                    "generation_total_duration_ns": response.get("total_duration"),
                    "generation_load_duration_ns": response.get("load_duration"),
                    "generation_eval_duration_ns": response.get("eval_duration"),
                    "generation_seconds": (response["total_duration"] / 1_000_000_000
                        if response.get("total_duration") is not None else None),
                    "generation_tokens_per_second": (
                        response["eval_count"] * 1_000_000_000 / response["eval_duration"]
                        if response.get("eval_count") and response.get("eval_duration") else None),
                    "done_reason": response.get("done_reason"), "done": response.get("done"),
                }
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                output.flush()
                require_completed_generation(response, query["id"])
                safe_print(f"[{position}/{len(queries)}] {query['id']}: {answer}")

        temporary.replace(output_path)
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["results_sha256"] = sha256_file(output_path)
        manifest.pop("partial_results_file", None)
        write_json_atomic(manifest_path, manifest)
        from scripts.evaluate_dense import evaluate, read_jsonl, validate_manifest_file
        final_rows = read_jsonl(output_path)
        validate_manifest_file(output_path, final_rows, manifest)
        metrics = evaluate(final_rows, read_json(labels_path), manifest=manifest)
        metrics_path = output_path.with_suffix(".metrics.json")
        write_json_atomic(metrics_path, metrics)
        safe_print(json.dumps({"status": "verified", "run_id": manifest["run_id"],
                               "questions": len(final_rows), "metrics": metrics,
                               "results": output_path.name,
                               "resumed_questions": len(expected_ids) - start},
                              ensure_ascii=True))
        return output_path
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["error"] = {"type": type(exc).__name__, "message": str(exc)}
        manifest["partial_results_file"] = temporary.name
        write_json_atomic(manifest_path, manifest)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        resume(args.manifest)
    except (OSError, ValueError, KeyError, RuntimeError, requests.RequestException) as exc:
        safe_print(f"Dense resume failed: {exc}")
        raise SystemExit(1)
