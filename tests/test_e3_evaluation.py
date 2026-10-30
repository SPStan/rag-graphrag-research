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
