"""Build reproducible retrieval corpora and separate queries from gold labels."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.download_data import verify


def canonical_key(title, text):
    if not isinstance(title, str) or not isinstance(text, str) or not text.strip():
        raise ValueError("Passage requires title and non-empty text strings")
    return (" ".join(title.split()), " ".join(text.split()))


def passage_id(key):
    payload = json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def normalize_corpus(corpus):
    by_key = {}
    for passage in corpus:
        key = canonical_key(passage["title"], passage["text"])
        # Exact canonical duplicates are one retrieval document, not several hits.
        by_key.setdefault(key, {"id": passage_id(key), "title": key[0], "text": key[1]})
    return by_key


def supporting_keys(dataset, question):
    if dataset == "musique":
        if question.get("answerable") is False:
            raise ValueError("Unanswerable MuSiQue question is outside this protocol")
        keys = [canonical_key(p["title"], p["paragraph_text"])
                for p in question["paragraphs"] if p["is_supporting"]]
        return [(key,) for key in keys]
    if dataset != "hotpotqa":
        raise ValueError(f"Unsupported dataset: {dataset}")
    contexts = {}
    for title, sentences in question["context"]:
        if title in contexts:
            raise ValueError(f"Ambiguous context title: {title}")
        if not isinstance(sentences, list) or not all(isinstance(s, str) for s in sentences):
            raise ValueError("HotpotQA context must contain sentence strings")
        contexts[title] = sentences
    titles = set()
    for title, sentence_index in question["supporting_facts"]:
        if title not in contexts:
            raise ValueError(f"Supporting title missing from context: {title}")
        if not isinstance(sentence_index, int) or not 0 <= sentence_index < len(contexts[title]):
            raise ValueError(f"Invalid supporting sentence index: {title}")
        titles.add(title)
    # Match both title and complete passage. Never match a title alone.
    return [tuple(dict.fromkeys((canonical_key(title, "".join(contexts[title])),
                                  canonical_key(title, " ".join(contexts[title])))))
            for title in sorted(titles)]


def build_subset(dataset, questions, corpus, count=500, corpus_size=5500, seed=42):
    if count <= 0 or count > len(questions) or corpus_size <= 0:
        raise ValueError("Invalid question count or corpus size")
    by_key = normalize_corpus(corpus)
    documents = {p["id"]: p for p in by_key.values()}
    if corpus_size > len(documents):
        raise ValueError("Not enough unique corpus passages")
    id_field = "id" if dataset == "musique" else "_id"
    by_id = {}
    for question in questions:
        qid = question[id_field]
        if not isinstance(qid, str) or not qid or qid in by_id:
            raise ValueError("Missing or duplicate question ID")
        by_id[qid] = question
    rng = random.Random(seed)
    selected_ids = rng.sample(sorted(by_id), count)
    queries, labels, required = [], [], set()
    for qid in selected_ids:
        question = by_id[qid]
        if not isinstance(question["question"], str) or not question["question"].strip():
            raise ValueError(f"Empty question: {qid}")
        if not isinstance(question["answer"], str) or not question["answer"].strip():
            raise ValueError(f"Empty answer: {qid}")
        support_ids = set()
        for alternatives in supporting_keys(dataset, question):
            matches = {by_key[key]["id"] for key in alternatives if key in by_key}
            if len(matches) != 1:
                raise ValueError(f"Missing or ambiguous supporting passage for {qid}")
            support_ids.update(matches)
        if not support_ids:
            raise ValueError(f"No supporting passages: {qid}")
        required.update(support_ids)
        queries.append({"id": qid, "question": question["question"]})
        labels.append({"id": qid, "answer": question["answer"],
                       "answer_aliases": question.get("answer_aliases", []),
                       "supporting_ids": sorted(support_ids)})
    if len(required) > corpus_size:
        raise ValueError(f"Supporting passages ({len(required)}) exceed corpus size ({corpus_size})")
    distractors = rng.sample(sorted(set(documents) - required), corpus_size - len(required))
    corpus_ids = sorted(required) + distractors
    rng.shuffle(corpus_ids)  # Gold passages must not be identified by position.
    selected_corpus = [documents[pid] for pid in corpus_ids]
    manifest = {
        "schema_version": 1, "dataset": dataset, "seed": seed,
        "selection": "random.Random(seed).sample(sorted(question_ids), count)",
        "passage_identity": "sha256 of JSON [title,text] after whitespace normalization",
        "question_ids": selected_ids, "passage_ids": corpus_ids,
        "views": {name: selected_ids[:min(size, count)] for name, size in
                  (("debug10", 10), ("debug20", 20), ("baseline100", 100), ("pilot200", 200))},
    }
    stats = {"source_questions": len(questions), "source_passages": len(corpus),
             "unique_source_passages": len(documents), "canonical_duplicates_removed": len(corpus) - len(documents),
             "selected_questions": count, "selected_passages": corpus_size,
             "supporting_passages": len(required), "distractors": len(distractors)}
    return queries, labels, selected_corpus, manifest, stats


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_stable(path, payload):
    """Refuse accidental replacement of a previously fixed selection."""
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"Existing file differs; review protocol and use a new output location: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(payload)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("musique", "hotpotqa", "all"), default="all")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed")
    parser.add_argument("--ids-dir", type=Path, default=ROOT / "data/ids")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / "data/sources.lock.json").read_text(encoding="utf-8"))
    entries = {entry["name"]: entry for entry in lock["files"]}
    report = {"source_repository": lock["repository"], "source_revision": lock["revision"],
              "protocol": "s500-c5500-seed42-v1", "datasets": {}}
    datasets = ("musique", "hotpotqa") if args.dataset == "all" else (args.dataset,)
    for dataset in datasets:
        question_name, corpus_name = f"{dataset}.json", f"{dataset}_corpus.json"
        qbytes = (args.raw_dir / question_name).read_bytes()
        cbytes = (args.raw_dir / corpus_name).read_bytes()
        source_hashes = {question_name: verify(qbytes, entries[question_name]),
                         corpus_name: verify(cbytes, entries[corpus_name])}
        queries, labels, corpus, ids, stats = build_subset(dataset, json.loads(qbytes), json.loads(cbytes))
        ids.update(source_revision=lock["revision"], source_sha256=source_hashes)
        outputs = {"queries.json": json_bytes(queries), "labels.json": json_bytes(labels),
                   "corpus.json": json_bytes(corpus)}
        for name, payload in outputs.items():
            write_stable(args.output_dir / dataset / name, payload)
        manifest_bytes = json_bytes(ids)
        write_stable(args.ids_dir / f"{dataset}_s500.json", manifest_bytes)
        stats.update(source_sha256=source_hashes,
                     ids_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                     output_sha256={name: hashlib.sha256(payload).hexdigest() for name, payload in outputs.items()},
                     all_supporting_present=all(set(row["supporting_ids"]) <= set(ids["passage_ids"]) for row in labels))
        report["datasets"][dataset] = stats
        print(f"{dataset}: {stats}")
    report_name = "subsamples.json" if args.dataset == "all" else f"{args.dataset}_subsample.json"
    write_stable(args.report or ROOT / "results/data" / report_name, json_bytes(report))


if __name__ == "__main__":
    main()
