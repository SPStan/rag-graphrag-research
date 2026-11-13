"""Issue20: aggregate oracle from verified saved E3 outcomes, without transport."""

import argparse
import inspect
import math
from pathlib import Path
from statistics import mean
from unittest.mock import patch

from scripts import e3_evaluation as e3, evaluate_dense, run_dense as dense

VERSION = "dense-hippo-oracle-v1"
METHODS = ("dense", "hipporag2")
DATASETS = ("musique", "hotpotqa")


def analyze(rows, dataset, ids):
    """Join by frozen ID; failures retain the pre-existing pipeline-zero policy."""
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("empty_or_duplicate_expected_IDs")
    paired = {m: {} for m in METHODS}
    problems = []
    for row in rows:
        method, qid = row.get("method"), row.get("question_id")
        if row.get("dataset") != dataset or method not in METHODS:
            problems.append("unexpected_dataset_or_method")
            continue
        if qid not in ids or qid in paired[method]:
            problems.append(f"{method}: duplicate_or_unexpected_ID={qid}")
            continue
        metrics = row.get("metrics", {})
        em, f1 = metrics.get("em"), metrics.get("f1")
        if (
            isinstance(em, bool)
            or not isinstance(em, (int, float))
            or em not in (0, 1)
            or isinstance(f1, bool)
            or not isinstance(f1, (int, float))
            or not math.isfinite(f1)
            or not 0 <= f1 <= 1
        ):
            problems.append(f"{method}: invalid_scores_ID={qid}")
        if row.get("status") not in ("completed", "attempted_failed"):
            problems.append(f"{method}: nonterminal_ID={qid}")
        if row.get("status") == "attempted_failed" and (em != 0 or f1 != 0):
            problems.append(f"{method}: failure_score_changed_ID={qid}")
        paired[method][qid] = row
    for method in METHODS:
        missing = sorted(set(ids) - paired[method].keys())
        if missing:
            problems.append(f"{method}: missing_IDs={missing}")
    if problems:
        raise ValueError("; ".join(problems))
    metrics = {}
    for metric in ("em", "f1"):
        left, right = (
            [paired[m][qid]["metrics"][metric] for qid in ids] for m in METHODS
        )
        oracle = mean(max(a, b) for a, b in zip(left, right))
        metrics[metric] = {
            "dense": mean(left),
            "hipporag2": mean(right),
            "oracle": oracle,
            "hippo_minus_dense_pp": 100 * (mean(right) - mean(left)),
            "oracle_minus_dense_pp": 100 * (oracle - mean(left)),
            "oracle_minus_hippo_pp": 100 * (oracle - mean(right)),
        }
    groups = dict.fromkeys(
        ("both_correct", "dense_only", "hippo_only", "both_wrong"), 0
    )
    names = {
        (1, 1): "both_correct",
        (1, 0): "dense_only",
        (0, 1): "hippo_only",
        (0, 0): "both_wrong",
    }
    for qid in ids:
        groups[names[tuple(paired[m][qid]["metrics"]["em"] for m in METHODS)]] += 1
    return {
        "dataset": dataset,
        "n": len(ids),
        "metrics": metrics,
        "em_groups": {
            k: {"count": v, "fraction": v / len(ids)} for k, v in groups.items()
        },
        "outcomes": {
            m: {
                s: sum(r["status"] == s for r in paired[m].values())
                for s in ("completed", "attempted_failed")
            }
            for m in METHODS
        },
    }


def build(artifact_root, data_root, ledger_path):
    ledger = dense.read_json(ledger_path)
    require = e3.require
    require(
        len(ledger["question_scores"]) == 3000
        and {r["dataset"] for r in ledger["question_scores"]} == set(DATASETS),
        "private_ledger_scope_mismatch",
    )
    require(
        e3.e2.target.digest(ledger["question_scores"])
        == ledger["question_scores_sha256"],
        "private_ledger_digest_mismatch",
    )
    require(
        ledger["metric_function_sha256"]
        == e3.e2.target.digest(inspect.getsource(e3.e2.score_result)),
        "metric_version_mismatch",
    )
    results, sources = [], {}
    for dataset in DATASETS:
        rows, ids, metadata = e3.load_dataset(artifact_root, data_root, dataset)
        require(len(ids) == 500, "expected_500_IDs")
        saved_scores = [r for r in ledger["question_scores"] if r["dataset"] == dataset]
        ordered = e3.join_order(saved_scores, dataset, ids)
        require(
            all(
                a["metrics"] == b["metrics"] and a["status"] == b["status"]
                for a, b in zip(ordered, e3.join_order(rows, dataset, ids))
            ),
            "private_ledger_saved_score_mismatch",
        )
        require(metadata == ledger["inputs"][dataset], "private_ledger_input_mismatch")
        results.append(
            analyze([r for r in rows if r["method"] in METHODS], dataset, ids)
        )
        files = {}
        for filename, sha in metadata["files"].items():
            path = Path(filename).resolve()
            root = artifact_root if path.is_relative_to(artifact_root) else data_root
            files[path.relative_to(root).as_posix()] = sha
        sources[dataset] = {
            "run_id": metadata["run_id"],
            "files": files,
            "ordered_ids_sha256": e3.e2.target.digest(ids),
            "reader": metadata["reader"],
        }
    require(
        sources["musique"]["reader"] == sources["hotpotqa"]["reader"], "reader_mismatch"
    )
    return {
        "version": VERSION,
        "metric_version": evaluate_dense.METRIC_VERSION,
        "graph_method": "hipporag2",
        "selection": "issue14 pilot200 decision; docs/E2_EVALUATION.md; not selected by this oracle",
        "private_ledger_sha256": dense.sha256_file(ledger_path),
        "inputs": sources,
        "code_sha256": {
            p: dense.sha256_file(Path(__file__).parent / p)
            for p in (
                "analyze_oracle.py",
                "e3_evaluation.py",
                "e2_evaluation.py",
                "evaluate_dense.py",
            )
        },
        "datasets": results,
        "limitations": [
            "Oracle uses reference labels to select among fixed saved answers; it is not a deployable router or an economic benefit.",
            "EM and F1 oracles select independently; their maximizing answer may differ.",
            "S500 includes development/pilot; this is descriptive, not an independent test.",
            "Historical control/reserve score disclosure remains; no signal or threshold is selected here.",
            "Existing attempted_failed pipeline scores remain zero; infrastructure failure is not a wrong reader answer; unknown usage remains unknown.",
            "Only aggregate metrics/groups are public; no per-question scores, IDs or labels are exported.",
        ],
    }


def markdown(result):
    lines = [
        "# Oracle: Dense и HippoRAG2",
        "",
        "500 парных вопросов на датасет. EM/F1 — проценты; разности — процентные пункты.",
        "Oracle EM и oracle F1 вычисляются независимо как среднее покомпонентного максимума.",
        "",
        "| Датасет | Метрика | Dense, % | HippoRAG2, % | Oracle, % | Hippo − Dense, п.п. | Oracle − Dense, п.п. | Oracle − Hippo, п.п. |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for dataset in result["datasets"]:
        for metric, values in dataset["metrics"].items():
            cells = [f"{100 * values[m]:.2f}" for m in ("dense", "hipporag2", "oracle")]
            cells += [
                f"{values[m]:.2f}"
                for m in (
                    "hippo_minus_dense_pp",
                    "oracle_minus_dense_pp",
                    "oracle_minus_hippo_pp",
                )
            ]
            lines.append(
                f"| {dataset['dataset']} | {metric.upper()} | {' | '.join(cells)} |"
            )
    lines += [
        "",
        "По EM: число вопросов и доля от 500. Неверный pipeline outcome включает сохранённые технические ошибки.",
        "",
        "| Датасет | Обе верны | Только Dense | Только Hippo | Обе неверны |",
        "|---|---:|---:|---:|---:|",
    ]
    for dataset in result["datasets"]:
        cells = [
            f"{v['count']} ({100 * v['fraction']:.2f}%)"
            for v in dataset["em_groups"].values()
        ]
        lines.append(f"| {dataset['dataset']} | {' | '.join(cells)} |")
    lines += [
        "",
        "Это идеальный предел выбора среди двух сохранённых ответов при известной разметке. Он не является качеством работающего маршрутизатора и не доказывает экономическую выгоду.",
        "",
        "S500 содержит development/pilot. Прежнее раскрытие контрольных оценок в истории сохраняется; здесь публикуются только агрегаты. Сигнал и порог не выбирались. Ошибки сохранены, unknown usage не заменён нулём.",
        "",
        "Методика и воспроизведение: [ORACLE](../../docs/ORACLE.md). Версии, run ID и SHA входов — в [JSON](oracle.json).",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("artifact-root", "data-root", "ledger", "output"):
        parser.add_argument(f"--{flag}", type=Path, required=True)
    args = parser.parse_args(argv)
    with (
        patch(
            "socket.socket.connect",
            side_effect=AssertionError("oracle_network_forbidden"),
        ),
        patch(
            "socket.socket.connect_ex",
            side_effect=AssertionError("oracle_network_forbidden"),
        ),
    ):
        result = build(
            args.artifact_root.resolve(), args.data_root.resolve(), args.ledger
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dense.write_json_atomic(args.output, result)
    args.output.with_suffix(".md").write_text(markdown(result), encoding="utf-8")
    print(
        "Oracle complete: 2 datasets, 500 paired IDs each; HTTP=0; aggregate output only"
    )


if __name__ == "__main__":
    main()
