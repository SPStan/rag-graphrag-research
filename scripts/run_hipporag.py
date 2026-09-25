"""Run a small or full HippoRAG 2 experiment with local OpenAI-compatible models."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib import metadata as importlib_metadata
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
from string import Template

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "results" / "raw"
DEFAULT_STORAGE = ROOT / "storage" / "hipporag2"
OLLAMA_BASE_URL = "http://localhost:11434/v1"
RUNNER_VERSION = "hipporag2-local-runner-v3"
PROMPT_VERSION = "hipporag2-musique-one-shot-v6"
UPSTREAM_READER_PROMPT_VERSION = "hipporag2-upstream-reader-v1"
PROMPT_SOURCE_COMMIT = "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff"
PROMPT_SOURCE_PATH = "src/hipporag/prompts/templates/rag_qa_musique.py"
PROMPT_SOURCE = (
    f"https://github.com/OSU-NLP-Group/HippoRAG/blob/{PROMPT_SOURCE_COMMIT}/"
    f"{PROMPT_SOURCE_PATH}"
)
LOG = logging.getLogger("run_hipporag")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def reader_template_metadata():
    try:
        from scripts.vendor.hipporag2_musique_template import prompt_template
    except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
        from vendor.hipporag2_musique_template import prompt_template

    messages = [{"role": item["role"], "content": item["content"]}
                for item in prompt_template]
    digest_payload = json.dumps(
        [item["content"] for item in messages[:3]], ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return messages, sha256_bytes(digest_payload)


def build_shared_reader_messages(question, passages):
    template, _ = reader_template_metadata()
    context = "\n\n".join(
        f"Wikipedia Title: {row['title']}\n{row['text']}" for row in passages
    )
    user_prompt = f"{context}\n\nQuestion: {question}\nThought: "
    return [*template[:3], {"role": "user", "content": user_prompt}]


def install_shared_reader_template(rag):
    template, digest = reader_template_metadata()
    rag.prompt_template_manager.templates["rag_qa_musique"] = [
        {"role": item["role"], "content": Template(item["content"])}
        for item in template
    ]
    return digest


def run_shared_reader(original_qa, qa_llm, solutions):
    """Use the common text reader and the same answer parser as Dense RAG."""
    config = getattr(qa_llm, "global_config", None)
    previous_format = getattr(config, "response_format", None) if config else None
    previous_infer = qa_llm.infer

    def uncached_infer(*args, **kwargs):
        kwargs["_bypass_cache"] = True
        return previous_infer(*args, **kwargs)

    if config is not None:
        config.response_format = None
    qa_llm.infer = uncached_infer
    try:
        qa_solutions, raw_answers, metadata = original_qa(solutions)
    finally:
        qa_llm.infer = previous_infer
        if config is not None:
            config.response_format = previous_format

    from scripts.answer_parser import extract_reader_answer

    for solution, raw_answer, item_metadata in zip(qa_solutions, raw_answers, metadata):
        solution.answer, item_metadata["answer_extraction_status"] = (
            extract_reader_answer(raw_answer)
        )
    return qa_solutions, raw_answers, metadata


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


def persist_interrupted_run(manifest, manifest_path, events, lock):
    """Keep a user-stopped run distinguishable from one still initializing."""
    with lock:
        manifest["usage_events"] = list(events)
    manifest["status"] = "interrupted"
    manifest["error_type"] = "KeyboardInterrupt"
    manifest["error"] = "Run interrupted; no complete results or metrics were written."
    manifest["interrupted_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(manifest_path, manifest)


def canonical_key(title, text):
    if not isinstance(title, str) or not isinstance(text, str) or not text.strip():
        raise ValueError("Each passage needs a non-empty title and text")
    return " ".join(title.split()), " ".join(text.split())


def passage_id(title, text):
    payload = json_bytes(canonical_key(title, text)).rstrip(b"\n")
    return "sha256:" + sha256_bytes(payload)


def normalize_ner_entities(values):
    """Normalize Qwen's occasional object-shaped NER items to entity strings."""
    normalized = []
    for value in values:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, dict):
            # Common model variants wrap an entity with a type/label, or group
            # entities by category. Keep names only and ignore category labels.
            candidates = ([value["entity"]] if isinstance(value.get("entity"), str)
                          else [item for item in value.values() if isinstance(item, str)])
        else:
            raise ValueError("NER entities must be strings or supported entity objects")
        for candidate in candidates:
            candidate = candidate.strip()
            if candidate and candidate not in normalized:
                normalized.append(candidate)
    return normalized


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
    git = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]
    try:
        commit = subprocess.run([*git, "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run([*git, "status", "--porcelain"], cwd=ROOT, check=True,
                                    capture_output=True, text=True).stdout.strip())
        snapshot = {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        snapshot = {"commit": None, "dirty": None}
    source_files = (
        "scripts/run_hipporag.py", "scripts/run_dense.py",
        "scripts/evaluate_dense.py", "scripts/answer_parser.py",
        "scripts/vendor/hipporag2_musique_template.py",
        "requirements-hipporag2.txt",
    )
    snapshot["source_sha256"] = {
        name: sha256_file(ROOT / name) for name in source_files
        if (ROOT / name).is_file()
    }
    return snapshot


def ollama_api_base(base_url):
    base = base_url.rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


def install_no_truncate_embedding_api(embedding_model, base_url, model_name,
                                      post_json=None):
    """Use Ollama's native embed API so truncate=false is part of each request."""
    session = requests.Session() if post_json is None else None
    if session is not None:
        session.trust_env = False
    post_json = post_json or session.post
    embedding_model._no_truncate_session = session
    endpoint = f"{ollama_api_base(base_url)}/api/embed"

    def request_embeddings(prepared_texts):
        response = post_json(
            endpoint,
            json={"model": model_name, "input": prepared_texts, "truncate": False},
            timeout=embedding_model.global_config.embedding_request_timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError:
            # Ollama can reject an otherwise small batch for one input. Split
            # only rejected multi-input batches so a single bad value is
            # isolated and recorded instead of discarding the whole index.
            if response.status_code == 400 and len(prepared_texts) > 1:
                middle = len(prepared_texts) // 2
                left, left_usage = request_embeddings(prepared_texts[:middle])
                right, right_usage = request_embeddings(prepared_texts[middle:])
                usage = {
                    "prompt_tokens": left_usage["prompt_tokens"] + right_usage["prompt_tokens"],
                    "total_tokens": left_usage["total_tokens"] + right_usage["total_tokens"],
                    "total_duration_ns": (left_usage.get("total_duration_ns") or 0)
                    + (right_usage.get("total_duration_ns") or 0),
                    "load_duration_ns": (left_usage.get("load_duration_ns") or 0)
                    + (right_usage.get("load_duration_ns") or 0),
                    "truncate": False,
                }
                return left + right, usage
            raise
        payload = response.json()
        vectors = payload.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(prepared_texts):
            raise RuntimeError("Ollama returned an incomplete embedding response")
        token_count = payload.get("prompt_eval_count")
        if not isinstance(token_count, int) or isinstance(token_count, bool) or token_count < 0:
            raise RuntimeError("Ollama embedding response omitted valid prompt_eval_count")
        usage = {
            "prompt_tokens": token_count,
            "total_tokens": token_count,
            "total_duration_ns": payload.get("total_duration"),
            "load_duration_ns": payload.get("load_duration"),
            "truncate": False,
        }
        return vectors, usage

    def encode(texts):
        scalar_input = isinstance(texts, str)
        if scalar_input:
            texts = [texts]
        if not texts or any(not isinstance(text, str) for text in texts):
            raise ValueError("Embedding input must be a non-empty list of strings")
        prepared_texts = [text.replace("\n", " ") or " " for text in texts]
        embedding_model.last_usage = None
        vectors, usage = request_embeddings(prepared_texts)
        matrix = np.asarray(vectors, dtype=np.float32)
        if (matrix.ndim != 2 or matrix.shape[0] != len(texts)
                or not np.all(np.isfinite(matrix))
                or np.any(np.linalg.norm(matrix, axis=1) <= 0)):
            raise RuntimeError("Ollama returned invalid, non-finite, or zero embeddings")
        embedding_model.last_usage = usage
        # HippoRAG batch_encode normalizes rows along axis 1, including the
        # one-query case. Preserve a vector row for list inputs of length one.
        return matrix[0] if scalar_input else matrix

    embedding_model.encode = encode
    return endpoint


def validate_pinned_dataset(dataset, corpus_path, queries, corpus, labels_path=None):
    if dataset not in ("musique", "hotpotqa"):
        return None
    try:
        from scripts.run_dense import validate_processed_data
    except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
        from run_dense import validate_processed_data
    labels_path = Path(labels_path) if labels_path else Path(corpus_path).parent / "labels.json"
    if not labels_path.is_file():
        raise ValueError(f"Pinned dataset labels are required: {labels_path}")
    return validate_processed_data(
        dataset, Path(corpus_path).parent, queries, corpus, labels_path)


def runtime_metadata(base_url):
    response = requests.get(f"{ollama_api_base(base_url)}/api/version", timeout=30)
    response.raise_for_status()
    packages = {}
    for name in ("hipporag", "openai", "numpy", "requests"):
        try:
            packages[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": platform.python_version(), "platform": platform.platform(),
            "ollama": response.json().get("version"), "packages": packages}


def _append_event(events, lock, event):
    with lock:
        events.append(event)


def record_openie_failure(failures, lock, passage_id, exc, stage):
    """Record a skipped OpenIE step without retaining passage text."""
    failure = {"stage": stage, "passage_id": passage_id,
               "error_type": type(exc).__name__,
               "error": str(exc)[:500]}
    with lock:
        failures.append(failure)
    return failure


def instrument_models(rag, corpus, query_text_to_id, events, lock,
                     embedding_max_inputs_per_second=18.0,
                     embedding_request_batch_size=4):
    """Record SDK usage and cache state without storing any raw prompts or texts."""
    local = threading.local()
    openie_failures = []
    openie_failures_lock = threading.Lock()
    local.openie_failures = openie_failures
    passage_id_by_text = {item["title"] + "\n" + item["text"]: item["id"] for item in corpus}
    query_id_by_embedding = {text: qid for text, qid in query_text_to_id.items()}

    llm = rag.qa_llm
    original_infer = llm.infer

    def tracked_infer(*args, **kwargs):
        messages = kwargs.get("messages", args[0] if args else None)
        if messages is None:
            raise ValueError("Missing messages for a tracked HippoRAG chat call")
        serialized = json.dumps(messages, ensure_ascii=False, sort_keys=True, default=str)
        bypass_cache = kwargs.pop("_bypass_cache", False)
        started = time.perf_counter()
        try:
            if bypass_cache:
                # The upstream decorator caches malformed JSON too. A targeted
                # retry must go through its wrapped API method, bypassing SQLite.
                response, metadata = original_infer.__func__.__wrapped__(
                    llm, *args, **kwargs)
                cache_hit = False
            else:
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
                 "usage": metadata, "cache_hit": bool(cache_hit),
                 "client_seconds": time.perf_counter() - started}
        _append_event(events, lock, event)
        return response, metadata, cache_hit

    llm.infer = tracked_infer

    embedding_model = rag.embedding_model
    original_encode = embedding_model.encode
    embedding_gate = threading.Lock()
    last_embedding_started = [0.0]

    def tracked_encode(texts):
        if isinstance(texts, str):
            texts = [texts]
        results = []
        total_usage = {"prompt_tokens": 0, "total_tokens": 0}
        for offset in range(0, len(texts), embedding_request_batch_size):
            batch = texts[offset:offset + embedding_request_batch_size]
            items = [{"input_sha256": sha256_bytes(text.encode("utf-8")),
                      "input_chars": len(text),
                      "input_type": "passage" if text in passage_id_by_text else (
                          "query" if text in query_id_by_embedding else "entity_or_fact"),
                      "passage_id": passage_id_by_text.get(text),
                      "question_id": query_id_by_embedding.get(text),
                      "prepared_input_sha256": sha256_bytes(
                          (text.replace("\n", " ") or " ").encode("utf-8")),
                      "preprocessing": "replace-newlines-with-space-v1"}
                     for text in batch]
            minimum_batch_interval = len(batch) / embedding_max_inputs_per_second
            with embedding_gate:
                wait = minimum_batch_interval - (
                    time.perf_counter() - last_embedding_started[0]
                )
                if last_embedding_started[0] and wait > 0:
                    time.sleep(wait)
                last_embedding_started[0] = time.perf_counter()
                try:
                    started = time.perf_counter()
                    result = original_encode(batch)
                except Exception:
                    usage = dict(embedding_model.last_usage or {})
                    event = {"kind": "embedding", "stage": getattr(local, "stage", "unknown"),
                             "items": items, "batch_size": len(batch), "usage_unknown": True,
                             "error_type": "embedding_request_failed"}
                    if isinstance(usage.get("prompt_tokens"), int):
                        event["usage"] = usage
                        event.pop("usage_unknown", None)
                    _append_event(events, lock, event)
                    raise
                usage = dict(embedding_model.last_usage or {})
                if (not isinstance(usage.get("prompt_tokens"), int)
                        or isinstance(usage.get("prompt_tokens"), bool)
                        or usage["prompt_tokens"] < 0):
                    raise RuntimeError("HippoRAG embedding response did not provide prompt token usage")
                event = {"kind": "embedding", "stage": getattr(local, "stage", "unknown"),
                         "items": items, "batch_size": len(batch), "usage": usage,
                         "client_seconds": time.perf_counter() - started}
                _append_event(events, lock, event)
                total_usage["prompt_tokens"] += usage["prompt_tokens"]
                total_usage["total_tokens"] += usage.get("total_tokens", usage["prompt_tokens"])
                results.append(result)
        embedding_model.last_usage = total_usage
        return np.concatenate(results, axis=0) if len(results) > 1 else results[0]

    embedding_model.encode = tracked_encode

    original_ner = rag.openie.ner
    def tracked_ner(chunk_key, passage):
        local.stage = "openie_ner"
        local.passage_id = passage_id_by_text.get(passage)
        try:
            result = original_ner(chunk_key, passage)
            if not result.metadata.get("error"):
                try:
                    entities = normalize_ner_entities(result.unique_entities)
                except ValueError:
                    # An otherwise cache-valid response can still contain an
                    # unsupported item; retry it once below without the cache.
                    pass
                else:
                    if entities == result.unique_entities:
                        return result
                    metadata = dict(result.metadata)
                    metadata["ner_object_items_normalized"] = True
                    return type(result)(chunk_id=chunk_key, response=result.response,
                                        unique_entities=entities, metadata=metadata)

            # Retry malformed/cut-off NER once without consulting the upstream
            # response cache. Successful cached passages remain untouched.
            from hipporag.prompts import PromptTemplateManager
            from hipporag.utils.llm_utils import fix_broken_generated_json
            from hipporag.information_extraction.openie_openai import _extract_ner_from_response

            messages = PromptTemplateManager(role_mapping={
                "system": "system", "user": "user", "assistant": "assistant"
            }).render(name="ner", passage=passage)
            kwargs = {"max_new_tokens": rag.openie.ner_max_tokens,
                      "_bypass_cache": True}
            response_format = getattr(getattr(rag.qa_llm, "global_config", None),
                                      "response_format", None)
            if response_format is not None:
                kwargs["response_format"] = response_format
            try:
                response, metadata, _ = rag.qa_llm.infer(messages=messages, **kwargs)
                parsed = (fix_broken_generated_json(response)
                          if metadata.get("finish_reason") == "length" else response)
                entities = normalize_ner_entities(_extract_ner_from_response(parsed))
            except Exception as exc:
                record_openie_failure(openie_failures, openie_failures_lock,
                                      local.passage_id, exc, "openie_ner")
                return type(result)(chunk_id=chunk_key, response="",
                                    unique_entities=[],
                                    metadata={"extraction_failed": True,
                                              "retry_without_cache": True})
            metadata = dict(metadata)
            metadata["retry_without_cache"] = True
            metadata["ner_object_items_normalized"] = True
            return type(result)(chunk_id=chunk_key, response=response,
                                unique_entities=entities, metadata=metadata)
        except Exception:
            raise
        finally:
            local.stage = "index_embedding"
            local.passage_id = None
    rag.openie.ner = tracked_ner

    original_triples = rag.openie.triple_extraction
    def tracked_triples(chunk_key, passage, named_entities):
        local.stage = "openie_triples"
        local.passage_id = passage_id_by_text.get(passage)
        try:
            result = original_triples(chunk_key, passage, named_entities)
            if not result.metadata.get("error"):
                return result

            # As with NER, a malformed cached answer must not poison retries.
            from hipporag.prompts import PromptTemplateManager
            from hipporag.utils.llm_utils import fix_broken_generated_json, filter_invalid_triples
            from hipporag.information_extraction.openie_openai import _extract_json_list_field

            messages = PromptTemplateManager(role_mapping={
                "system": "system", "user": "user", "assistant": "assistant"
            }).render(name="triple_extraction", passage=passage,
                      named_entity_json=json.dumps({"named_entities": named_entities}))
            kwargs = {"max_new_tokens": rag.openie.triple_max_tokens,
                      "_bypass_cache": True}
            response_format = getattr(getattr(rag.qa_llm, "global_config", None),
                                      "response_format", None)
            if response_format is not None:
                kwargs["response_format"] = response_format
            try:
                response, metadata, _ = rag.qa_llm.infer(messages=messages, **kwargs)
                parsed = (fix_broken_generated_json(response)
                          if metadata.get("finish_reason") == "length" else response)
                triples = filter_invalid_triples(
                    triples=_extract_json_list_field(parsed, "triples"))
            except Exception as exc:
                # Ollama may abort one fragment on token repetition. Keep a
                # partial graph, and disclose the omitted extraction explicitly.
                record_openie_failure(openie_failures, openie_failures_lock,
                                      local.passage_id, exc, "openie_triples")
                return type(result)(chunk_id=chunk_key, response="",
                                    metadata={"extraction_failed": True,
                                              "retry_without_cache": True},
                                    triples=[])
            metadata = dict(metadata)
            metadata["retry_without_cache"] = True
            return type(result)(chunk_id=chunk_key, response=response,
                                metadata=metadata, triples=triples)
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
            if rag.global_config.dataset == "musique":
                return run_shared_reader(original_qa, rag.qa_llm, solutions)
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
                               "passage_embedding_usage_attributed": True,
                               "embedding_batches": 0,
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
                    row["embedding_batches"] += 1
                    if event.get("batch_size", len(event.get("items", []))) == 1:
                        row["embedding_calls"] += 1
                        row["passage_embedding_tokens"] += count or 0
                    else:
                        row["passage_embedding_tokens"] = None
                        row["passage_embedding_usage_attributed"] = False
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
               model_generation, top_k, generation_options, index_fingerprint,
               reader_info, query_embedding_seconds, retrieval_seconds,
               generation_seconds, question_seconds):
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
            "answer_extraction_status": metadata.get(
                "answer_extraction_status",
                "ok" if "Answer:" in raw else "missing_answer_marker"),
            "done": True, "done_reason": finish_reason,
            "retrieved": docs,
            "top_k": top_k,
            "generation_model": model_generation,
            "embedding_model": model_embedding,
            "reader_prompt_version": reader_info["version"],
            "reader_prompt_source": reader_info.get("source"),
            "reader_prompt_source_commit": reader_info.get("source_commit"),
            "reader_prompt_sha256": hashlib.sha256(json.dumps(
                build_shared_reader_messages(query["question"], docs),
                ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest() if dataset == "musique" else None,
            "generation_options": generation_options,
            "index_fingerprint": index_fingerprint,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "query_embedding_prompt_tokens": query_usage.get(query["id"]),
            "query_embedding_client_seconds": query_embedding_seconds.get(query["id"]),
            "retrieval_seconds": retrieval_seconds.get(query["id"]),
            "generation_wall_seconds": generation_seconds.get(query["id"]),
            "question_end_to_end_seconds": question_seconds.get(query["id"]),
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
    parser.add_argument("--embedding-request-batch-size", type=int, default=4)
    parser.add_argument("--embedding-max-inputs-per-second", type=float, default=18.0)
    return parser.parse_args(argv)


def run(args):
    if not 1 <= args.limit <= 20:
        raise ValueError("--limit must be between 1 and 20 for this runner")
    if (args.top_k < 1 or args.max_new_tokens < 1 or args.num_ctx < 1
            or not 1 <= args.embedding_batch_size <= 128
            or not 1 <= args.embedding_request_batch_size <= 18
            or args.embedding_max_inputs_per_second <= 0):
        raise ValueError("top-k, max-new-tokens and num-ctx must be positive; embedding batch sizes must be 1-128 and 1-18")
    raw_corpus = read_json(args.corpus)
    raw_queries = read_json(args.queries)
    labels_path = args.labels
    raw_labels = read_json(labels_path) if labels_path and labels_path.exists() else None
    corpus, queries, labels = normalize_inputs(raw_corpus, raw_queries, raw_labels)
    data_provenance = validate_pinned_dataset(
        args.dataset, args.corpus, queries, corpus, args.labels)
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
    runtime = runtime_metadata(args.base_url)
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
                          "num_ctx": args.num_ctx}
    if args.dataset != "musique":
        generation_options["response_format"] = {"type": "json_object"}
    if args.dataset == "musique":
        _reader_template, reader_template_sha256 = reader_template_metadata()
        reader_info = {"version": PROMPT_VERSION, "source": PROMPT_SOURCE,
                       "source_commit": PROMPT_SOURCE_COMMIT,
                       "source_path": PROMPT_SOURCE_PATH,
                       "template_sha256": reader_template_sha256}
    else:
        reader_info = {"version": UPSTREAM_READER_PROMPT_VERSION,
                       "source": "HippoRAG upstream default reader",
                       "source_commit": "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff",
                       "source_path": None, "template_sha256": None}
    top_k = args.top_k
    local_alias = windows_safe_model_label(args.generation_model)
    embedding_alias = windows_safe_model_label(args.embedding_model)
    embedding_pipeline = {
        "endpoint": "/api/embed", "truncate": False,
        "text_preprocessing": "replace-newlines-with-space-v1",
        "vector_validation": "finite-nonzero-row-v1",
    }
    model_identity = sha256_bytes(json_bytes({
        "generation": model_generation["digest"],
        "embedding": model_embedding["digest"],
        "embedding_pipeline": embedding_pipeline,
        "upstream": "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff",
    }))
    index_storage = storage / f"index-{model_identity[:12]}"
    index_storage.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1, "run_id": run_id, "dataset": args.dataset,
        "status": "initializing", "created_at": timestamp,
        "runner": RUNNER_VERSION, "source": git_snapshot(), "runtime": runtime,
        "inputs": {"corpus_path": str(args.corpus), "corpus_sha256": sha256_file(args.corpus),
                   "corpus_fingerprint": corpus_fingerprint,
                   "queries_path": str(args.queries), "queries_sha256": sha256_file(args.queries),
                   "queries_fingerprint": query_fingerprint,
                   "labels_path": str(args.labels) if args.labels else None,
                   "labels_sha256": sha256_file(args.labels) if args.labels else labels_fingerprint,
                   "pinned_dataset_provenance": data_provenance},
        "expected_question_ids": [query["id"] for query in queries],
        "generation": {"model": model_generation, "endpoint": args.base_url,
                       "reader_prompt_version": reader_info["version"],
                       "reader_prompt_source": reader_info["source"],
                       "reader_prompt_source_commit": reader_info["source_commit"],
                       "reader_prompt_source_path": reader_info["source_path"],
                       "reader_template_sha256": reader_info["template_sha256"],
                       "options": generation_options},
        "embedding": {"model": model_embedding, "endpoint": args.base_url,
                      "batch_size": 1,
                      "hipporag_outer_batch_size": args.embedding_batch_size,
                      "max_inputs_per_second": args.embedding_max_inputs_per_second,
                      "request_batch_size": args.embedding_request_batch_size,
                      **embedding_pipeline},
        "retrieval": {"top_k": args.top_k, "reader_context_top_k": args.top_k},
        "upstream": {"repository": "OSU-NLP-Group/HippoRAG",
                     "commit": "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff",
                     "package": "hipporag==2.0.0a5"},
        "storage_dir": str(index_storage), "storage_root": str(storage),
        "results_file": results_path.name,
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
        save_dir=str(index_storage),
        max_retry_attempts=1,
    )
    llm = CacheOpenAI.from_experiment_config(config)
    llm_cache_dir = storage / "llm_cache"
    llm_cache_dir.mkdir(parents=True, exist_ok=True)
    llm.cache_file_name = str(llm_cache_dir / f"{local_alias}_cache.sqlite")
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
        manifest["embedding"]["native_endpoint"] = install_no_truncate_embedding_api(
            embedding, args.base_url, args.embedding_model)
        write_json_atomic(manifest_path, manifest)
        if args.dataset == "musique":
            install_shared_reader_template(rag)
        # A previous interrupted indexing attempt may have persisted passage
        # vectors before producing a graph. Reuse those vectors and explicitly
        # rebuild the missing graph from cached OpenIE outputs.
        if (not rag._graph_state_available
                and rag.chunk_embedding_store.get_all_ids()):
            config.force_index_from_scratch = True
            manifest["recovery"] = "rebuild_missing_graph_reusing_persisted_passage_embeddings"
            write_json_atomic(manifest_path, manifest)
        local = instrument_models(rag, corpus, question_text_to_id, events, event_lock,
                                  args.embedding_max_inputs_per_second,
                                  args.embedding_request_batch_size)
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
        query_embedding_seconds = {}
        retrieval_seconds = {}
        generation_seconds = {}
        question_seconds = {}
        for query in queries:
            question_started = time.perf_counter()
            retrieval_started = time.perf_counter()
            with current_question(local, query["id"]):
                retrieved = rag.retrieve([query["question"]])
            retrieval_seconds[query["id"]] = time.perf_counter() - retrieval_started
            solution = retrieved[0]
            generation_started = time.perf_counter()
            with current_question(local, query["id"]):
                qa_solutions, raw, metadata = rag.qa([solution])
            generation_seconds[query["id"]] = time.perf_counter() - generation_started
            question_seconds[query["id"]] = time.perf_counter() - question_started
            solutions.extend(qa_solutions)
            raw_answers.extend(raw)
            generation_metadata.extend(metadata)
            query_usage[query["id"]] = sum(
                event["usage"].get("prompt_tokens", 0)
                for event in events if event["kind"] == "embedding"
                and event.get("stage") == "graph_retrieval"
                and event.get("batch_size") == 1
                and any(item.get("question_id") == query["id"] for item in event.get("items", []))
            ) or None
            query_embedding_seconds[query["id"]] = sum(
                event.get("client_seconds", 0.0)
                for event in events if event["kind"] == "embedding"
                and event.get("stage") == "graph_retrieval"
                and event.get("batch_size") == 1
                and any(item.get("question_id") == query["id"] for item in event.get("items", []))
            ) or None
        actual_context = runtime_context_length(args.generation_model, args.base_url)
        if actual_context is not None and actual_context != args.num_ctx:
            raise RuntimeError(f"Ollama runtime context is {actual_context}, expected {args.num_ctx}")
        manifest["generation"]["runtime_context_length"] = actual_context
        rows = build_rows(run_id, args.dataset, queries, solutions,
                          raw_answers, generation_metadata, corpus_by_text,
                          query_usage, model_embedding, model_generation, top_k,
                          generation_options, corpus_fingerprint, reader_info,
                          query_embedding_seconds, retrieval_seconds,
                          generation_seconds, question_seconds)
        write_jsonl_atomic(results_path, rows)
        results_hash = sha256_file(results_path)
        manifest["results_sha256"] = results_hash
        manifest["index"] = {"build_seconds": round(index_seconds, 6), "cache": cache_counts,
                              "usage": summarize_usage(events, corpus)}
        manifest["index"]["openie_extraction_failures"] = sorted(
            local.openie_failures, key=lambda item: item.get("passage_id") or "")
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
    except KeyboardInterrupt:
        persist_interrupted_run(manifest, manifest_path, events, event_lock)
        raise
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
        session = getattr(embedding, "_no_truncate_session", None)
        if session is not None:
            session.close()
        embedding.close()
        llm.close()


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    run(args)


if __name__ == "__main__":
    main()
