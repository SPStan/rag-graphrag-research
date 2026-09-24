"""Run a small or full HippoRAG 2 experiment with local OpenAI-compatible models."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import platform
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "results" / "raw"
DEFAULT_STORAGE = ROOT / "storage" / "hipporag2"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
RUNNER_VERSION = "hipporag2-local-runner-v1"
PROMPT_VERSION = "hipporag2-upstream-reader-v1"
LOG = logging.getLogger("run_hipporag")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def write_json_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_jsonl_atomic(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def canonical_key(title, text):
    if not isinstance(title, str) or not isinstance(text, str) or not text.strip():
        raise ValueError("Each passage needs a non-empty title and text")
    return " ".join(title.split()), " ".join(text.split())


def passage_id(title, text):
    payload = json_bytes(canonical_key(title, text)).rstrip(b"\n")
    return "sha256:" + sha256_bytes(payload)


def normalize_inputs(corpus, queries, labels=None):
    """Normalize project data and the upstream HippoRAG sample schema."""
    if not isinstance(corpus, list) or not corpus:
        raise ValueError("Corpus JSON must be a non-empty list")
    normalized = []
    by_id = {}
    by_key = {}
    for item in corpus:
        title, text = canonical_key(item.get("title"), item.get("text"))
        key = (title, text)
        pid = item.get("id") or passage_id(title, text)
        if not isinstance(pid, str) or not pid:
            raise ValueError("Passage IDs must be non-empty strings")
        if pid in by_id and by_id[pid] != key:
            raise ValueError(f"Passage ID collision: {pid}")
        if key in by_key:
            continue
        passage = {"id": pid, "title": title, "text": text}
        normalized.append(passage)
        by_id[pid] = key
        by_key[key] = pid

    if not isinstance(queries, list) or not queries:
        raise ValueError("Queries JSON must be a non-empty list")
    labels_by_id = {}
    if labels is not None:
        if not isinstance(labels, list):
            raise ValueError("Labels JSON must be a list")
        for label in labels:
            qid = label.get("id")
            if not isinstance(qid, str) or not qid or qid in labels_by_id:
                raise ValueError("Labels need unique non-empty id values")
            labels_by_id[qid] = label

    normalized_queries = []
    derived_labels = []
    seen_query_ids = set()
    for query in queries:
        qid = query.get("id", query.get("_id"))
        question = query.get("question")
        if not isinstance(qid, str) or not qid or qid in seen_query_ids:
            raise ValueError("Queries need unique non-empty id values")
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"Empty question: {qid}")
        seen_query_ids.add(qid)
        normalized_queries.append({"id": qid, "question": question})
        label = labels_by_id.get(qid)
        if label is None:
            answer = query.get("answer", query.get("gold_ans"))
            if answer is None:
                raise ValueError(f"No answer label for query {qid}; pass a separate labels file")
            if isinstance(answer, list):
                answer, aliases = (answer[0], answer[1:]) if answer else ("", [])
            else:
                aliases = []
            aliases.extend(query.get("answer_aliases", []))
            supporting_ids = set()
            if "paragraphs" in query:
                for paragraph in query["paragraphs"]:
                    if paragraph.get("is_supporting", True):
                        key = canonical_key(paragraph.get("title"),
                                            paragraph.get("text", paragraph.get("paragraph_text", "")))
                        if key not in by_key:
                            raise ValueError(f"Supporting passage for {qid} is absent from corpus")
                        supporting_ids.add(by_key[key])
            if not supporting_ids:
                raise ValueError(f"No supporting IDs for {qid}; pass a separate labels file")
            label = {"id": qid, "answer": answer, "answer_aliases": aliases,
                     "supporting_ids": sorted(supporting_ids)}
        derived_labels.append(label)

    if labels is not None:
        missing = seen_query_ids - set(labels_by_id)
        if missing:
            raise ValueError(f"Missing labels for query IDs: {sorted(missing)[:3]}")
        derived_labels = [labels_by_id[q["id"]] for q in normalized_queries]
    for label in derived_labels:
        if label["id"] not in seen_query_ids:
            raise ValueError(f"Label does not match a query: {label['id']}")
        supporting = label.get("supporting_ids")
        if not isinstance(supporting, list) or not supporting:
            raise ValueError(f"No supporting passages in label {label['id']}")
        absent = set(supporting) - set(by_id)
        if absent:
            raise ValueError(f"Supporting IDs absent from corpus for {label['id']}: {sorted(absent)[:3]}")
        answers = [label.get("answer"), *label.get("answer_aliases", [])]
        if not all(isinstance(answer, str) and answer.strip() for answer in answers):
            raise ValueError(f"Label {label['id']} needs a non-empty answer and aliases")
    return normalized, normalized_queries, derived_labels


def model_info(model_name, base_url=OLLAMA_BASE_URL):
    """Return the exact installed Ollama model digest without printing secrets."""
    from urllib.request import urlopen

    with urlopen(base_url.removesuffix("/v1") + "/api/tags", timeout=20) as response:
        models = json.loads(response.read().decode("utf-8")).get("models", [])
    target = model_name if ":" in model_name else model_name + ":latest"
    for item in models:
        if item.get("name") == target or item.get("model") == target:
            return {"name": item.get("name", target), "digest": item.get("digest"),
                    "size_bytes": item.get("size"), "details": item.get("details", {})}
    raise RuntimeError(f"Model is not installed in Ollama: {target}")


def runtime_context_length(model_name, base_url=OLLAMA_BASE_URL):
    """Read the active Ollama runtime context after the model has been used."""
    from urllib.request import urlopen

    with urlopen(base_url.removesuffix("/v1") + "/api/ps", timeout=20) as response:
        models = json.loads(response.read().decode("utf-8")).get("models", [])
    target = model_name if ":" in model_name else model_name + ":latest"
    for item in models:
        if item.get("name") == target or item.get("model") == target:
            value = item.get("context_length")
            if isinstance(value, int) and value > 0:
                return value
    return None


def windows_safe_model_label(model_name):
    """Use a path-safe HippoRAG label; the actual Ollama model name stays unchanged."""
    label = re.sub(r"[^A-Za-z0-9._-]+", "_", model_name).strip("._-")
    if not label:
        raise ValueError("Model name cannot be converted to a safe local label")
    return label


def git_snapshot():
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, check=True,
                                    capture_output=True, text=True).stdout.strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def _append_event(events, lock, event):
    with lock:
        events.append(event)


def instrument_models(rag, corpus, query_text_to_id, events, lock):
    """Record SDK usage and cache state without storing any raw prompts or texts."""
    local = threading.local()
    passage_id_by_text = {item["title"] + "\n" + item["text"]: item["id"] for item in corpus}
    query_id_by_embedding = {text: qid for text, qid in query_text_to_id.items()}

    llm = rag.qa_llm
    original_infer = llm.infer

    def tracked_infer(*args, **kwargs):
        messages = kwargs.get("messages", args[0] if args else None)
        if messages is None:
            raise ValueError("Missing messages for a tracked HippoRAG chat call")
        serialized = json.dumps(messages, ensure_ascii=False, sort_keys=True, default=str)
        try:
            response, metadata, cache_hit = original_infer(*args, **kwargs)
        except Exception as exc:
            stage = getattr(local, "stage", "unknown")
            event = {"kind": "chat", "stage": stage,
                     "passage_id": getattr(local, "passage_id", None),
                     "question_id": getattr(local, "question_id", None),
                     "prompt_sha256": sha256_bytes(serialized.encode("utf-8")),
                     "usage_unknown": True, "error_type": type(exc).__name__}
            _append_event(events, lock, event)
            raise
        complete_usage = all(isinstance(metadata.get(key), int)
                             and not isinstance(metadata.get(key), bool)
                             and metadata[key] >= 0
                             for key in ("prompt_tokens", "completion_tokens"))
        if not complete_usage:
            raise RuntimeError("HippoRAG chat response did not provide complete token usage")
        event = {"kind": "chat", "stage": getattr(local, "stage", "unknown"),
                 "passage_id": getattr(local, "passage_id", None),
                 "question_id": getattr(local, "question_id", None),
                 "prompt_sha256": sha256_bytes(serialized.encode("utf-8")),
                 "usage": metadata, "cache_hit": bool(cache_hit)}
        _append_event(events, lock, event)
        return response, metadata, cache_hit

    llm.infer = tracked_infer

    embedding_model = rag.embedding_model
    original_encode = embedding_model.encode

    def tracked_encode(texts):
        result = original_encode(texts)
        usage = dict(embedding_model.last_usage or {})
        if (not isinstance(usage.get("prompt_tokens"), int)
                or isinstance(usage.get("prompt_tokens"), bool)
                or usage["prompt_tokens"] < 0):
            raise RuntimeError("HippoRAG embedding response did not provide prompt token usage")
        items = []
        for text in texts:
            pid = passage_id_by_text.get(text)
            qid = query_id_by_embedding.get(text)
            items.append({"input_sha256": sha256_bytes(text.encode("utf-8")),
                          "input_chars": len(text),
                          "input_type": "passage" if pid else ("query" if qid else "entity_or_fact"),
                          "passage_id": pid, "question_id": qid})
        event = {"kind": "embedding", "stage": getattr(local, "stage", "unknown"),
                 "items": items, "batch_size": len(texts), "usage": usage}
        _append_event(events, lock, event)
        return result

    embedding_model.encode = tracked_encode

    original_ner = rag.openie.ner
    def tracked_ner(chunk_key, passage):
        local.stage = "openie_ner"
        local.passage_id = passage_id_by_text.get(passage)
        try:
            return original_ner(chunk_key, passage)
        finally:
            local.stage = "index_embedding"
            local.passage_id = None
    rag.openie.ner = tracked_ner

    original_triples = rag.openie.triple_extraction
    def tracked_triples(chunk_key, passage, named_entities):
        local.stage = "openie_triples"
        local.passage_id = passage_id_by_text.get(passage)
        try:
            return original_triples(chunk_key, passage, named_entities)
        finally:
            local.stage = "index_embedding"
            local.passage_id = None
    rag.openie.triple_extraction = tracked_triples

    original_index = rag.index
    def tracked_index(docs):
        local.stage = "index_embedding"
        try:
            return original_index(docs)
        finally:
            local.stage = "unknown"
    rag.index = tracked_index

    original_retrieve = rag.retrieve
    def tracked_retrieve(queries, *args, **kwargs):
        previous = getattr(local, "stage", "unknown")
        local.stage = "graph_retrieval"
        try:
            return original_retrieve(queries, *args, **kwargs)
        finally:
            local.stage = previous
    rag.retrieve = tracked_retrieve

    original_qa = rag.qa
    def tracked_qa(solutions):
        local.stage = "qa"
        try:
            return original_qa(solutions)
        finally:
            local.stage = "unknown"
    rag.qa = tracked_qa

    # Queries are mapped using their text when embedding instructions modify the input.
    # Chat question association is assigned by the caller around retrieve/qa in question batches.
    return local


@contextmanager
def current_question(local, qid):
    old = getattr(local, "question_id", None)
    local.question_id = qid
    try:
        yield
    finally:
        local.question_id = old


def collect_cache_counts(rag, before):
    after = {
        "passages": set(rag.chunk_embedding_store.get_all_ids()),
        "entities": set(rag.entity_embedding_store.get_all_ids()),
        "facts": set(rag.fact_embedding_store.get_all_ids()),
    }
    output = {}
    for kind, ids in after.items():
        output[kind] = {"stored": len(ids), "new": len(ids - before[kind]),
                        "reused": len(ids & before[kind])}
    return output


def summarize_usage(events, corpus):
    by_passage = {item["id"]: {"passage_embedding_tokens": 0,
                               "openie_prompt_tokens": 0,
                               "openie_completion_tokens": 0,
                               "openie_cached_prompt_tokens": 0,
                               "openie_cached_completion_tokens": 0,
                               "embedding_calls": 0, "openie_calls": 0}
                  for item in corpus}
    phases = {}
    for event in events:
        stage = event.get("stage", "unknown")
        totals = phases.setdefault(stage, {"api_prompt_tokens": 0, "api_completion_tokens": 0,
                                            "api_embedding_tokens": 0,
                                            "cached_prompt_tokens": 0, "cached_completion_tokens": 0,
                                            "calls": 0,
                                            "cache_hits": 0, "usage_unknown_calls": 0})
        totals["calls"] += 1
        if event.get("usage_unknown"):
            totals["usage_unknown_calls"] += 1
            continue
        usage = event.get("usage") or {}
        if event["kind"] == "chat":
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
            if event.get("cache_hit"):
                totals["cached_prompt_tokens"] += prompt
                totals["cached_completion_tokens"] += completion
                totals["cache_hits"] += 1
            else:
                totals["api_prompt_tokens"] += prompt
                totals["api_completion_tokens"] += completion
            pid = event.get("passage_id")
            if pid in by_passage and stage in ("openie_ner", "openie_triples"):
                row = by_passage[pid]
                row["openie_calls"] += 1
                if event.get("cache_hit"):
                    row["openie_cached_prompt_tokens"] += prompt
                    row["openie_cached_completion_tokens"] += completion
                else:
                    row["openie_prompt_tokens"] += prompt
                    row["openie_completion_tokens"] += completion
        else:
            count = usage.get("prompt_tokens")
            if isinstance(count, int):
                totals["api_embedding_tokens"] += count
            for item in event.get("items", []):
                pid = item.get("passage_id")
                if pid in by_passage:
                    row = by_passage[pid]
                    row["embedding_calls"] += 1
                    row["passage_embedding_tokens"] += count or 0
    return {"phases": phases, "per_passage": by_passage}


def load_hipporag_classes():
    """Import the optional engine only when the runner is invoked."""
    try:
        from hipporag.HippoRAG import HippoRAG
        from hipporag.llm.openai_gpt import CacheOpenAI
        from hipporag.embedding_model.OpenAI import OpenAIEmbeddingModel
        from hipporag.utils.config_utils import BaseConfig
    except ImportError as exc:
        raise RuntimeError(
            "HippoRAG dependencies are missing. Install requirements-hipporag2.txt "
            "into a separate venv and run this script with that venv's Python."
        ) from exc
    return HippoRAG, CacheOpenAI, OpenAIEmbeddingModel, BaseConfig


def build_rows(run_id, dataset, queries, solutions, raw_answers,
               generation_metadata, corpus_by_text, query_usage, model_embedding,
               model_generation, top_k, generation_options, index_fingerprint):
    rows = []
    for query, solution, raw, metadata in zip(queries, solutions, raw_answers, generation_metadata):
        if not isinstance(raw, str) or not isinstance(solution.answer, str):
            raise RuntimeError(f"HippoRAG returned a missing answer for {query['id']}")
        finish_reason = metadata.get("finish_reason")
        if finish_reason not in ("stop", "length"):
            raise RuntimeError(f"Generation for {query['id']} did not finish normally: {finish_reason}")
        docs = []
        scores = solution.doc_scores.tolist() if solution.doc_scores is not None else []
        for index, content in enumerate(solution.docs[:top_k]):
            passage = corpus_by_text.get(content)
            if passage is None:
                raise RuntimeError("HippoRAG returned passage text absent from the indexed corpus")
            docs.append({"id": passage["id"], "title": passage["title"], "text": passage["text"],
                         "score": float(scores[index]) if index < len(scores) else None})
        qa_usage = metadata
        prompt_tokens = qa_usage.get("prompt_tokens")
        completion_tokens = qa_usage.get("completion_tokens")
        row = {
            "run_id": run_id, "dataset": dataset, "mode": "local-poc",
            "question_id": query["id"], "planned_question_ids": [q["id"] for q in queries],
            "question": query["question"], "answer": solution.answer,
            "raw_answer": raw,
            "answer_extraction_status": "ok" if "Answer:" in raw else "missing_answer_marker",
            "done": True, "done_reason": finish_reason,
            "retrieved": docs,
            "top_k": top_k,
            "generation_model": model_generation,
            "embedding_model": model_embedding,
            "reader_prompt_version": PROMPT_VERSION,
            "generation_options": generation_options,
            "index_fingerprint": index_fingerprint,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "query_embedding_prompt_tokens": query_usage.get(query["id"]),
            "query_embedding_client_seconds": None,
            "retrieval_seconds": None,
            "generation_wall_seconds": None,
            "question_end_to_end_seconds": None,
        }
        rows.append(row)
    return rows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="musique", choices=("musique", "hotpotqa", "sample"))
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--labels", type=Path, help="Separate labels file; labels are read only after retrieval/generation")
    parser.add_argument("--limit", type=int, default=1, help="Small smoke size; maximum 20 questions")
    parser.add_argument("--generation-model", default="qwen2.5:3b")
    parser.add_argument("--embedding-model", default="bge-m3:latest")
    parser.add_argument("--base-url", default=OLLAMA_BASE_URL)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--storage-dir", type=Path, default=DEFAULT_STORAGE)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--embedding-batch-size", type=int, default=1)
    return parser.parse_args(argv)


def run(args):
    if not 1 <= args.limit <= 20:
        raise ValueError("--limit must be between 1 and 20 for this runner")
    if args.top_k < 1 or args.max_new_tokens < 1 or args.num_ctx < 1 or args.embedding_batch_size != 1:
        raise ValueError("top-k, max-new-tokens and num-ctx must be positive; batch size must be 1 for per-passage usage")
    raw_corpus = read_json(args.corpus)
    raw_queries = read_json(args.queries)
    labels_path = args.labels
    raw_labels = read_json(labels_path) if labels_path and labels_path.exists() else None
    corpus, queries, labels = normalize_inputs(raw_corpus, raw_queries, raw_labels)
    queries = queries[:args.limit]
    labels = labels[:args.limit]
    corpus_by_text = {item["title"] + "\n" + item["text"]: item for item in corpus}
    corpus_by_id = {item["id"]: item for item in corpus}
    question_text_to_id = {query["question"]: query["id"] for query in queries}
    corpus_fingerprint = sha256_bytes(json_bytes(corpus))
    query_fingerprint = sha256_bytes(json_bytes(queries))
    labels_fingerprint = sha256_bytes(json_bytes(labels))
    model_generation = model_info(args.generation_model, args.base_url)
    model_embedding = model_info(args.embedding_model, args.base_url)
    run_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    output = args.results_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    storage = args.storage_dir.resolve()
    storage.mkdir(parents=True, exist_ok=True)
    hf_cache = storage / ".huggingface-cache"
    hf_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(hf_cache))
    results_path = output / f"hipporag2-{args.dataset}-{run_id}.jsonl"
    metrics_path = results_path.with_suffix(".metrics.json")
    manifest_path = results_path.with_suffix(".manifest.json")
    generation_options = {"temperature": args.temperature, "seed": args.seed,
                          "num_predict": args.max_new_tokens, "max_new_tokens": args.max_new_tokens,
                          "num_ctx": args.num_ctx,
                          "response_format": {"type": "json_object"}}
    top_k = args.top_k
    local_alias = windows_safe_model_label(args.generation_model)
    embedding_alias = windows_safe_model_label(args.embedding_model)
    model_identity = sha256_bytes(json_bytes({"generation": model_generation["digest"],
                                               "embedding": model_embedding["digest"],
                                               "upstream": "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff"}))
    manifest = {
        "schema_version": 1, "run_id": run_id, "dataset": args.dataset,
        "status": "initializing", "created_at": timestamp,
        "runner": RUNNER_VERSION, "source": git_snapshot(),
        "inputs": {"corpus_path": str(args.corpus), "corpus_sha256": sha256_file(args.corpus),
                   "corpus_fingerprint": corpus_fingerprint,
                   "queries_path": str(args.queries), "queries_sha256": sha256_file(args.queries),
                   "queries_fingerprint": query_fingerprint,
                   "labels_path": str(args.labels) if args.labels else None,
                   "labels_sha256": sha256_file(args.labels) if args.labels else labels_fingerprint},
        "expected_question_ids": [query["id"] for query in queries],
        "generation": {"model": model_generation, "endpoint": args.base_url,
                       "options": generation_options},
        "embedding": {"model": model_embedding, "endpoint": args.base_url,
                      "batch_size": args.embedding_batch_size},
        "retrieval": {"top_k": args.top_k, "reader_context_top_k": args.top_k},
        "upstream": {"repository": "OSU-NLP-Group/HippoRAG",
                     "commit": "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff",
                     "package": "hipporag==2.0.0a5"},
        "storage_dir": str(storage), "results_file": results_path.name,
        "metrics_file": metrics_path.name,
    }
    write_json_atomic(manifest_path, manifest)
    events, event_lock = [], threading.Lock()
    HippoRAG, CacheOpenAI, OpenAIEmbeddingModel, BaseConfig = load_hipporag_classes()
    config = BaseConfig(
        llm_name=local_alias,
        llm_base_url=args.base_url,
        embedding_model_name=embedding_alias,
        embedding_provider="openai",
        embedding_base_url=args.base_url,
        embedding_batch_size=args.embedding_batch_size,
        response_format={"type": "json_object"},
        temperature=args.temperature,
        seed=args.seed,
        max_new_tokens=args.max_new_tokens,
        retrieval_top_k=max(args.top_k, 200),
        qa_top_k=args.top_k,
        dataset=args.dataset,
        save_dir=str(storage),
        max_retry_attempts=1,
    )
    llm = CacheOpenAI.from_experiment_config(config)
    llm.request_model_name = args.generation_model
    llm.llm_config.generate_params["model"] = args.generation_model
    llm.llm_config.generate_params["extra_body"] = {"options": {"num_ctx": args.num_ctx}}
    embedding = OpenAIEmbeddingModel(global_config=config)
    embedding.request_model_name = args.embedding_model
    embedding.embedding_config.embedding_model_name = args.embedding_model
    rag = None
    try:
        rag = HippoRAG(global_config=config, extraction_llm=llm, qa_llm=llm,
                       embedding_model=embedding, index_identity=f"ollama:{model_identity}")
        local = instrument_models(rag, corpus, question_text_to_id, events, event_lock)
        before = {
            "passages": set(rag.chunk_embedding_store.get_all_ids()),
            "entities": set(rag.entity_embedding_store.get_all_ids()),
            "facts": set(rag.fact_embedding_store.get_all_ids()),
        }
        docs = [item["title"] + "\n" + item["text"] for item in corpus]
        start = time.perf_counter()
        rag.index(docs)
        index_seconds = time.perf_counter() - start
        cache_counts = collect_cache_counts(rag, before)
        solutions = []
        raw_answers = []
        generation_metadata = []
        query_usage = {}
        retrieval_seconds = {}
        for query in queries:
            started = time.perf_counter()
            with current_question(local, query["id"]):
                retrieved = rag.retrieve([query["question"]])
            retrieval_seconds[query["id"]] = time.perf_counter() - started
            solution = retrieved[0]
            with current_question(local, query["id"]):
                qa_solutions, raw, metadata = rag.qa([solution])
            solutions.extend(qa_solutions)
            raw_answers.extend(raw)
            generation_metadata.extend(metadata)
            query_usage[query["id"]] = sum(
                event["usage"].get("prompt_tokens", 0)
                for event in events if event["kind"] == "embedding"
                and event.get("stage") == "graph_retrieval"
                and any(item.get("question_id") == query["id"] for item in event.get("items", []))
            ) or None
        actual_context = runtime_context_length(args.generation_model, args.base_url)
        if actual_context is not None and actual_context != args.num_ctx:
            raise RuntimeError(f"Ollama runtime context is {actual_context}, expected {args.num_ctx}")
        manifest["generation"]["runtime_context_length"] = actual_context
        rows = build_rows(run_id, args.dataset, queries, solutions,
                          raw_answers, generation_metadata, corpus_by_text,
                          query_usage, model_embedding, model_generation, top_k,
                          generation_options, corpus_fingerprint)
        for row in rows:
            row["retrieval_seconds"] = retrieval_seconds[row["question_id"]]
        write_jsonl_atomic(results_path, rows)
        results_hash = sha256_file(results_path)
        manifest["results_sha256"] = results_hash
        manifest["index"] = {"build_seconds": round(index_seconds, 6), "cache": cache_counts,
                              "usage": summarize_usage(events, corpus)}
        manifest["usage_events"] = events
        index_embedding_tokens = sum(
            event.get("usage", {}).get("prompt_tokens", 0)
            for event in events if event["kind"] == "embedding"
            and event.get("stage") == "index_embedding"
        )
        manifest["index_embedding"] = {
            "embedding_prompt_tokens": index_embedding_tokens,
            "build_seconds_this_run": None,
            "cache_read_seconds": None,
            "pipeline_wall_seconds": round(index_seconds, 6),
        }
        manifest["status"] = "completed"
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        write_json_atomic(manifest_path, manifest)
        from scripts.evaluate_dense import evaluate, read_jsonl, validate_manifest_file
        parsed_rows = read_jsonl(results_path)
        validate_manifest_file(results_path, parsed_rows, manifest)
        metrics = evaluate(parsed_rows, labels, manifest=manifest)
        write_json_atomic(metrics_path, metrics)
        print(json.dumps({"status": "verified", "run_id": run_id,
                          "questions": len(rows), "metrics": metrics,
                          "manifest": str(manifest_path), "results": str(results_path),
                          "model_generation_digest": model_generation["digest"],
                          "model_embedding_digest": model_embedding["digest"]},
                         ensure_ascii=False, indent=2))
        return results_path
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error_type"] = type(exc).__name__
        manifest["error"] = str(exc)
        manifest["usage_events"] = events
        write_json_atomic(manifest_path, manifest)
        raise
    finally:
        if rag is not None:
            rag.close()
        embedding.close()
        llm.close()


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
