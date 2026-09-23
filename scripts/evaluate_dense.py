"""Evaluate a saved Dense RAG JSONL against labels, after generation is complete."""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import string
import sys


ROOT = Path(__file__).resolve().parents[1]
METRIC_VERSION = "hipporag2-squad-normalization-v1"
PUNCTUATION = str.maketrans("", "", string.punctuation)


def normalize_answer(text):
    text = str(text).lower().translate(PUNCTUATION)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def exact_match(prediction, reference):
    return float(normalize_answer(prediction) == normalize_answer(reference))


def token_f1(prediction, reference):
    predicted = normalize_answer(prediction).split()
    expected = normalize_answer(reference).split()
    if not predicted or not expected:
        return 0.0
    overlap = sum((Counter(predicted) & Counter(expected)).values())
    if not overlap:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 2 * precision * recall / (precision + recall)


def answer_scores(prediction, references):
    if not references:
        raise ValueError("Each label must have at least one reference answer")
    return {
        "em": max(exact_match(prediction, reference) for reference in references),
        "f1": max(token_f1(prediction, reference) for reference in references),
    }


def recall_at_k(retrieved_ids, supporting_ids, k):
    supporting = set(supporting_ids)
    if not supporting:
        raise ValueError("Each label must have at least one supporting passage")
    if not isinstance(k, int) or k <= 0:
        raise ValueError("top_k must be a positive integer")
    return len(set(retrieved_ids[:k]) & supporting) / len(supporting)


def read_jsonl(path):
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
    if not rows:
        raise ValueError("Run file is empty")
    return rows


def evaluate(rows, labels, expected_ids=None):
    run_ids = {row.get("run_id") for row in rows}
    datasets = {row.get("dataset") for row in rows}
    if len(run_ids) != 1 or None in run_ids:
        raise ValueError("Run rows must share one non-empty run_id")
    if len(datasets) != 1 or None in datasets:
        raise ValueError("Run rows must share one dataset")

    by_id = {label["id"]: label for label in labels}
    if len(by_id) != len(labels):
        raise ValueError("Duplicate label IDs")
    row_ids = [row.get("question_id") for row in rows]
    if None in row_ids or len(set(row_ids)) != len(row_ids):
        raise ValueError("Run rows contain missing or duplicate question IDs")

    embedded_expected = [row.get("planned_question_ids") for row in rows]
    if expected_ids is None:
        if any(ids is None for ids in embedded_expected):
            raise ValueError("Expected question IDs are required for legacy runs")
        if any(ids != embedded_expected[0] for ids in embedded_expected[1:]):
            raise ValueError("Run rows disagree on planned question IDs")
        expected_ids = embedded_expected[0]
    if not expected_ids or row_ids != expected_ids:
        raise ValueError("Run question IDs do not exactly match the expected ordered IDs")

    config_fields = ("top_k", "embedding_model", "generation_model",
                     "reader_prompt_version", "generation_options")
    first = rows[0]
    for field in config_fields:
        value = json.dumps(first.get(field), sort_keys=True, ensure_ascii=False)
        if any(json.dumps(row.get(field), sort_keys=True, ensure_ascii=False) != value
               for row in rows[1:]):
            raise ValueError(f"Run rows have mixed {field}")
    top_k = first.get("top_k")
    if not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("Run needs a positive top_k")

    per_question = []
    for row in rows:
        qid = row["question_id"]
        if qid not in by_id:
            raise ValueError(f"No gold label found for question {qid}")
        label = by_id[qid]
        references = [label["answer"], *label.get("answer_aliases", [])]
        scores = answer_scores(row.get("answer", ""), references)
        supporting = label.get("supporting_ids", [])
        retrieved = [passage["id"] for passage in row.get("retrieved", [])]
        per_question.append({
            "question_id": qid,
            "em": scores["em"],
            "f1": scores["f1"],
            "recall_at_k": recall_at_k(retrieved, supporting, top_k),
            "supporting_passages": len(set(supporting)),
            "supporting_passages_retrieved": len(set(retrieved) & set(supporting)),
        })

    count = len(per_question)
    mean = lambda key: sum(row[key] for row in per_question) / count
    return {
        "schema_version": 1,
        "metric_version": METRIC_VERSION,
        "mode": first.get("mode"),
        "run_id": next(iter(run_ids)),
        "dataset": next(iter(datasets)),
        "questions_evaluated": count,
        "top_k": first.get("top_k"),
        "embedding_model": first.get("embedding_model"),
        "generation_model": first.get("generation_model"),
        "em": mean("em"),
        "token_f1": mean("f1"),
        "recall_at_k": mean("recall_at_k"),
        "per_question": per_question,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="local Dense RAG JSONL file")
    parser.add_argument("--labels", type=Path,
                        help="optional labels JSON; defaults to data/processed/<dataset>/labels.json")
    parser.add_argument("--output", type=Path, help="optional metrics JSON output path")
    parser.add_argument("--expected-view", choices=("debug10", "debug20", "baseline100", "pilot200", "s500"),
                        help="expected IDs for a legacy JSONL without planned_question_ids")
    args = parser.parse_args()
    run_path = args.run if args.run.is_absolute() else ROOT / args.run
    try:
        rows = read_jsonl(run_path)
        dataset = rows[0].get("dataset")
        if dataset not in {"musique", "hotpotqa"}:
            raise ValueError(f"Unsupported dataset in run: {dataset}")
        labels_path = args.labels or (ROOT / "data" / "processed" / dataset / "labels.json")
        if not labels_path.is_absolute():
            labels_path = ROOT / labels_path
        expected_ids = None
        if args.expected_view:
            manifest_path = ROOT / "data" / "ids" / f"{dataset}_s500.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if args.expected_view == "s500":
                expected_ids = manifest["question_ids"]
            else:
                expected_ids = manifest["views"][args.expected_view]
        result = evaluate(rows, json.loads(labels_path.read_text(encoding="utf-8")), expected_ids)
        output_path = args.output or run_path.with_suffix(".metrics.json")
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8", newline="\n")
        print(f"Run ID: {result['run_id']}")
        print(f"Questions: {result['questions_evaluated']}")
        print(f"EM: {result['em']:.3f}; token F1: {result['token_f1']:.3f}; "
              f"recall@{result['top_k']}: {result['recall_at_k']:.3f}")
        print(f"Metrics: {output_path.relative_to(ROOT) if output_path.is_relative_to(ROOT) else output_path}")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Dense evaluation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
