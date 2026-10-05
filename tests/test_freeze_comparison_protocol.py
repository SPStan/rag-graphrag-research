"""Offline checks for the pinned comparison views and usage audit."""

import hashlib
import json
import sys
from pathlib import Path
import pytest

from scripts.freeze_comparison_protocol import audit_usage, freeze, main, make_split


def source(dataset):
    ids = [f"{dataset}-{i}" for i in range(500)]
    return {
        "dataset": dataset,
        "seed": 42,
        "source_revision": "fixture-revision",
        "question_ids": ids,
        "views": {"pilot200": ids[:200], "holdout100": ids[400:]},
    }


def dump(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_split_preserves_pilot_and_separates_signal_check_from_legacy_holdout():
    item = source("musique")
    split = make_split(item, "source-sha")
    assert split["pilot200_ids"] == item["question_ids"][:200]
    assert split["signal_tuning_ids"] == item["question_ids"][:300]
    assert split["signal_check_ids"] == item["question_ids"][300:400]
    assert split["legacy_holdout_reserved_ids"] == item["question_ids"][400:]


@pytest.mark.parametrize("damage", ["duplicate", "pilot", "holdout", "seed"])
def test_split_rejects_changed_source(damage):
    item = source("hotpotqa")
    if damage == "duplicate":
        item["question_ids"][1] = item["question_ids"][0]
    elif damage == "pilot":
        item["views"]["pilot200"][0] = "changed"
    elif damage == "holdout":
        item["views"]["holdout100"][0] = "changed"
    else:
        item["seed"] = 43
    with pytest.raises(ValueError):
        make_split(item, "source-sha")


def test_audit_distinguishes_planned_from_observed_and_keeps_only_positions(tmp_path):
    raw = tmp_path / "raw"
    summary = tmp_path / "summary"
    raw.mkdir()
    summary.mkdir()
    dump(
        raw / "r.manifest.json",
        {
            "dataset": "musique",
            "run_id": "r",
            "expected_question_ids": ["musique-0", "musique-300"],
        },
    )
    record = {
        "dataset": "musique",
        "run_id": "r",
        "question_id": "musique-0",
        "question": "PRIVATE QUESTION",
        "answer": "PRIVATE ANSWER",
    }
    (raw / "r.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    dump(summary / "old.json", {"run_id": "r"})
    report = audit_usage(
        {name: source(name) for name in ("musique", "hotpotqa")}, raw, summary
    )
    assert report["totals"]["musique"] == {
        "observed_s500": 1,
        "planned_s500": 2,
        "signal_check_observed": 0,
        "signal_check_planned": 1,
    }
    assert report["runs"][0]["observed_positions"] == [0]
    assert report["runs"][0]["planned_positions"] == [0, 300]
    assert "PRIVATE" not in json.dumps(report)
    assert report["published_summaries"][0]["file"] == "old.json"
    assert report["published_summaries"][0]["referenced_run_ids"] == ["r"]


def test_freeze_refuses_planned_signal_check_and_detects_tampering(tmp_path):
    ids_dir, raw, summary = (tmp_path / name for name in ("ids", "raw", "summary"))
    for directory in (ids_dir, raw, summary):
        directory.mkdir()
    for name in ("musique", "hotpotqa"):
        dump(ids_dir / f"{name}_s500.json", source(name))
    dump(
        raw / "r.manifest.json",
        {"dataset": "musique", "run_id": "r", "expected_question_ids": ["musique-300"]},
    )
    with pytest.raises(ValueError, match="Signal check IDs"):
        freeze(ids_dir, raw, summary)
    dump(
        raw / "r.manifest.json",
        {"dataset": "musique", "run_id": "r", "expected_question_ids": ["musique-0"]},
    )
    freeze(ids_dir, raw, summary)
    freeze(ids_dir, raw, summary, verify_only=True)
    split_path = ids_dir / "musique_comparison_split.json"
    split_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen file differs"):
        freeze(ids_dir, raw, summary, verify_only=True)
    with pytest.raises(ValueError, match="Frozen file differs"):
        freeze(ids_dir, raw, summary, verify_only=True, splits_only=True)


def test_freeze_refuses_signal_check_id_mentioned_in_tracked_doc(tmp_path):
    ids_dir = tmp_path / "data" / "ids"
    raw = tmp_path / "results" / "raw"
    summary = tmp_path / "results" / "summary"
    docs = tmp_path / "docs"
    for directory in (ids_dir, raw, summary, docs):
        directory.mkdir(parents=True)
    for name in ("musique", "hotpotqa"):
        dump(ids_dir / f"{name}_s500.json", source(name))
    dump(
        raw / "r.manifest.json",
        {"dataset": "musique", "run_id": "r", "expected_question_ids": ["musique-0"]},
    )
    (docs / "example.md").write_text("musique-300", encoding="utf-8")
    with pytest.raises(ValueError, match="tracked docs"):
        freeze(ids_dir, raw, summary, docs_dir=docs)


def test_audit_rejects_missing_docs_directory(tmp_path):
    raw, summary = (tmp_path / name for name in ("raw", "summary"))
    raw.mkdir()
    summary.mkdir()
    with pytest.raises(ValueError, match="existing docs"):
        audit_usage(
            {name: source(name) for name in ("musique", "hotpotqa")},
            raw,
            summary,
            docs_dir=tmp_path / "missing-docs",
        )


def test_cli_audits_explicit_docs_when_summary_is_elsewhere(tmp_path, monkeypatch):
    ids_dir = tmp_path / "project" / "data" / "ids"
    docs_dir = tmp_path / "project" / "docs"
    raw = tmp_path / "elsewhere" / "raw"
    summary = tmp_path / "elsewhere" / "summary"
    for directory in (ids_dir, docs_dir, raw, summary):
        directory.mkdir(parents=True)
    for name in ("musique", "hotpotqa"):
        dump(ids_dir / f"{name}_s500.json", source(name))
    dump(
        raw / "r.manifest.json",
        {"dataset": "musique", "run_id": "r", "expected_question_ids": ["musique-0"]},
    )
    (docs_dir / "example.md").write_text("musique-300", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "freeze_comparison_protocol.py",
            "--ids-dir",
            str(ids_dir),
            "--raw-dir",
            str(raw),
            "--summary-dir",
            str(summary),
            "--docs-dir",
            str(docs_dir),
        ],
    )
    with pytest.raises(ValueError, match="tracked docs"):
        main()
    assert not list(summary.glob("question-usage-audit*.json"))


def test_published_splits_verify_without_private_data():
    root = Path(__file__).resolve().parents[1]
    freeze(
        root / "data/ids",
        root / "results/raw",
        root / "results/summary",
        verify_only=True,
        splits_only=True,
    )


def test_missing_raw_is_not_empty_history(tmp_path):
    summary = tmp_path / "summary"
    summary.mkdir()
    with pytest.raises(ValueError, match="existing raw"):
        audit_usage(
            {name: source(name) for name in ("musique", "hotpotqa")},
            tmp_path / "missing",
            summary,
        )


def test_freeze_does_not_overwrite_history_implicitly(tmp_path):
    ids_dir, raw, summary = (tmp_path / name for name in ("ids", "raw", "summary"))
    for directory in (ids_dir, raw, summary):
        directory.mkdir()
    for name in ("musique", "hotpotqa"):
        dump(ids_dir / f"{name}_s500.json", source(name))
    with pytest.raises(ValueError, match="empty history"):
        freeze(ids_dir, raw, summary)
    manifest = {
        "dataset": "musique",
        "run_id": "r",
        "expected_question_ids": ["musique-0"],
    }
    dump(raw / "r.manifest.json", manifest)
    freeze(ids_dir, raw, summary)
    snapshot = {
        p: p.read_bytes()
        for p in [*ids_dir.glob("*split.json"), summary / "question-usage-audit.json"]
    }
    manifest["expected_question_ids"] = ["musique-1"]
    dump(raw / "r.manifest.json", manifest)
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        freeze(ids_dir, raw, summary)
    assert all(path.read_bytes() == value for path, value in snapshot.items())
    freeze(ids_dir, raw, summary, refresh_audit=True)
    assert all(path.read_bytes() == value for path, value in snapshot.items())
    current = json.loads(
        (summary / "question-usage-audit-current.json").read_text(encoding="utf-8")
    )
    assert (
        current["baseline_audit_sha256"]
        == hashlib.sha256(snapshot[summary / "question-usage-audit.json"]).hexdigest()
    )
    assert current["runs"][0]["planned_positions"] == [1]
    freeze(ids_dir, raw, summary, verify_only=True, splits_only=True)
    split = ids_dir / "musique_comparison_split.json"
    split.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        freeze(ids_dir, raw, summary, refresh_audit=True)


def test_postrun_audit_records_signal_check_without_rewriting_precheck(tmp_path):
    ids_dir, raw, summary = (tmp_path / name for name in ("ids", "raw", "summary"))
    for directory in (ids_dir, raw, summary):
        directory.mkdir()
    for name in ("musique", "hotpotqa"):
        dump(ids_dir / f"{name}_s500.json", source(name))
    manifest = {
        "dataset": "musique",
        "run_id": "r",
        "expected_question_ids": ["musique-0"],
    }
    dump(raw / "r.manifest.json", manifest)
    freeze(ids_dir, raw, summary)
    baseline_path = summary / "question-usage-audit.json"
    baseline_bytes = baseline_path.read_bytes()

    manifest["expected_question_ids"] = ["musique-0", "musique-300"]
    dump(raw / "r.manifest.json", manifest)
    (raw / "r.jsonl").write_text(
        json.dumps(
            {
                "dataset": "musique",
                "run_id": "r",
                "question_id": "musique-300",
                "answer": "PRIVATE ANSWER",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Signal check IDs"):
        freeze(ids_dir, raw, summary, verify_only=True)
    freeze(ids_dir, raw, summary, refresh_audit=True)
    current_path = summary / "question-usage-audit-current.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    assert baseline_path.read_bytes() == baseline_bytes
    assert current["audit_phase"] == "postrun"
    assert (
        current["baseline_audit_sha256"] == hashlib.sha256(baseline_bytes).hexdigest()
    )
    assert current["totals"]["musique"]["signal_check_planned"] == 1
    assert current["totals"]["musique"]["signal_check_observed"] == 1
    assert "PRIVATE" not in current_path.read_text(encoding="utf-8")
    freeze(ids_dir, raw, summary, verify_only=True, splits_only=True)
