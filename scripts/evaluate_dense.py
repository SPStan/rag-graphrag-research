"""Evaluate a saved Dense RAG JSONL against labels, after generation is complete."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import string
import sys

try:
    from scripts.answer_parser import extract_reader_answer
except ModuleNotFoundError:  # Direct execution puts the scripts directory on sys.path.
    from answer_parser import extract_reader_answer


ROOT = Path(__file__).resolve().parents[1]
METRIC_VERSION = "hipporag2-squad-normalization-answer-marker-v3"
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


def validate_manifest_file(run_path, rows, manifest):
    """Bind a result file to its completed run manifest and expected ID plan."""
    if manifest.get("status") != "completed":
        raise ValueError("Run manifest status must be completed")
    run_ids = {row.get("run_id") for row in rows}
    if manifest.get("run_id") not in run_ids or len(run_ids) != 1:
        raise ValueError("Run manifest does not match the JSONL run_id")
    datasets = {row.get("dataset") for row in rows}
    if manifest.get("dataset") is not None and datasets != {manifest.get("dataset")}:
        raise ValueError("Run manifest does not match the JSONL dataset")
    expected_hash = manifest.get("results_sha256")
    actual_hash = hashlib.sha256(run_path.read_bytes()).hexdigest()
    if not expected_hash or actual_hash != expected_hash:
        raise ValueError("Run JSONL does not match the results hash in its manifest")
    expected_ids = manifest.get("expected_question_ids")
    if not isinstance(expected_ids, list) or not expected_ids:
        raise ValueError("Run manifest must contain expected_question_ids")
    return expected_ids


def evaluate(rows, labels, expected_ids=None, manifest=None):
    run_ids = {row.get("run_id") for row in rows}
    datasets = {row.get("dataset") for row in rows}
    if len(run_ids) != 1 or None in run_ids:
        raise ValueError("Run rows must share one non-empty run_id")
    if len(datasets) != 1 or None in datasets:
        raise ValueError("Run rows must share one dataset")
    if manifest is not None:
        if manifest.get("status") != "completed":
            raise ValueError("Run manifest status must be completed")
        if manifest.get("run_id") != next(iter(run_ids)):
            raise ValueError("Run manifest does not match the JSONL run_id")

    by_id = {label["id"]: label for label in labels}
    if len(by_id) != len(labels):
        raise ValueError("Duplicate label IDs")
    row_ids = [row.get("question_id") for row in rows]
    if None in row_ids or len(set(row_ids)) != len(row_ids):
        raise ValueError("Run rows contain missing or duplicate question IDs")

    embedded_expected = [row.get("planned_question_ids") for row in rows]
    if manifest is not None:
        manifest_ids = manifest.get("expected_question_ids")
        if not isinstance(manifest_ids, list) or not manifest_ids:
            raise ValueError("Run manifest must contain expected_question_ids")
        if expected_ids is not None and expected_ids != manifest_ids:
            raise ValueError("Explicit expected IDs do not match the run manifest")
        expected_ids = manifest_ids
    if expected_ids is None:
        if any(ids is None for ids in embedded_expected):
            raise ValueError("Expected question IDs are required for legacy runs")
        if any(ids != embedded_expected[0] for ids in embedded_expected[1:]):
            raise ValueError("Run rows disagree on planned question IDs")
        expected_ids = embedded_expected[0]
    if not expected_ids or row_ids != expected_ids:
        raise ValueError("Run question IDs do not exactly match the expected ordered IDs")
    if any(ids is not None and ids != expected_ids for ids in embedded_expected):
        raise ValueError("Run rows disagree with manifest expected question IDs")

    config_fields = ("top_k", "embedding_model", "generation_model",
                     "reader_prompt_version", "generation_options")
    first = rows[0]
    for field in config_fields:
        if first.get(field) in (None, "", {}):
            raise ValueError(f"Run is missing required {field}")
        value = json.dumps(first.get(field), sort_keys=True, ensure_ascii=False)
        if any(json.dumps(row.get(field), sort_keys=True, ensure_ascii=False) != value
               for row in rows[1:]):
            raise ValueError(f"Run rows have mixed {field}")
    for field in ("context_source_run_id", "context_source_results_sha256"):
        value = json.dumps(first.get(field), sort_keys=True, ensure_ascii=False)
        if any(json.dumps(row.get(field), sort_keys=True, ensure_ascii=False) != value
               for row in rows[1:]):
            raise ValueError(f"Run rows have mixed {field}")
    top_k = first.get("top_k")
    if not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("Run needs a positive top_k")
    options = first.get("generation_options")
    required_options = ("temperature", "num_predict", "num_ctx")
    prompt_version = re.search(r"-v(\d+)$", str(first["reader_prompt_version"]))
    if prompt_version and int(prompt_version.group(1)) >= 3:
        required_options += ("seed",)
    if not isinstance(options, dict) or not all(key in options for key in required_options):
        raise ValueError(f"Run generation_options must include {', '.join(required_options)}")

    per_question = []
    for row in rows:
        if "answer" not in row or not isinstance(row.get("answer"), str):
            raise ValueError("Each row must contain an answer string, including for failed answers")
        if "answer_extraction_status" not in row:
            raise ValueError("Each row must record answer_extraction_status")
        if "done_reason" not in row or row.get("done_reason") is None:
            raise ValueError("Each row must record a non-empty done_reason")
        if row.get("done") is False:
            raise ValueError("Run contains an incomplete generation response")
        if prompt_version and int(prompt_version.group(1)) >= 3 and row.get("done") is not True:
            raise ValueError("Reader v3 rows must record done=true")
        if not isinstance(row.get("retrieved"), list):
            raise ValueError("Each row must contain a retrieved passage list")
        qid = row["question_id"]
        if qid not in by_id:
            raise ValueError(f"No gold label found for question {qid}")
        label = by_id[qid]
        references = [label["answer"], *label.get("answer_aliases", [])]
        prediction = row.get("answer", "")
        extraction_status = row.get("answer_extraction_status")
        if extraction_status == "missing_answer_marker" and isinstance(row.get("raw_answer"), str):
            prediction, extraction_status = extract_reader_answer(row["raw_answer"])
        scores = answer_scores(prediction, references)
        supporting = label.get("supporting_ids", [])
        retrieved = [passage["id"] for passage in row.get("retrieved", [])]
        per_question.append({
            "question_id": qid,
            "answer_extraction_status": extraction_status,
            "em": scores["em"],
            "f1": scores["f1"],
            "recall_at_k": recall_at_k(retrieved, supporting, top_k),
            "supporting_passages": len(set(supporting)),
            "supporting_passages_retrieved": len(set(retrieved) & set(supporting)),
            "done_reason": row.get("done_reason"),
            "prompt_tokens": row.get("prompt_tokens"),
            "completion_tokens": row.get("completion_tokens"),
            "query_embedding_prompt_tokens": row.get("query_embedding_prompt_tokens"),
            "query_embedding_client_seconds": row.get("query_embedding_client_seconds"),
            "retrieval_seconds": row.get("retrieval_seconds"),
            "generation_wall_seconds": row.get("generation_wall_seconds"),
            "question_end_to_end_seconds": row.get("question_end_to_end_seconds"),
        })

    count = len(per_question)
    mean = lambda key: sum(row[key] for row in per_question) / count
    def known_sum(key):
        values = [row.get(key) for row in rows]
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                   for value in values):
            return None
        return sum(values)

    def known_mean(key):
        total = known_sum(key)
        return total / count if total is not None else None

    index_usage = (manifest or {}).get("index_embedding", {})
    if not index_usage:
        # Older manifests only stored the embedding build duration.
        old_seconds = (manifest or {}).get("index_embedding_seconds_this_run")
        index_usage = {"build_seconds_this_run": old_seconds}
    cache_build = index_usage.get("cache_build_provenance") or {}
    retrieval_manifest = (manifest or {}).get("retrieval", {})
    if any(row.get("context_source_run_id") != retrieval_manifest.get("context_source_run_id")
           or row.get("context_source_results_sha256")
           != retrieval_manifest.get("context_source_results_sha256") for row in rows):
        raise ValueError("Run rows disagree with manifest context replay source")
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
        "context_source_run_id": (manifest or {}).get("retrieval", {}).get(
            "context_source_run_id"),
        "context_source_results_sha256": (manifest or {}).get("retrieval", {}).get(
            "context_source_results_sha256"),
        "em": mean("em"),
        "token_f1": mean("f1"),
        "recall_at_k": mean("recall_at_k"),
        "generation_stopped_normally": sum(row.get("done_reason") == "stop" for row in rows),
        "usage": {
            "index_embedding_prompt_tokens": index_usage.get("embedding_prompt_tokens"),
            "index_embedding_api_total_duration_ns": index_usage.get("api_total_duration_ns"),
            "index_embedding_build_seconds": index_usage.get("build_seconds_this_run"),
            "index_embedding_cache_read_seconds": index_usage.get("cache_read_seconds"),
            "index_embedding_original_build_run_id": cache_build.get("build_run_id"),
            "index_embedding_original_build_seconds": cache_build.get("build_seconds"),
            "index_embedding_original_prompt_tokens": cache_build.get("embedding_prompt_tokens"),
            "index_embedding_original_api_total_duration_ns": cache_build.get("api_total_duration_ns"),
            "query_embedding_prompt_tokens": known_sum("query_embedding_prompt_tokens"),
            "query_embedding_client_seconds": known_sum("query_embedding_client_seconds"),
            "retrieval_seconds": known_sum("retrieval_seconds"),
            "generation_prompt_tokens": known_sum("prompt_tokens"),
            "generation_completion_tokens": known_sum("completion_tokens"),
            "generation_wall_seconds": known_sum("generation_wall_seconds"),
            "generation_server_seconds": known_sum("generation_seconds"),
            "question_end_to_end_seconds": known_sum("question_end_to_end_seconds"),
            "mean_generation_tokens_per_second": known_mean("generation_tokens_per_second"),
            "note": ("Index embedding usage is in the run manifest; null means unavailable, not zero. "
                     "Reader replays do not repeat query embedding or retrieval; their source run "
                     "is recorded separately."),
        },
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
        manifest_path = run_path.with_suffix(".manifest.json")
        manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest_path.exists() else None)
        if manifest is not None:
            manifest_ids = validate_manifest_file(run_path, rows, manifest)
            if expected_ids is not None and expected_ids != manifest_ids:
                raise ValueError("Expected view does not match the run manifest")
            expected_ids = manifest_ids
        result = evaluate(rows, json.loads(labels_path.read_text(encoding="utf-8")),
                          expected_ids, manifest)
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
