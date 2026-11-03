"""Pure paired statistics and the offline CLI, never a model evaluation."""

import copy
import socket
import pytest
from scripts import e3_evaluation as e3, run_dense as dense


def rows():
    return [
        {
            "dataset": "synthetic",
            "method": m,
            "question_id": q,
            "status": "completed",
            "metrics": {
                "em": 0.25,
                "f1": 0.25,
                "passage_recall_at_5": None if m == "raptor" else 0.5,
                "supporting_provenance_coverage": 0.5,
            },
        }
        for m in e3.METHODS
        for q in ("a", "b", "c")
    ]


def test_identical_scores_zero_paired_interval_and_shared_draws():
    report = e3.analyze(rows(), "synthetic", ["a", "b", "c"])
    assert all(
        r["mean"] == 0 and r["ci95"] == [0, 0] for r in report["paired_differences"]
    )
    assert not any(
        r["left"] == "raptor" and r["metric"] == "passage_recall_at_5"
        for r in report["paired_differences"]
    )
    assert len(report["resample_indices_sha256"]) == 64


def test_constant_difference_permutation_and_reproducibility():
    data = rows()
    for r in data:
        if r["method"] == "hipporag2":
            r["metrics"]["em"] += 0.5
            r["metrics"]["f1"] += 0.5
    report = e3.analyze(data, "synthetic", ["a", "b", "c"])
    assert report == e3.analyze(list(reversed(data)), "synthetic", ["a", "b", "c"])
    assert all(
        r["mean"] == 0.5 and r["ci95"] == [0.5, 0.5]
        for r in report["paired_differences"]
        if r["left"] == "hipporag2" and r["metric"] in ("em", "f1")
    )


@pytest.mark.parametrize(
    "fault", ["duplicate", "missing", "extra", "not_attempted", "null", "raptor_metric"]
)
def test_strict_ID_and_metric_gate(fault):
    data = rows()
    if fault == "duplicate":
        data.append(copy.deepcopy(data[0]))
    elif fault == "missing":
        data.pop()
    elif fault == "extra":
        data[0]["question_id"] = "other"
    elif fault == "not_attempted":
        data[0]["status"] = "not_attempted"
    elif fault == "null":
        data[0]["metrics"]["em"] = None
    else:
        data[-1]["metrics"]["passage_recall_at_5"] = 1.0
    with pytest.raises(ValueError):
        e3.analyze(data, "synthetic", ["a", "b", "c"])


def test_failed_pipeline_zero_and_incomplete_retrieval_preserved():
    data = rows()
    data[0].update(status="attempted_failed")
    data[0]["metrics"].update(em=0, f1=0, passage_recall_at_5=None)
    result = e3.analyze(data, "synthetic", ["a", "b", "c"])
    metric = result["rows"][0]["metrics"]["passage_recall_at_5"]
    assert metric["known_cases"] == 2 and metric["ci95"] is None
    assert result["rows"][0]["attempted_failed"] == 1


def test_existing_CLI_reproducible_and_zero_HTTP(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("HTTP forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)

    def source(root, data, dataset):
        selected = rows()
        for r in selected:
            r["dataset"] = dataset
        return (
            selected,
            ["a", "b", "c"],
            {"reader": {"version": "fixed"}, "files": {}, "unknown_usage": None},
        )

    monkeypatch.setattr(e3, "load_dataset", source)
    results = []
    for name in ("one", "two"):
        prefix = tmp_path / name
        e3.main(
            [
                "--artifact-root",
                str(tmp_path),
                "--data-root",
                str(tmp_path),
                "--output",
                str(prefix),
            ]
        )
        results.append(dense.read_json(prefix.with_suffix(".json")))
    assert results[0] == results[1]
    assert results[0]["bootstrap"]["samples"] == 1000
    assert results[0]["bootstrap"]["seed"] == 42


def test_missing_terminal_input_never_publishes_full_E3(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("HTTP forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    with pytest.raises(FileNotFoundError):
        e3.main(
            [
                "--artifact-root",
                str(tmp_path),
                "--data-root",
                str(tmp_path),
                "--output",
                str(tmp_path / "final"),
            ]
        )
    assert not (tmp_path / "final.json").exists()


def test_loader_and_CLI_reject_changed_recall_before_publishing(tmp_path, monkeypatch):
    """Keep answers/saved cases fixed; tamper only temporary evaluation metrics."""

    def forbidden(*a, **kw):
        raise AssertionError("HTTP forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    dataset = "musique"
    ids = [f"q{i}" for i in range(500)]
    labels = [{"id": q, "answer": "Paris", "supporting_ids": ["p0", "p1"]} for q in ids]
    labels_path = tmp_path / "data/processed/musique/labels.json"
    dense.write_json_atomic(labels_path, labels)
    dense.write_json_atomic(
        tmp_path / "data/ids/musique_s500.json", {"question_ids": ids}
    )
    plan = {
        "datasets": {
            dataset: {
                "question_ids": ids,
                "labels_sha256_evaluator_only": dense.sha256_file(labels_path),
            }
        },
        **{
            k: "synthetic"
            for k in (
                "reader_model",
                "reader_version",
                "reader_options",
                "message_utf8_bytes_limit",
                "embedding_model",
                "embedding_digest",
            )
        },
    }
    plan_path = tmp_path / ".cache/e2-musique-s500-unattempted-plan.json"
    dense.write_json_atomic(plan_path, plan)
    output = tmp_path / "results/raw/e2-musique-s500-unattempted-v1"
    manifest = {
        "status": "completed",
        "run_id": "synthetic",
        "plan_sha256": e3.e2.target.digest(plan),
        "results": {},
    }
    details = []
    for method in e3.METHODS:
        for q, label in zip(ids, labels, strict=True):
            failed = method == "hipporag2" and q == "q0"
            saved = {
                "dataset": dataset,
                "method": method,
                "question_id": q,
                "status": "attempted_failed" if failed else "completed",
                "answer": "" if failed else "Paris",
                "retrieval": {} if failed else {"source_ids": ["p0"]},
            }
            key = e3.e2.case_key(dataset, method, q)
            path = output / f"question-{key}.json"
            dense.write_json_atomic(path, saved)
            manifest["results"][key] = dense.sha256_file(path)
            details.append({**saved, "metrics": e3.e2.score_result(saved, label)})
    manifest_path = output / "manifest.json"
    dense.write_json_atomic(manifest_path, manifest)
    (output / "usage.jsonl").write_text("", encoding="utf-8")
    evaluation = {
        "run_id": "synthetic",
        "comparison_complete": True,
        "question_results": details,
    }
    evaluation_path = output / "evaluation.json"
    dense.write_json_atomic(evaluation_path, evaluation)
    dense.write_json_atomic(
        tmp_path / "results/summary/e2-musique-s500.json",
        {
            "status": "completed",
            "run_id": "synthetic",
            "comparison_complete": True,
            "plan_sha256": dense.sha256_file(plan_path),
            "manifest_sha256": dense.sha256_file(manifest_path),
            "new_physical_accounting": {},
            "historical_source_accounting": {},
            "cost_complete": True,
        },
    )
    # Synthetic transport receipts; metric computation and saved-file SHA are real.
    monkeypatch.setattr(e3.e2, "check_parent_pins", lambda p: None)
    monkeypatch.setattr(
        e3.accounting, "verified_reference", lambda *a: {"status": "verified"}
    )
    monkeypatch.setattr(e3.e2, "verify_saved_case", lambda *a: None)
    loaded, loaded_ids, _ = e3.load_dataset(tmp_path, tmp_path, dataset)
    assert loaded_ids == ids and len(loaded) == 1500
    assert loaded[0]["metrics"]["passage_recall_at_5"] == 0.5
    assert loaded[500]["metrics"]["passage_recall_at_5"] == 0
    assert loaded[1000]["metrics"]["passage_recall_at_5"] is None
    for i, changed in ((0, 0.75), (501, 0.75), (500, 0.25), (1, None)):
        original = details[i]["metrics"]["passage_recall_at_5"]
        details[i]["metrics"]["passage_recall_at_5"] = changed
        dense.write_json_atomic(evaluation_path, evaluation)
        prefix = tmp_path / f"rejected-{i}"
        with pytest.raises(ValueError, match="common_evaluator_score_mismatch"):
            e3.main(
                [
                    "--artifact-root",
                    str(tmp_path),
                    "--data-root",
                    str(tmp_path),
                    "--output",
                    str(prefix),
                ]
            )
        assert not prefix.with_suffix(".json").exists()
        assert not prefix.with_suffix(".md").exists()
        details[i]["metrics"]["passage_recall_at_5"] = original
