"""Run local Dense RAG on a pinned MuSiQue view through the Ollama HTTP API."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
import time
import uuid

import numpy as np
import requests

try:
    from scripts.evaluation_view import load_view, select_in_view
    from scripts.answer_parser import extract_reader_answer
    from scripts.vendor.hipporag2_musique_template import (
        one_shot_rag_qa_input, one_shot_rag_qa_output, rag_qa_system,
    )
except ModuleNotFoundError:  # Direct execution puts the scripts directory on sys.path.
    from evaluation_view import load_view, select_in_view
    from answer_parser import extract_reader_answer
    from vendor.hipporag2_musique_template import (
        one_shot_rag_qa_input, one_shot_rag_qa_output, rag_qa_system,
    )


ROOT = Path(__file__).resolve().parents[1]
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"
GEN_MODEL = "qwen2.5:3b"
READER_PROMPT_VERSION = "hipporag2-musique-one-shot-v6"
READER_SYSTEM = rag_qa_system
DEMO_USER = one_shot_rag_qa_input
DEMO_ASSISTANT = one_shot_rag_qa_output
PROMPT_SOURCE_COMMIT = "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff"
PROMPT_SOURCE_PATH = "src/hipporag/prompts/templates/rag_qa_musique.py"
PROMPT_SOURCE = (
    f"https://github.com/OSU-NLP-Group/HippoRAG/blob/{PROMPT_SOURCE_COMMIT}/"
    f"{PROMPT_SOURCE_PATH}"
)
BATCH_SIZE = 32
GENERATION_OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 512, "num_ctx": 4096}
EMBED_TEXT_VERSION = "title-newline-text-v1"
EMBED_TRUNCATE = False
EMBED_CACHE_SCHEMA_VERSION = 2


def normalize_rows(vectors):
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] == 0:
        raise ValueError("Expected a non-empty matrix of embedding vectors")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0) or not np.all(np.isfinite(norms)):
        raise ValueError("Embedding vectors must have finite, non-zero norms")
    return vectors / norms


def top_k(query_vector, document_vectors, k=5):
    """Return (row index, cosine similarity), sorted from best to worst."""
    documents = normalize_rows(document_vectors)
    query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
    query = normalize_rows(query)[0]
    if query.shape[0] != documents.shape[1]:
        raise ValueError("Query and document embedding dimensions differ")
    if not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")
    scores = documents @ query
    indices = np.argsort(-scores, kind="stable")[:min(k, len(scores))]
    return [(int(index), float(scores[index])) for index in indices]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def post_json(session, endpoint, payload, timeout=300):
    response = session.post(f"{OLLAMA_URL}{endpoint}", json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def require_completed_generation(generation, question_id):
    """Reject a partial Ollama response so the run manifest cannot say completed."""
    if generation.get("done") is not True or not generation.get("done_reason"):
        raise RuntimeError(
            f"Ollama generation for {question_id} did not report a completed response "
            "(expected done=true and a non-empty done_reason)"
        )


def model_info(session, model_name):
    response = session.get(f"{OLLAMA_URL}/api/tags", timeout=30)
    response.raise_for_status()
    target = model_name if ":" in model_name else f"{model_name}:latest"
    for item in response.json().get("models", []):
        if item.get("name") == target or item.get("model") == target:
            return {
                "name": item.get("name", target),
                "digest": item.get("digest"),
                "size_bytes": item.get("size"),
                "details": item.get("details", {}),
            }
    raise RuntimeError(f"Model {target} is not installed in Ollama")


def corpus_fingerprint(corpus):
    content = json.dumps(corpus, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cache_provenance_path(cache_path):
    return cache_path.with_suffix(".provenance.json")


def recover_cache_build_provenance(cache_path, fingerprint, model_digest):
    """Recover build cost only from a completed, hash-verified historical run."""
    cache_relative = cache_path.relative_to(ROOT).as_posix()
    for manifest_path in (ROOT / "results" / "raw").glob("dense-*.manifest.json"):
        try:
            manifest = read_json(manifest_path)
            embedding = manifest.get("embedding", {})
            model = embedding.get("model", {})
            if (manifest.get("status") != "completed"
                    or embedding.get("cache_file") != cache_relative
                    or manifest.get("inputs", {}).get("corpus_fingerprint") != fingerprint
                    or model.get("digest") != model_digest
                    or embedding.get("text_version") != EMBED_TEXT_VERSION
                    or embedding.get("truncate") is not EMBED_TRUNCATE
                    or embedding.get("cache_schema") != EMBED_CACHE_SCHEMA_VERSION):
                continue
            result_path = manifest_path.parent / manifest["results_file"]
            if sha256_file(result_path) != manifest.get("results_sha256"):
                continue
            old_index = manifest.get("index_embedding") or {}
            build_seconds = old_index.get(
                "build_seconds_this_run", manifest.get("index_embedding_seconds_this_run")
            )
            if not isinstance(build_seconds, (int, float)) or build_seconds <= 0:
                continue
            return {
                "schema_version": 1,
                "provenance_kind": "reconciled_historical_manifest",
                "dataset": manifest.get("dataset"),
                "build_run_id": manifest.get("run_id"),
                "build_seconds": build_seconds,
                "embedding_prompt_tokens": old_index.get("embedding_prompt_tokens"),
                "api_total_duration_ns": old_index.get("api_total_duration_ns"),
                "api_load_duration_ns": old_index.get("api_load_duration_ns"),
                "source_manifest": manifest_path.relative_to(ROOT).as_posix(),
                "source_manifest_sha256": sha256_file(manifest_path),
                "source_results_sha256": manifest.get("results_sha256"),
                "corpus_fingerprint": fingerprint,
                "model_digest": model_digest,
                "text_version": EMBED_TEXT_VERSION,
                "truncate": EMBED_TRUNCATE,
                "cache_schema": EMBED_CACHE_SCHEMA_VERSION,
                "cache_file": cache_relative,
                "cache_sha256_at_registration": sha256_file(cache_path),
                "usage_note": "Historical build token/API usage is unknown when absent from the source manifest.",
            }
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return None


def get_cache_build_provenance(cache_path, fingerprint, model_digest):
    sidecar = cache_provenance_path(cache_path)
    cache_sha = sha256_file(cache_path)
    try:
        provenance = read_json(sidecar)
        matches = (
            provenance.get("schema_version") == 1
            and provenance.get("cache_file") == cache_path.relative_to(ROOT).as_posix()
            and provenance.get("cache_sha256_at_registration") == cache_sha
            and provenance.get("corpus_fingerprint") == fingerprint
            and provenance.get("model_digest") == model_digest
            and provenance.get("text_version") == EMBED_TEXT_VERSION
            and provenance.get("truncate") is EMBED_TRUNCATE
            and provenance.get("cache_schema") == EMBED_CACHE_SCHEMA_VERSION
        )
        if matches:
            return provenance
    except (OSError, ValueError, KeyError, TypeError):
        pass
    provenance = recover_cache_build_provenance(cache_path, fingerprint, model_digest)
    if provenance is not None:
        write_json_atomic(sidecar, provenance)
    return provenance


def write_json_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    temporary.replace(path)


def git_snapshot():
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, check=True,
                                    capture_output=True, text=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    source_files = ("scripts/run_dense.py", "scripts/replay_reader.py",
                    "scripts/evaluate_dense.py", "scripts/answer_parser.py")
    return {
        "commit": commit,
        "working_tree_dirty": dirty,
        "source_sha256": {name: sha256_file(ROOT / name) for name in source_files
                          if (ROOT / name).is_file()},
    }


def validate_processed_data(dataset, data_dir, queries, corpus, labels_path=None):
    report_path = ROOT / "results" / "data" / "subsamples.json"
    ids_path = ROOT / "data" / "ids" / f"{dataset}_s500.json"
    report = read_json(report_path)
    ids_manifest = read_json(ids_path)
    dataset_report = report["datasets"][dataset]
    actual_hashes = {}
    for filename in ("queries.json", "corpus.json"):
        actual_hashes[filename] = sha256_file(data_dir / filename)
        expected = dataset_report["output_sha256"].get(filename)
        if actual_hashes[filename] != expected:
            raise ValueError(f"Processed {filename} does not match the pinned subsample report")
    labels_path = Path(labels_path) if labels_path else Path(data_dir) / "labels.json"
    if labels_path.is_file():
        actual_hashes["labels.json"] = sha256_file(labels_path)
        expected = dataset_report["output_sha256"].get("labels.json")
        if actual_hashes["labels.json"] != expected:
            raise ValueError("Processed labels.json does not match the pinned subsample report")
    query_ids = [row["id"] for row in queries]
    corpus_ids = [row["id"] for row in corpus]
    if query_ids != ids_manifest["question_ids"]:
        raise ValueError("Processed question IDs do not match the pinned IDs manifest")
    if corpus_ids != ids_manifest["passage_ids"]:
        raise ValueError("Processed passage IDs do not match the pinned IDs manifest")
    return {
        "report_sha256": sha256_file(report_path),
        "ids_manifest_sha256": sha256_file(ids_path),
        "source_revision": ids_manifest["source_revision"],
        "output_sha256": actual_hashes,
    }


def embed_corpus(session, corpus, cache_path, fingerprint, model_digest,
                 dataset=None, build_run_id=None):
    ids = [row["id"] for row in corpus]
    if cache_path.exists():
        cache_started = time.perf_counter()
        try:
            with np.load(cache_path, allow_pickle=False) as saved:
                saved_ids = saved["ids"].astype(str).tolist()
                saved_fingerprint = str(saved["fingerprint"].item())
                saved_model = str(saved["model"].item())
                saved_digest = str(saved["model_digest"].item())
                saved_schema = int(saved["cache_schema"].item()) if "cache_schema" in saved else None
                saved_text_version = str(saved["text_version"].item()) if "text_version" in saved else None
                saved_truncate = bool(saved["truncate"].item()) if "truncate" in saved else None
                vectors = saved["vectors"]
            if (saved_ids == ids and saved_fingerprint == fingerprint and saved_model == EMBED_MODEL
                    and saved_digest == model_digest and saved_schema == EMBED_CACHE_SCHEMA_VERSION
                    and saved_text_version == EMBED_TEXT_VERSION and saved_truncate is EMBED_TRUNCATE):
                if (vectors.ndim == 2 and vectors.shape[0] == len(corpus)
                        and np.all(np.isfinite(vectors)) and np.all(np.linalg.norm(vectors, axis=1) > 0)):
                    print(f"Embeddings cache: {cache_path.relative_to(ROOT)} ({vectors.shape[0]} passages)")
                    build_provenance = get_cache_build_provenance(
                        cache_path, fingerprint, model_digest
                    )
                    if build_provenance is None:
                        print("Original embedding build cost is unknown for this cache.")
                    return vectors, {
                        "cache_hit": True,
                        "cache_read_seconds": time.perf_counter() - cache_started,
                        "build_seconds_this_run": None,
                        "api_batches": 0,
                        "embedding_prompt_tokens": None,
                        "api_total_duration_ns": None,
                        "api_load_duration_ns": None,
                        "cache_build_provenance": build_provenance,
                    }
        except (OSError, ValueError, KeyError):
            pass
        print("Embeddings cache is stale; rebuilding it.")

    document_texts = [f"{row['title']}\n{row['text']}" for row in corpus]
    all_vectors = []
    batch_results = []
    started = time.perf_counter()
    for offset in range(0, len(document_texts), BATCH_SIZE):
        batch = document_texts[offset:offset + BATCH_SIZE]
        result = post_json(session, "/api/embed", {
            "model": EMBED_MODEL, "input": batch, "truncate": EMBED_TRUNCATE
        })
        vectors = result.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise RuntimeError(f"Ollama returned an unexpected embedding batch at offset {offset}")
        all_vectors.extend(vectors)
        batch_results.append(result)
        done = min(offset + len(batch), len(document_texts))
        print(f"Embedded passages: {done}/{len(document_texts)}", end="\r", flush=True)
    elapsed = time.perf_counter() - started
    matrix = np.asarray(all_vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != len(corpus):
        raise RuntimeError("Ollama returned an invalid corpus embedding matrix")
    normalize_rows(matrix)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".npz.part")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, ids=np.asarray(ids), vectors=matrix,
                            fingerprint=np.asarray(fingerprint), model=np.asarray(EMBED_MODEL),
                            model_digest=np.asarray(model_digest),
                            cache_schema=np.asarray(EMBED_CACHE_SCHEMA_VERSION),
                            text_version=np.asarray(EMBED_TEXT_VERSION),
                            truncate=np.asarray(EMBED_TRUNCATE))
    temporary.replace(cache_path)
    print(f"Embedded passages: {len(corpus)}/{len(corpus)}")
    def sum_if_complete(key):
        values = [item.get(key) for item in batch_results]
        return sum(values) if values and all(value is not None for value in values) else None

    index_stats = {
        "cache_hit": False,
        "cache_read_seconds": 0.0,
        "build_seconds_this_run": elapsed,
        "api_batches": len(batch_results),
        "embedding_prompt_tokens": sum_if_complete("prompt_eval_count"),
        "api_total_duration_ns": sum_if_complete("total_duration"),
        "api_load_duration_ns": sum_if_complete("load_duration"),
    }
    build_provenance = {
        "schema_version": 1,
        "provenance_kind": "built_this_run",
        "dataset": dataset,
        "build_run_id": build_run_id,
        "build_seconds": elapsed,
        "embedding_prompt_tokens": index_stats["embedding_prompt_tokens"],
        "api_total_duration_ns": index_stats["api_total_duration_ns"],
        "api_load_duration_ns": index_stats["api_load_duration_ns"],
        "corpus_fingerprint": fingerprint,
        "model_digest": model_digest,
        "text_version": EMBED_TEXT_VERSION,
        "truncate": EMBED_TRUNCATE,
        "cache_schema": EMBED_CACHE_SCHEMA_VERSION,
        "cache_file": cache_path.relative_to(ROOT).as_posix(),
        "cache_sha256_at_registration": sha256_file(cache_path),
        "usage_note": "Null token or API duration fields mean the embedding response did not report them.",
    }
    write_json_atomic(cache_provenance_path(cache_path), build_provenance)
    index_stats["cache_build_provenance"] = build_provenance
    return matrix, index_stats


def build_reader_messages(question, passages):
    context = "\n\n".join(
        f"Wikipedia Title: {row['title']}\n{row['text']}"
        for row in passages
    )
    return [
        {"role": "system", "content": READER_SYSTEM},
        {"role": "user", "content": DEMO_USER},
        {"role": "assistant", "content": DEMO_ASSISTANT},
        {"role": "user", "content": f"{context}\n\nQuestion: {question}\nThought: "},
    ]


def reader_template_sha256():
    return hashlib.sha256(
        json.dumps([READER_SYSTEM, DEMO_USER, DEMO_ASSISTANT], ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def safe_print(*values, **kwargs):
    """Keep non-UTF8 Windows consoles from aborting after a saved result row."""
    stream = kwargs.get("file", sys.stdout)
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (OSError, ValueError):
            pass
    print(*values, **kwargs)


def run(dataset="musique", limit=10, top_n=5, generation_model=GEN_MODEL,
        id_view_path=None):
    if dataset != "musique":
        raise ValueError("The pinned HippoRAG one-shot reader is validated only for MuSiQue")
    data_dir = ROOT / "data" / "processed" / dataset
    queries_path = data_dir / "queries.json"
    corpus_path = data_dir / "corpus.json"
    queries = read_json(queries_path)
    corpus = read_json(corpus_path)
    data_provenance = validate_processed_data(
        dataset, data_dir, queries, corpus, data_dir / "labels.json")
    labels_path = data_dir / "labels.json"
    view_info = load_view(id_view_path, dataset, labels_path) if id_view_path else None
    if view_info:
        if limit != len(view_info["question_ids"]):
            raise ValueError("--limit must equal the frozen evaluation view size")
        queries = select_in_view(queries, view_info["question_ids"], "query")
    if not 1 <= limit <= 100:
        raise ValueError("Local benchmark limit must be between 1 and 100; use a pinned view")
    if not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top-k must be a positive integer")
    if len(queries) < limit:
        raise ValueError(f"Requested {limit} questions but only {len(queries)} are available")
    queries = queries[:limit]
    planned_question_ids = [query["id"] for query in queries]
    if len(set(planned_question_ids)) != len(planned_question_ids):
        raise ValueError("Selected query IDs contain duplicates")
    fingerprint = corpus_fingerprint(corpus)
    cache_path = ROOT / "indexes" / "dense" / f"{dataset}-{EMBED_MODEL}-notrunc-v2.npz"
    output_dir = ROOT / "results" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    started_run = datetime.now(timezone.utc).isoformat()
    output_path = output_dir / f"dense-{dataset}-{run_id}.jsonl"
    temporary = output_path.with_suffix(".jsonl.part")
    manifest_path = output_path.with_suffix(".manifest.json")
    prompt_template_sha256 = reader_template_sha256()
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "starting",
        "mode": "local-poc",
        "dataset": dataset,
        "started_at": started_run,
        "expected_question_ids": planned_question_ids,
        "inputs": {
            "queries_sha256": sha256_file(queries_path),
            "corpus_sha256": sha256_file(corpus_path),
            "corpus_fingerprint": fingerprint,
            **data_provenance,
        },
        "evaluation_view": ({key: value for key, value in view_info.items()
                              if key != "question_ids"} if view_info else None),
        "code": git_snapshot(),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpy": np.__version__,
            "requests": requests.__version__,
        },
        "embedding": {
            "requested_model": EMBED_MODEL,
            "text_version": EMBED_TEXT_VERSION,
            "truncate": EMBED_TRUNCATE,
            "batch_size": BATCH_SIZE,
            "cache_schema": EMBED_CACHE_SCHEMA_VERSION,
            "cache_file": cache_path.relative_to(ROOT).as_posix(),
        },
        "generation": {
            "requested_model": generation_model,
            "options": GENERATION_OPTIONS,
            "reader_prompt_version": READER_PROMPT_VERSION,
            "reader_prompt_source": PROMPT_SOURCE,
            "reader_prompt_source_commit": PROMPT_SOURCE_COMMIT,
            "reader_prompt_source_path": PROMPT_SOURCE_PATH,
            "reader_template_sha256": prompt_template_sha256,
        },
        "retrieval": {"method": "cosine", "top_k": top_n},
        "results_file": output_path.name,
    }
    write_json_atomic(manifest_path, manifest)
    session = requests.Session()
    try:
        version_response = session.get(f"{OLLAMA_URL}/api/version", timeout=30)
        version_response.raise_for_status()
        embedding_info = model_info(session, EMBED_MODEL)
        generation_info = model_info(session, generation_model)
        manifest["ollama_version"] = version_response.json().get("version")
        manifest["embedding"]["model"] = embedding_info
        manifest["generation"]["model"] = generation_info
        manifest["status"] = "running"
        write_json_atomic(manifest_path, manifest)

        print(f"Dataset: {dataset}; questions: {len(queries)}; corpus passages: {len(corpus)}")
        print(f"Embedding model: {embedding_info['name']} ({embedding_info['digest']})")
        print(f"Generator: {generation_info['name']} ({generation_info['digest']}); "
              f"prompt: {READER_PROMPT_VERSION}; top-k: {top_n}")
        document_vectors, index_embedding = embed_corpus(
            session, corpus, cache_path, fingerprint, embedding_info["digest"],
            dataset=dataset, build_run_id=run_id,
        )
        manifest["index_embedding"] = index_embedding
        write_json_atomic(manifest_path, manifest)

        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            for position, query in enumerate(queries, start=1):
                question_started = time.perf_counter()
                query_embed_started = time.perf_counter()
                query_result = post_json(session, "/api/embed", {
                    "model": EMBED_MODEL, "input": query["question"], "truncate": EMBED_TRUNCATE
                })
                query_embed_client_seconds = time.perf_counter() - query_embed_started
                query_vectors = query_result.get("embeddings")
                if not isinstance(query_vectors, list) or len(query_vectors) != 1:
                    raise RuntimeError(f"Ollama returned an invalid query embedding for {query['id']}")
                retrieval_started = time.perf_counter()
                ranked = top_k(query_vectors[0], document_vectors, top_n)
                passages = [corpus[index] for index, _score in ranked]
                retrieval_seconds = time.perf_counter() - retrieval_started
                messages = build_reader_messages(query["question"], passages)
                prompt_sha256 = hashlib.sha256(
                    json.dumps(messages, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                generation_started = time.perf_counter()
                generation = post_json(session, "/api/chat", {
                    "model": generation_model,
                    "messages": messages,
                    "stream": False,
                    "options": GENERATION_OPTIONS,
                })
                generation_wall_seconds = time.perf_counter() - generation_started
                raw_answer = generation.get("message", {}).get("content", "")
                answer, answer_status = extract_reader_answer(raw_answer)
                question_end_to_end_seconds = time.perf_counter() - question_started
                row = {
                    "schema_version": 1,
                    "run_id": run_id,
                    "started_at": started_run,
                    "mode": "local-poc",
                    "dataset": dataset,
                    "question_id": query["id"],
                    "planned_question_ids": planned_question_ids,
                    "question": query["question"],
                    "embedding_model": embedding_info,
                    "generation_model": generation_info,
                    "reader_prompt_version": READER_PROMPT_VERSION,
                    "generation_options": GENERATION_OPTIONS,
                    "reader_prompt_source": PROMPT_SOURCE,
                    "reader_prompt_source_commit": PROMPT_SOURCE_COMMIT,
                    "reader_prompt_sha256": prompt_sha256,
                    "top_k": top_n,
                    "retrieved": [
                        {"id": passage["id"], "score": score}
                        for passage, (_index, score) in zip(passages, ranked)
                    ],
                    "answer": answer,
                    "answer_extraction_status": answer_status,
                    "raw_answer": raw_answer,
                    "prompt_tokens": generation.get("prompt_eval_count"),
                    "completion_tokens": generation.get("eval_count"),
                    "query_embedding_prompt_tokens": query_result.get("prompt_eval_count"),
                    "query_embedding_total_duration_ns": query_result.get("total_duration"),
                    "query_embedding_load_duration_ns": query_result.get("load_duration"),
                    "query_embedding_client_seconds": query_embed_client_seconds,
                    "retrieval_seconds": retrieval_seconds,
                    "generation_wall_seconds": generation_wall_seconds,
                    "question_end_to_end_seconds": question_end_to_end_seconds,
                    "generation_total_duration_ns": generation.get("total_duration"),
                    "generation_load_duration_ns": generation.get("load_duration"),
                    "generation_eval_duration_ns": generation.get("eval_duration"),
                    "generation_seconds": (
                        generation["total_duration"] / 1_000_000_000
                        if generation.get("total_duration") is not None else None
                    ),
                    "generation_tokens_per_second": (
                        generation["eval_count"] * 1_000_000_000 / generation["eval_duration"]
                        if generation.get("eval_count") and generation.get("eval_duration") else None
                    ),
                    "done_reason": generation.get("done_reason"),
                    "done": generation.get("done"),
                }
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                output.flush()
                require_completed_generation(generation, query["id"])
                safe_print(f"[{position}/{len(queries)}] {query['id']}: {row['answer']}")
        temporary.replace(output_path)
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["results_sha256"] = sha256_file(output_path)
        write_json_atomic(manifest_path, manifest)
        if index_embedding["build_seconds_this_run"] is not None:
            safe_print(f"Corpus embedding seconds: {index_embedding['build_seconds_this_run']:.2f}")
        else:
            safe_print(f"Embeddings cache read seconds: {index_embedding['cache_read_seconds']:.4f}")
        safe_print(f"Run ID: {run_id}")
        safe_print(f"Results: {output_path.relative_to(ROOT)}")
        safe_print(f"Manifest: {manifest_path.relative_to(ROOT)}")
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        manifest["error"] = {"type": type(exc).__name__, "message": str(exc)}
        if temporary.exists():
            manifest["partial_results_file"] = temporary.name
        write_json_atomic(manifest_path, manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("musique",), default="musique",
                        help="HippoRAG one-shot reader currently validated for MuSiQue only")
    parser.add_argument("--limit", type=int, default=10,
                        help="number of initial fixed-ID questions (1-100; baseline100 includes debug10)")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--id-view", type=Path,
                        help="frozen ID view; --limit must equal its question count")
    parser.add_argument("--generation-model", default=GEN_MODEL,
                        help=f"installed Ollama generation model (default: {GEN_MODEL})")
    args = parser.parse_args()
    try:
        run(args.dataset, args.limit, args.top_k, args.generation_model, args.id_view)
    except (OSError, requests.RequestException, ValueError, RuntimeError, KeyError) as exc:
        safe_print(f"Dense RAG pilot failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
