"""Run a small, local dense-RAG pilot through the Ollama HTTP API."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

import numpy as np
import requests

try:
    from scripts.answer_parser import extract_reader_answer
except ModuleNotFoundError:  # Direct execution puts the scripts directory on sys.path.
    from answer_parser import extract_reader_answer


ROOT = Path(__file__).resolve().parents[1]
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"
GEN_MODEL = "qwen2.5:3b"
READER_PROMPT_VERSION = "hipporag2-musique-one-shot-v1"
# Adapted from OSU-NLP-Group/HippoRAG's rag_qa_musique.py (MIT).
# Keep this fixed demonstration independent of the benchmark questions and labels.
READER_SYSTEM = (
    'As an advanced reading comprehension assistant, your task is to analyze text passages and '
    'corresponding questions meticulously. Your response start after "Thought: ", where you will '
    'methodically break down the reasoning process, illustrating how you arrive at conclusions. '
    'Conclude with "Answer: " to present a concise, definitive response, devoid of additional elaborations.'
)
DEMO_USER = (
    "Wikipedia Title: The Last Horse\nThe Last Horse (Spanish:El último caballo) is a 1950 Spanish "
    "comedy film directed by Edgar Neville starring Fernando Fernán Gómez.\n\n"
    "Wikipedia Title: Southampton\nThe University of Southampton, which was founded in 1862 and "
    "received its Royal Charter as a university in 1952, has over 22,000 students.\n\n"
    "Wikipedia Title: Stanton Township, Champaign County, Illinois\nStanton Township is a township "
    "in Champaign County, Illinois, USA.\n\n"
    "Wikipedia Title: Neville A. Stanton\nNeville A. Stanton is a British Professor of Human Factors "
    "and Ergonomics at the University of Southampton.\n\n"
    "Wikipedia Title: Finding Nemo\nFinding Nemo is a 2003 film directed by Andrew Stanton.\n\n"
    "Question: When was Neville A. Stanton's employer founded?\nThought:"
)
DEMO_ASSISTANT = (
    "The employer of Neville A. Stanton is University of Southampton. The University of Southampton "
    "was founded in 1862. So the answer is: 1862.\nAnswer: 1862."
)
PROMPT_SOURCE = (
    "https://github.com/OSU-NLP-Group/HippoRAG/blob/main/"
    "src/hipporag/prompts/templates/rag_qa_musique.py"
)
BATCH_SIZE = 32


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


def embed_corpus(session, corpus, cache_path, fingerprint, model_digest):
    ids = [row["id"] for row in corpus]
    if cache_path.exists():
        with np.load(cache_path, allow_pickle=False) as saved:
            saved_ids = saved["ids"].astype(str).tolist()
            saved_fingerprint = str(saved["fingerprint"].item())
            saved_model = str(saved["model"].item())
            saved_digest = str(saved["model_digest"].item())
            vectors = saved["vectors"]
        if (saved_ids == ids and saved_fingerprint == fingerprint and saved_model == EMBED_MODEL
                and saved_digest == model_digest):
            if vectors.ndim == 2 and vectors.shape[0] == len(corpus):
                print(f"Embeddings cache: {cache_path.relative_to(ROOT)} ({vectors.shape[0]} passages)")
                return vectors, 0.0
        print("Embeddings cache is stale; rebuilding it.")

    document_texts = [f"{row['title']}\n{row['text']}" for row in corpus]
    all_vectors = []
    started = time.perf_counter()
    for offset in range(0, len(document_texts), BATCH_SIZE):
        batch = document_texts[offset:offset + BATCH_SIZE]
        result = post_json(session, "/api/embed", {"model": EMBED_MODEL, "input": batch})
        vectors = result.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise RuntimeError(f"Ollama returned an unexpected embedding batch at offset {offset}")
        all_vectors.extend(vectors)
        done = min(offset + len(batch), len(document_texts))
        print(f"Embedded passages: {done}/{len(document_texts)}", end="\r", flush=True)
    elapsed = time.perf_counter() - started
    matrix = np.asarray(all_vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != len(corpus):
        raise RuntimeError("Ollama returned an invalid corpus embedding matrix")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".npz.part")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, ids=np.asarray(ids), vectors=matrix,
                            fingerprint=np.asarray(fingerprint), model=np.asarray(EMBED_MODEL),
                            model_digest=np.asarray(model_digest))
    temporary.replace(cache_path)
    print(f"Embedded passages: {len(corpus)}/{len(corpus)}")
    return matrix, elapsed


def build_reader_messages(question, passages):
    context = "\n\n".join(
        f"Wikipedia Title: {row['title']}\n{row['text']}"
        for row in passages
    )
    return [
        {"role": "system", "content": READER_SYSTEM},
        {"role": "user", "content": DEMO_USER},
        {"role": "assistant", "content": DEMO_ASSISTANT},
        {"role": "user", "content": f"{context}\n\nQuestion: {question}\nThought:"},
    ]


def run(dataset="musique", limit=10, top_n=5, generation_model=GEN_MODEL):
    data_dir = ROOT / "data" / "processed" / dataset
    queries = read_json(data_dir / "queries.json")
    corpus = read_json(data_dir / "corpus.json")
    if not 1 <= limit <= 20:
        raise ValueError("Pilot limit must be between 1 and 20; larger runs need a reviewed protocol")
    queries = queries[:limit]
    planned_question_ids = [query["id"] for query in queries]
    fingerprint = corpus_fingerprint(corpus)
    cache_path = ROOT / "indexes" / "dense" / f"{dataset}-{EMBED_MODEL}.npz"
    session = requests.Session()
    embedding_info = model_info(session, EMBED_MODEL)
    generation_info = model_info(session, generation_model)
    print(f"Dataset: {dataset}; questions: {len(queries)}; corpus passages: {len(corpus)}")
    print(f"Embedding model: {embedding_info['name']} ({embedding_info['digest']})")
    print(f"Generator: {generation_info['name']} ({generation_info['digest']}); "
          f"prompt: {READER_PROMPT_VERSION}; top-k: {top_n}")
    document_vectors, embedding_seconds = embed_corpus(
        session, corpus, cache_path, fingerprint, embedding_info["digest"]
    )

    run_id = str(uuid.uuid4())
    output_dir = ROOT / "results" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"dense-{dataset}-{run_id}.jsonl"
    temporary = output_path.with_suffix(".jsonl.part")
    started_run = datetime.now(timezone.utc).isoformat()
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        for position, query in enumerate(queries, start=1):
            query_result = post_json(session, "/api/embed", {
                "model": EMBED_MODEL, "input": query["question"]
            })
            query_vectors = query_result.get("embeddings")
            if not isinstance(query_vectors, list) or len(query_vectors) != 1:
                raise RuntimeError(f"Ollama returned an invalid query embedding for {query['id']}")
            ranked = top_k(query_vectors[0], document_vectors, top_n)
            passages = [corpus[index] for index, _score in ranked]
            messages = build_reader_messages(query["question"], passages)
            prompt_sha256 = hashlib.sha256(
                json.dumps(messages, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            generation = post_json(session, "/api/chat", {
                "model": generation_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 256, "num_ctx": 4096},
            })
            raw_answer = generation.get("message", {}).get("content", "")
            answer, answer_status = extract_reader_answer(raw_answer)
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
                "generation_options": {"temperature": 0, "num_predict": 256, "num_ctx": 4096},
                "reader_prompt_source": PROMPT_SOURCE,
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
                "generation_seconds": generation.get("total_duration", 0) / 1_000_000_000,
                "generation_tokens_per_second": (
                    generation["eval_count"] * 1_000_000_000 / generation["eval_duration"]
                    if generation.get("eval_count") and generation.get("eval_duration") else None
                ),
                "done_reason": generation.get("done_reason"),
            }
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            print(f"[{position}/{len(queries)}] {query['id']}: {row['answer']}")
    temporary.replace(output_path)
    print(f"Corpus embedding seconds: {embedding_seconds:.2f}")
    print(f"Run ID: {run_id}")
    print(f"Results: {output_path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("musique", "hotpotqa"), default="musique")
    parser.add_argument("--limit", type=int, default=10,
                        help="number of initial fixed-ID questions (1-20)")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--generation-model", default=GEN_MODEL,
                        help=f"installed Ollama generation model (default: {GEN_MODEL})")
    args = parser.parse_args()
    try:
        run(args.dataset, args.limit, args.top_k, args.generation_model)
    except (OSError, requests.RequestException, ValueError, RuntimeError, KeyError) as exc:
        print(f"Dense RAG pilot failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
