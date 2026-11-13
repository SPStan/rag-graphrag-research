"""Issue21: freeze one retrieval-only signal before offline signal-check scoring."""

import argparse
import csv
import hashlib
import io
import math
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

from scripts import e2_evaluation as e2, e3_evaluation as e3, full_experiment as full
from scripts import run_dense as dense, evaluate_dense

ROOT = Path(__file__).resolve().parents[1]
VERSION = "negative-top1-cosine-v1"
DATASETS = ("musique", "hotpotqa")
CODE_FILES = (
    "run_dense.py",
    "dense_error_signal.py",
    "e2_evaluation.py",
    "e3_evaluation.py",
    "evaluate_dense.py",
    "full_experiment.py",
    "evaluation_view.py",
    "answer_parser.py",
)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def code_digest(content):
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def error_signal(scores):
    """Only five inference-time cosine scores enter this pure function."""
    require(isinstance(scores, tuple) and len(scores) == 5, "five_scores_required")
    require(
        all(
            isinstance(x, (int, float))
            and not isinstance(x, bool)
            and math.isfinite(x)
            and -1 <= x <= 1
            for x in scores
        ),
        "invalid_cosine_scores",
    )
    require(all(a >= b for a, b in zip(scores, scores[1:])), "scores_not_descending")
    return -float(scores[0])


def auroc(values, errors):
    require(len(values) == len(errors) and bool(values), "score_target_length")
    require(
        all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
            for x in values
        ),
        "invalid_signal",
    )
    require(all(type(x) is int and x in (0, 1) for x in errors), "invalid_error_target")
    positive = [s for s, y in zip(values, errors) if y == 1]
    negative = [s for s, y in zip(values, errors) if y == 0]
    if not positive or not negative:
        return None
    return sum((a > b) + 0.5 * (a == b) for a in positive for b in negative) / (
        len(positive) * len(negative)
    )


def inputs(artifact_root, dataset):
    plan_path = artifact_root / f".cache/e2-{dataset}-s500-unattempted-plan.json"
    output = artifact_root / f"results/raw/e2-{dataset}-s500-unattempted-v1"
    if dataset == "hotpotqa":
        active = dense.read_json(artifact_root / ".cache/e2-hotpotqa-s500-active.json")
        require(
            (artifact_root / active["plan"]).resolve() == plan_path.resolve()
            and Path(active["output"]).resolve() == output.resolve()
            and dense.sha256_file(plan_path) == active["plan_sha256"],
            "active_binding_changed",
        )
    plan, manifest = (
        dense.read_json(plan_path),
        dense.read_json(output / "manifest.json"),
    )
    require(
        manifest["status"] == "completed" and not (output / "running.lock").exists(),
        "terminal_source_required",
    )
    require(manifest["plan_sha256"] == e2.target.digest(plan), "plan_pin_mismatch")
    e3.verify_protocol(plan, artifact_root, dataset)  # Does not read labels or scores.
    e2.check_parent_pins(plan)
    ids_path, split_path = (
        ROOT / f"data/ids/{dataset}_{name}.json"
        for name in ("s500", "comparison_split")
    )
    ids, split = dense.read_json(ids_path)["question_ids"], dense.read_json(split_path)
    full.check_split(ids, split)
    require(
        ids == plan["datasets"][dataset]["question_ids"]
        and dense.sha256_file(ids_path) == split["source_sha256"]
        and dense.sha256_file(split_path) == plan["datasets"][dataset]["split_sha256"],
        "frozen_split_changed",
    )
    refs = e2.result_references(plan, manifest, output)
    require(len(refs) == 1500, "incomplete_source")
    metadata = {
        "run_id": manifest["run_id"],
        "plan_sha256": dense.sha256_file(plan_path),
        "manifest_sha256": dense.sha256_file(output / "manifest.json"),
        "ids_sha256": dense.sha256_file(ids_path),
        "split_sha256": dense.sha256_file(split_path),
        "labels_sha256_evaluation_only": plan["datasets"][dataset][
            "labels_sha256_evaluator_only"
        ],
        "contract_sha256": e2.target.digest(full.contract(plan)),
        "index_sha256": e2.target.digest(
            next(
                i
                for i in plan["datasets"][dataset]["indexes"]
                if i["method"] == "dense"
            )
        ),
    }
    return ids, refs, metadata


def saved_features(refs, dataset, qid):
    path, sha = refs[e2.case_key(dataset, "dense", qid)]
    require(dense.sha256_file(path) == sha, "case_pin_changed")
    saved = dense.read_json(path)
    require(
        saved["dataset"] == dataset
        and saved["method"] == "dense"
        and saved["question_id"] == qid,
        "case_identity_changed",
    )
    retrieval = saved.get("retrieval", {})
    require(retrieval.get("kind") == "passages", "dense_passages_required")
    # No question, response, gold, EM/F1, supporting labels or metadata is passed.
    scores = tuple(retrieval.get("scores", []))
    error_signal(scores)
    return scores, saved


def freeze(artifact_root):
    datasets = {}
    for dataset in DATASETS:
        ids, refs, metadata = inputs(artifact_root, dataset)
        top1 = [saved_features(refs, dataset, q)[0][0] for q in ids[:300]]
        datasets[dataset] = {
            "inputs": metadata,
            "tuning_n": 300,
            "check_n": 100,
            "reserved_n": 100,
            "tuning_top1_min": min(top1),
            "tuning_top1_max": max(top1),
            "tuning_top1_mean": sum(top1) / 300,
        }
    return {
        "version": VERSION,
        "formula": "error_signal = -retrieval.scores[0]",
        "direction": "larger means more likely Dense EM=0",
        "selection": "Only candidate: saved BGE cosine top1, available for all tuning300 cases; direction from similarity-confidence prior, not check labels or AUROC optimization",
        "target": "int(existing evaluator EM == 0)",
        "threshold": None,
        "threshold_reason": "ranking-only AUROC; no cascade or threshold fitting",
        "split": "frozen S500 [0:300] tuning, [300:400] signal-check, [400:500] reserved; seed42; no reshuffle",
        "code_sha256_lf": {
            name: code_digest((ROOT / "scripts" / name).read_bytes())
            for name in CODE_FILES
        },
        "metric_version": evaluate_dense.METRIC_VERSION,
        "metric_code_sha256_lf": code_digest(
            (ROOT / "scripts/evaluate_dense.py").read_bytes()
        ),
        "datasets": datasets,
        "limitation": "Historical control/reserve scores were disclosed in PR40 and processed by E3/oracle. Freeze precedes this signal-check evaluation only; no pristine or independent test claim.",
    }


def verify_freeze(path, commit):
    require(
        len(commit) == 40 and all(c in "0123456789abcdef" for c in commit),
        "full_freeze_commit_required",
    )
    relative = path.resolve().relative_to(ROOT.resolve()).as_posix()

    def blob(name):
        return subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=ROOT)

    require(
        code_digest(blob(relative)) == code_digest(path.read_bytes()),
        "freeze_not_committed_or_changed",
    )
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT, check=True
    )
    # Legacy freeze41c2f1c did not list this IO/hash dependency. Bind it to
    # that exact Git commit before calling its JSON reader, without editing
    # the historical decision or substituting the current dependency hash.
    run_dense_sha = code_digest(blob("scripts/run_dense.py"))
    require(
        code_digest((ROOT / "scripts/run_dense.py").read_bytes())
        == code_digest(Path(dense.__file__).read_bytes())
        == run_dense_sha,
        "signal_code_changed_after_freeze:run_dense.py",
    )
    decision = dense.read_json(path)
    require(
        decision["version"] == VERSION
        and decision["formula"] == "error_signal = -retrieval.scores[0]"
        and decision["direction"] == "larger means more likely Dense EM=0"
        and decision["target"] == "int(existing evaluator EM == 0)"
        and decision["threshold"] is None,
        "signal_contract_changed",
    )
    for name in CODE_FILES:
        expected = (
            decision["code_sha256_lf"].get(name, run_dense_sha)
            if name == "run_dense.py"
            else decision["code_sha256_lf"][name]
        )
        require(
            code_digest(blob(f"scripts/{name}"))
            == expected
            == code_digest((ROOT / "scripts" / name).read_bytes()),
            "signal_code_changed_after_freeze",
        )
    require(
        code_digest((ROOT / "scripts/evaluate_dense.py").read_bytes())
        == decision["metric_code_sha256_lf"]
        and decision["metric_version"] == evaluate_dense.METRIC_VERSION,
        "evaluator_changed_after_freeze",
    )
    return decision


def evaluate(artifact_root, data_root, decision, commit):
    rows, summaries = [], []
    for dataset in DATASETS:
        ids, refs, metadata = inputs(artifact_root, dataset)
        require(
            metadata == decision["datasets"][dataset]["inputs"], "frozen_inputs_changed"
        )
        # This is the first label access; the committed freeze was verified already.
        label_path = data_root / f"data/processed/{dataset}/labels.json"
        require(
            dense.sha256_file(label_path) == metadata["labels_sha256_evaluation_only"],
            "label_pin_changed",
        )
        labels = {
            r["id"]: r
            for r in e2.select_in_view(
                dense.read_json(label_path), ids[300:400], "label"
            )
        }
        signals, errors, timings = [], [], []
        for qid in ids[300:400]:
            scores, saved = saved_features(refs, dataset, qid)
            start = time.perf_counter_ns()
            value = error_signal(scores)
            timings.append((time.perf_counter_ns() - start) / 1e9)
            score = e2.score_result(saved, labels[qid])["em"]
            require(score in (0, 1), "invalid_EM")
            target = int(score == 0)
            signals.append(value)
            errors.append(target)
            rows.append(
                {
                    "dataset": dataset,
                    "question_id": qid,
                    "signal": value,
                    "error": target,
                    "source_run_id": saved["run_id"],
                }
            )
        auc = auroc(signals, errors)
        summaries.append(
            {
                "dataset": dataset,
                "n": 100,
                "errors": sum(errors),
                "correct": 100 - sum(errors),
                "auroc": auc,
                "auroc_status": "undefined_single_class" if auc is None else "defined",
                "signal_compute_seconds": sum(timings),
                "signal_mean_seconds": sum(timings) / 100,
            }
        )
    csv_io = io.StringIO(newline="")
    writer = csv.DictWriter(
        csv_io,
        fieldnames=("dataset", "question_id", "signal", "error", "source_run_id"),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    private_bytes = csv_io.getvalue().encode("utf-8")
    result = {
        "version": VERSION,
        "freeze_commit": commit,
        "freeze_digest": e2.target.digest(decision),
        "datasets": summaries,
        "private_rows": len(rows),
        "private_csv_sha256": hashlib.sha256(private_bytes).hexdigest(),
        "additional_usage": {"LLM_tokens": 0, "embedding_tokens": 0, "POST": 0},
        "network": "socket connect/connect_ex forbidden; saved retrieval reused",
        "timing_scope": "pure signal calculation only; excludes loading, SHA audits and label scoring; measured local wall time, not original inference latency",
        "limitations": [
            decision["limitation"],
            "No signal reselection or direction flip after check; no cascade/E6 run; no economic benefit established",
            "EM=0 is the evaluator target, not semantic truth; no per-question labels/scores are public",
        ],
    }
    result["analytical_digest"] = e2.target.digest(
        {
            "datasets": [
                {k: v for k, v in s.items() if not k.startswith("signal_")}
                for s in summaries
            ],
            "private_csv_sha256": result["private_csv_sha256"],
            "freeze_digest": result["freeze_digest"],
        }
    )
    return result, private_bytes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "evaluate"))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--freeze-commit")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--private-output", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    with (
        patch(
            "socket.socket.connect",
            side_effect=AssertionError("signal_network_forbidden"),
        ),
        patch(
            "socket.socket.connect_ex",
            side_effect=AssertionError("signal_network_forbidden"),
        ),
    ):
        if args.action == "freeze":
            require(not args.decision.exists(), "freeze_overwrite_forbidden")
            result = freeze(args.artifact_root.resolve())
            args.decision.parent.mkdir(parents=True, exist_ok=True)
            dense.write_json_atomic(args.decision, result)
        else:
            require(
                all(
                    (
                        args.freeze_commit,
                        args.data_root,
                        args.private_output,
                        args.output,
                    )
                ),
                "evaluation_arguments_required",
            )
            private = args.private_output.resolve()
            require(
                private.is_relative_to((args.artifact_root / ".cache").resolve())
                and not private.exists(),
                "private_output_must_be_new_inside_artifact_cache",
            )
            require(not args.output.exists(), "public_output_overwrite_forbidden")
            decision = verify_freeze(args.decision, args.freeze_commit)
            result, private_bytes = evaluate(
                args.artifact_root.resolve(),
                args.data_root,
                decision,
                args.freeze_commit,
            )
            private.parent.mkdir(parents=True, exist_ok=True)
            with private.open("xb") as stream:
                stream.write(private_bytes)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            dense.write_json_atomic(args.output, result)
    print("Signal stage complete; HTTP=0; no per-case values printed")


if __name__ == "__main__":
    main()
