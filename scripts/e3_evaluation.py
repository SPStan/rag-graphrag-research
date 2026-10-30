"""Issue18: deterministic paired E3 from terminal saved outcomes, no transport."""

import argparse
import inspect
import json
import platform
from pathlib import Path
import numpy as np
from scripts import (
    e2_evaluation as e2,
    run_dense as dense,
    token_accounting as accounting,
)
from scripts.compare_asbuilt import bootstrap_mean

VERSION = "e3-paired-S500-v1"
METHODS = e2.METHODS
SEED = 42
SAMPLES = 1000


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def join(rows, dataset, ids):
    require(len(ids) == len(set(ids)) and bool(ids), "duplicate_or_empty_frozen_IDs")
    joined = {m: {} for m in METHODS}
    for row in rows:
        require(
            row["dataset"] == dataset and row["method"] in METHODS,
            "unexpected_dataset_or_method",
        )
        method, qid = row["method"], row["question_id"]
        require(qid in ids and qid not in joined[method], "duplicate_or_unexpected_ID")
        require(
            row["status"] in ("completed", "attempted_failed"),
            "incomplete_E3_not_attempted",
        )
        for metric in ("em", "f1"):
            value = row["metrics"][metric]
            require(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and 0 <= value <= 1,
                "missing_or_invalid_score",
            )
            require(
                row["status"] != "attempted_failed" or value == 0,
                "failure_pipeline_score_changed",
            )
        require(
            method != "raptor" or row["metrics"]["passage_recall_at_5"] is None,
            "RAPTOR_provenance_is_not_passage_recall",
        )
        joined[method][qid] = row
    require(all(set(x) == set(ids) for x in joined.values()), "missing_IDs")
    return {m: [joined[m][qid] for qid in ids] for m in METHODS}


def analyze(rows, dataset, ids):
    paired = join(rows, dataset, ids)
    draws = np.random.default_rng(SEED).integers(0, len(ids), (SAMPLES, len(ids)))
    results, deltas = [], []
    arrays = {}
    for method in METHODS:
        selected = paired[method]
        metrics = {}
        for metric in (
            "em",
            "f1",
            "passage_recall_at_5",
            "supporting_provenance_coverage",
        ):
            values = [r["metrics"][metric] for r in selected]
            if method != "raptor" and metric == "supporting_provenance_coverage":
                continue
            known = [x for x in values if x is not None]
            metrics[metric] = {"known_cases": len(known), "mean": None, "ci95": None}
            if len(known) == len(ids):
                arrays[method, metric] = np.asarray(values, dtype=float)
                metrics[metric].update(bootstrap_mean(arrays[method, metric], draws))
            elif known:
                # No imputation or independent resampling: incomplete retrieval
                # has its observed mean only, no misleading full-pair interval.
                metrics[metric]["observed_mean"] = float(np.mean(known))
        results.append(
            {
                "method": method,
                "completed": sum(r["status"] == "completed" for r in selected),
                "attempted_failed": sum(
                    r["status"] == "attempted_failed" for r in selected
                ),
                "not_attempted": 0,
                "metrics": metrics,
            }
        )
    for method in ("hipporag2", "raptor"):
        for metric in ("em", "f1", "passage_recall_at_5"):
            if (method, metric) in arrays and ("dense", metric) in arrays:
                deltas.append(
                    {
                        "left": method,
                        "right": "dense",
                        "metric": metric,
                        **bootstrap_mean(
                            arrays[method, metric] - arrays["dense", metric], draws
                        ),
                    }
                )
    return {
        "dataset": dataset,
        "n": len(ids),
        "ordered_ids_sha256": e2.target.digest(ids),
        "resample_indices_sha256": e2.target.digest(draws.tolist()),
        "rows": results,
        "paired_differences": deltas,
    }


def load_dataset(artifact_root, data_root, dataset):
    suffix = "unattempted" if dataset == "musique" else "execution"
    plan_path = artifact_root / f".cache/e2-{dataset}-s500-{suffix}-plan.json"
    output = artifact_root / (
        "results/raw/e2-musique-s500-unattempted-v1"
        if dataset == "musique"
        else "results/raw/e2-hotpotqa-s500-v1"
    )
    public_path = artifact_root / f"results/summary/e2-{dataset}-s500.json"
    plan = dense.read_json(plan_path)
    manifest_path, evaluation_path = (
        output / "manifest.json",
        output / "evaluation.json",
    )
    manifest, public, evaluation = map(
        dense.read_json, (manifest_path, public_path, evaluation_path)
    )
    require(
        not (output / "running.lock").exists()
        and manifest["status"] == "completed"
        and evaluation["comparison_complete"],
        "full_terminal_input_required",
    )
    require(
        public["status"] == "completed"
        and public["comparison_complete"]
        and public["run_id"] == manifest["run_id"] == evaluation["run_id"],
        "terminal_run_mismatch",
    )
    require(
        public["plan_sha256"] == dense.sha256_file(plan_path)
        and public["manifest_sha256"] == dense.sha256_file(manifest_path),
        "terminal_SHA_mismatch",
    )
    require(manifest["plan_sha256"] == e2.target.digest(plan), "plan_identity_mismatch")
    e2.check_parent_pins(plan)
    reference = accounting.verified_reference(manifest, manifest_path)
    require(reference["status"] == "verified", "journal_mismatch")
    records = accounting.read_records(output / "usage.jsonl")
    require(
        not records.corrupt_tail and accounting.summarize(records)["complete"],
        "new_unknown_or_incomplete_usage",
    )
    ids_file = data_root / f"data/ids/{dataset}_s500.json"
    frozen_ids = dense.read_json(ids_file)
    ids = frozen_ids["question_ids"]
    require(
        len(ids) == 500 and ids == plan["datasets"][dataset]["question_ids"],
        "frozen_IDs_mismatch",
    )
    labels_file = data_root / f"data/processed/{dataset}/labels.json"
    require(
        dense.sha256_file(labels_file)
        == plan["datasets"][dataset]["labels_sha256_evaluator_only"],
        "labels_pin_mismatch",
    )
    labels = {r["id"]: r for r in dense.read_json(labels_file)}
    refs = e2.result_references(plan, manifest, output)
    require(len(refs) == 1500, "expected_1500_unique_outcomes")
    rows = evaluation["question_results"]
    join(rows, dataset, ids)
    for row in rows:
        key = e2.case_key(dataset, row["method"], row["question_id"])
        path, sha = refs[key]
        require(dense.sha256_file(path) == sha, "saved_case_mismatch")
        saved = dense.read_json(path)
        require(
            saved["dataset"] == dataset
            and saved["method"] == row["method"]
            and saved["question_id"] == row["question_id"],
            "saved_case_identity_mismatch",
        )
        require(
            saved["status"] == "completed"
            if row["status"] == "completed"
            else saved["status"] != "completed",
            "saved_case_status_mismatch",
        )
        rescored = e2.score_result(saved, labels[row["question_id"]])
        require(
            all(
                rescored[k] == row["metrics"][k]
                for k in ("em", "f1", "supporting_provenance_coverage")
            ),
            "common_evaluator_score_mismatch",
        )
        if key in manifest["results"]:
            e2.verify_saved_case(plan, output, saved, records)
    metadata = {
        "files": {
            str(p.resolve()): dense.sha256_file(p)
            for p in (
                plan_path,
                manifest_path,
                evaluation_path,
                public_path,
                output / "usage.jsonl",
                labels_file,
                ids_file,
            )
        },
        "run_id": manifest["run_id"],
        "reader": {
            k: plan[k]
            for k in (
                "reader_model",
                "reader_version",
                "reader_options",
                "message_utf8_bytes_limit",
                "embedding_model",
                "embedding_digest",
            )
        },
        "accounting": {
            k: public[k]
            for k in (
                "new_physical_accounting",
                "historical_source_accounting",
                "cost_complete",
            )
        },
    }
    return rows, ids, metadata


def build(artifact_root, data_root):
    datasets, inputs, examples = [], {}, []
    reader = None
    for dataset in ("musique", "hotpotqa"):
        rows, ids, metadata = load_dataset(artifact_root, data_root, dataset)
        require(
            reader is None or reader == metadata["reader"], "common_reader_mismatch"
        )
        reader = metadata["reader"]
        datasets.append(analyze(rows, dataset, ids))
        inputs[dataset] = metadata
        paired = join(rows, dataset, ids)
        # Fixed strata, then frozen tuning order; no check/reserve selection.
        candidates = [
            (qid, i)
            for i, qid in enumerate(ids[:300])
            if len({paired[m][i]["metrics"]["f1"] for m in METHODS}) > 1
        ]
        for qid, i in candidates[:5]:
            examples.append(
                {
                    "dataset": dataset,
                    "question_id": qid,
                    "selection": "first five frozen tuning300 IDs with unequal F1",
                    "scores": {m: paired[m][i]["metrics"] for m in METHODS},
                    "statuses": {m: paired[m][i]["status"] for m in METHODS},
                    "interpretation": "saved-answer disagreement; illustrative, not a causal frequency or signal choice",
                }
            )
    return {
        "version": VERSION,
        "comparison_complete": True,
        "bootstrap": {
            "seed": SEED,
            "samples": SAMPLES,
            "interval": "pointwise percentile95 [2.5,97.5]",
            "rng": "numpy.default_rng/PCG64",
            "numpy": np.__version__,
            "python": platform.python_version(),
        },
        "metric_function_sha256": e2.target.digest(inspect.getsource(e2.score_result)),
        "code_sha256": {
            p: dense.sha256_file(Path(__file__).parent / p)
            for p in (
                "e3_evaluation.py",
                "compare_asbuilt.py",
                "evaluate_dense.py",
                "e2_evaluation.py",
            )
        },
        "inputs": inputs,
        "datasets": datasets,
        "examples": examples,
        "limitations": [
            "S500 includes development; descriptive, not independent test",
            "Mixed Hippo extractor/errors and incomplete E1/source cost retained",
            "Sealed transport failures are pipeline zero, not wrong reader answers; unknown usage is not zero",
            "RAPTOR provenance is not passage recall@5",
            "CI containing zero does not establish equivalence or a <2pp bound",
            "No signal-check selection, models, HTTP or tracking export",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = build(args.artifact_root, args.data_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dense.write_json_atomic(args.output.with_suffix(".json"), result)
    lines = [
        "# E3: descriptive paired S500",
        "",
        "| Dataset | Method | completed / failed | EM [95% CI] | F1 [95% CI] |",
        "|---|---|---|---|---|",
    ]
    for dataset in result["datasets"]:
        for row in dataset["rows"]:
            cells = [
                f"{row['metrics'][k]['mean']:.4f} {row['metrics'][k]['ci95']}"
                for k in ("em", "f1")
            ]
            lines.append(
                f"| {dataset['dataset']} | {row['method']} | {row['completed']} / {row['attempted_failed']} | {' | '.join(cells)} |"
            )
        for delta in dataset["paired_differences"]:
            lines.append(
                f"\n{dataset['dataset']} {delta['left']}−Dense {delta['metric']}: {delta['mean']:.4f}, CI {delta['ci95']}."
            )
    lines += [
        "",
        *result["limitations"],
        "",
        "1000 paired resamples, seed42; all systems share the same sampled IDs per repetition. Values are fractions, not percentages. Refs #18.",
    ]
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "comparison_complete": True,
                "datasets": len(result["datasets"]),
                "HTTP": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
