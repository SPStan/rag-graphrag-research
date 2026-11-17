"""Strict paired oracle validation and the public offline CLI."""

import copy
import inspect
import json
import socket

import pytest

from scripts import analyze_oracle as oracle


def rows(dataset="synthetic", ids=("a", "b", "c", "d")):
    return [
        {
            "dataset": dataset,
            "method": method,
            "question_id": qid,
            "status": "completed",
            "metrics": {"em": em, "f1": f1},
        }
        for method, ems, f1s in (
            ("dense", [1, 0, 0, 0], [1, 0, 0.5, 0]),
            ("hipporag2", [0, 1, 0, 0], [0, 1, 0.5, 0]),
        )
        for qid, em, f1 in zip(ids, ems, f1s)
    ]


def test_control_example_and_independent_em_oracle():
    result = oracle.analyze(rows(), "synthetic", ["a", "b", "c", "d"])
    f1 = result["metrics"]["f1"]
    assert (f1["dense"], f1["hipporag2"], f1["oracle"]) == (0.375, 0.375, 0.625)
    assert f1["oracle_minus_dense_pp"] == f1["oracle_minus_hippo_pp"] == 25
    assert result["metrics"]["em"]["oracle"] == 0.5
    assert result["em_groups"] == {
        "both_correct": {"count": 0, "fraction": 0},
        "dense_only": {"count": 1, "fraction": 0.25},
        "hippo_only": {"count": 1, "fraction": 0.25},
        "both_wrong": {"count": 2, "fraction": 0.5},
    }
    changed = rows()
    changed[2]["metrics"]["em"] = changed[6]["metrics"]["em"] = 1
    assert all(
        x["count"] == 1
        for x in oracle.analyze(changed, "synthetic", ["a", "b", "c", "d"])[
            "em_groups"
        ].values()
    )


def test_row_order_does_not_matter():
    assert oracle.analyze(rows(), "synthetic", list("abcd")) == oracle.analyze(
        list(reversed(rows())), "synthetic", list("abcd")
    )


@pytest.mark.parametrize(
    "fault",
    [
        "duplicate",
        "missing",
        "extra",
        "dataset",
        "method",
        "expected_duplicate",
        "empty",
        "status",
    ],
)
def test_id_gate(fault):
    data, ids = rows(), list("abcd")
    if fault == "duplicate":
        data.append(copy.deepcopy(data[0]))
    elif fault == "missing":
        data.pop()
    elif fault == "extra":
        data[0]["question_id"] = "other"
    elif fault == "dataset":
        data[0]["dataset"] = "other"
    elif fault == "method":
        data[0]["method"] = "raptor"
    elif fault == "expected_duplicate":
        ids.append("a")
    elif fault == "empty":
        ids = []
    else:
        data[0]["status"] = "not_attempted"
    with pytest.raises(ValueError):
        oracle.analyze(data, "synthetic", ids)


@pytest.mark.parametrize(
    "field,value",
    [
        ("em", 0.5),
        ("em", True),
        ("em", None),
        ("f1", float("nan")),
        ("f1", float("inf")),
        ("f1", -0.1),
        ("f1", 1.1),
        ("f1", None),
        ("f1", True),
    ],
)
def test_score_gate(field, value):
    data = rows()
    data[0]["metrics"][field] = value
    with pytest.raises(ValueError, match="invalid_scores"):
        oracle.analyze(data, "synthetic", list("abcd"))


def test_failure_zero_is_retained_not_dropped():
    data = rows()
    data[0]["status"] = "attempted_failed"
    with pytest.raises(ValueError, match="failure_score_changed"):
        oracle.analyze(data, "synthetic", list("abcd"))
    data[0]["metrics"] = {"em": 0, "f1": 0}
    result = oracle.analyze(data, "synthetic", list("abcd"))
    assert result["n"] == 4
    assert result["outcomes"]["dense"]["attempted_failed"] == 1


def test_existing_cli_rebuild_private_binding_and_no_public_scores(
    tmp_path, monkeypatch
):
    ids = [f"private-{i}" for i in range(500)]
    all_rows, metadata = [], {}
    for dataset in oracle.DATASETS:
        data = []
        for method in oracle.e3.METHODS:
            for qid in ids:
                data.append(
                    {
                        "dataset": dataset,
                        "method": method,
                        "question_id": qid,
                        "status": "completed",
                        "metrics": {"em": 0, "f1": 0, "passage_recall_at_5": None},
                    }
                )
        all_rows.extend(data)
        metadata[dataset] = {"files": {}, "run_id": dataset, "reader": {}}
    ledger = {
        "question_scores": all_rows,
        "question_scores_sha256": oracle.e3.e2.target.digest(all_rows),
        "metric_function_sha256": oracle.e3.e2.target.digest(
            inspect.getsource(oracle.e3.e2.score_result)
        ),
        "inputs": metadata,
    }
    ledger_path = tmp_path / "private.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    def load(*args):
        with pytest.raises(AssertionError, match="oracle_network_forbidden"):
            socket.socket().connect(("localhost", 9))
        dataset = args[-1]
        return [r for r in all_rows if r["dataset"] == dataset], ids, metadata[dataset]

    monkeypatch.setattr(oracle.e3, "load_dataset", load)
    outputs = [tmp_path / "one.json", tmp_path / "two.json"]
    for output in outputs:
        oracle.main(
            [
                "--artifact-root",
                str(tmp_path),
                "--data-root",
                str(tmp_path),
                "--ledger",
                str(ledger_path),
                "--output",
                str(output),
            ]
        )
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    report = json.loads(outputs[0].read_text())
    assert all(d["n"] == 500 for d in report["datasets"])
    assert "private-0" not in outputs[0].read_text()
    ledger["question_scores"][0]["metrics"]["f1"] = 0.5
    ledger["question_scores_sha256"] = oracle.e3.e2.target.digest(
        ledger["question_scores"]
    )
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    # Simulate a ledger modified independently from the verified saved outcomes.
    monkeypatch.setattr(
        oracle.e3,
        "load_dataset",
        lambda *a: (
            [
                dict(r, metrics=dict(r["metrics"], f1=0))
                for r in all_rows
                if r["dataset"] == a[-1]
            ],
            ids,
            metadata[a[-1]],
        ),
    )
    with pytest.raises(ValueError, match="private_ledger_saved_score_mismatch"):
        oracle.main(
            [
                "--artifact-root",
                str(tmp_path),
                "--data-root",
                str(tmp_path),
                "--ledger",
                str(ledger_path),
                "--output",
                str(outputs[0]),
            ]
        )
