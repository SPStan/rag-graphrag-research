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
        lines = prefix.with_suffix(".md").read_text(encoding="utf-8").splitlines()
        start = next(i for i, line in enumerate(lines) if line.startswith("| Dataset"))
        table = lines[start : start + 8]
        assert len(table) == 8 and all(line.startswith("|") for line in table)
        assert "\u2212Dense" in "\n".join(lines[start + 8 :])
        assert "\u0432\u20ac\u2019Dense" not in "\n".join(lines)
        assert sum(line.startswith("| musique |") for line in table) == 3
        assert sum(line.startswith("| hotpotqa |") for line in table) == 3
        assert all("−Dense" not in line for line in lines[: start + 8])

    assert results[0] == results[1]
    assert results[0]["bootstrap"]["samples"] == 1000
    assert results[0]["bootstrap"]["seed"] == 42
    assert len(results[0]["question_scores"]) == 18
    assert results[0]["question_scores_sha256"] == e3.e2.target.digest(
        results[0]["question_scores"]
    )
    assert all(
        set(r)
        == {"dataset", "method", "question_id", "status", "pipeline_failure", "metrics"}
        for r in results[0]["question_scores"]
    )


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


@pytest.fixture
def saved_inputs(tmp_path, monkeypatch):
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
    plan.update({k: plan.get(k, "synthetic") for k in e3.full.CONTRACT})
    plan.update(
        top_k=5,
        version="e2-musique-s500-v1",
        e1_plan=str(tmp_path / "e1.json"),
        s500={"source_global_cost": {}},
        parent_run={"cases": {}, "files": {}},
    )
    dense.write_json_atomic(tmp_path / "e1.json", {"data_root": str(tmp_path)})
    data = plan["datasets"][dataset]
    data["indexes"] = []
    data.update(
        ordered_ids_sha256=e3.e2.target.digest(ids),
        queries_sha256="queries",
        corpus_sha256="corpus",
        split_sha256="split",
    )
    frozen = {
        "configurations": [],
        "contract": e3.full.contract(plan),
        "input_message_bytes_limit": plan["message_utf8_bytes_limit"],
        "datasets": {
            dataset: {
                "ordered_ids": ids,
                "ordered_ids_sha256": data["ordered_ids_sha256"],
                "queries_sha256": "queries",
                "corpus_sha256": "corpus",
                "split_file_sha256": "split",
                "labels_sha256_hash_only": data["labels_sha256_evaluator_only"],
            }
        },
        **{
            k: {}
            for k in (
                "pilot_physical",
                "development_physical",
                "E1_separate",
                "sealed_unknown",
            )
        },
    }
    plan["s500"]["source_global_cost"] = {
        k: frozen[k]
        for k in (
            "pilot_physical",
            "development_physical",
            "E1_separate",
            "sealed_unknown",
        )
    }
    plan["s500"]["source_digest"] = e3.e2.target.digest(frozen)
    dense.write_json_atomic(tmp_path / "results/summary/full-experiment.json", frozen)
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
                "wall_seconds": 1.0,
                "operations": [],
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
    journal_path = output / "usage.jsonl"
    # Real journal/reference and real summary; only absent transport checkpoints
    # are stubbed in this metric fixture (runner tests cover their own verification).
    manifest["token_accounting"] = {
        "journal_file": "usage.jsonl",
        "journal_sha256": dense.sha256_file(journal_path),
        "summary": e3.accounting.summarize(e3.accounting.read_records(journal_path)),
    }
    dense.write_json_atomic(manifest_path, manifest)
    evaluation = e3.e2.summary(plan, output)
    details = evaluation["question_results"]
    evaluation_path = output / "evaluation.json"
    dense.write_json_atomic(evaluation_path, evaluation)
    public_path = tmp_path / "results/summary/e2-musique-s500.json"
    public = {
        "status": "completed",
        "run_id": "synthetic",
        "comparison_complete": True,
        "plan_sha256": dense.sha256_file(plan_path),
        "manifest_sha256": dense.sha256_file(manifest_path),
        "rows": evaluation["rows"],
        "new_physical_accounting": manifest["token_accounting"]["summary"],
        "historical_source_accounting": plan["s500"]["source_global_cost"],
        "new_POST": 0,
        "model_posts": 0,
        "inherited_cases": 0,
        "new_terminal_cases": 1500,
        "cost_complete": True,
    }
    dense.write_json_atomic(public_path, public)
    monkeypatch.setattr(e3.e2, "verify_saved_case", lambda *a: None)
    return plan_path, manifest_path, evaluation_path, public_path


def test_loader_and_CLI_reject_changed_recall_before_publishing(tmp_path, saved_inputs):
    _, _, evaluation_path, _ = saved_inputs
    dataset = "musique"
    evaluation = dense.read_json(evaluation_path)
    details = evaluation["question_results"]
    ids = [f"q{i}" for i in range(500)]
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


@pytest.mark.parametrize(
    "field",
    [
        "top_k",
        "hippo",
        "reader_options",
        "context_order",
        "embedding_digest",
        "message_utf8_bytes_limit",
    ],
)
def test_CLI_rejects_protocol_changes_even_with_rebound_SHA(
    tmp_path, saved_inputs, field
):
    plan_path, manifest_path, _, public_path = saved_inputs
    plan = dense.read_json(plan_path)
    plan[field] = 7 if field == "top_k" else "changed"
    dense.write_json_atomic(plan_path, plan)
    manifest = dense.read_json(manifest_path)
    manifest["plan_sha256"] = e3.e2.target.digest(plan)
    dense.write_json_atomic(manifest_path, manifest)
    public = dense.read_json(public_path)
    public.update(
        plan_sha256=dense.sha256_file(plan_path),
        manifest_sha256=dense.sha256_file(manifest_path),
    )
    dense.write_json_atomic(public_path, public)
    with pytest.raises(ValueError, match="frozen_"):
        e3.main(
            [
                "--artifact-root",
                str(tmp_path),
                "--data-root",
                str(tmp_path),
                "--output",
                str(tmp_path / "rejected"),
            ]
        )
    assert not (tmp_path / "rejected.json").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "f1",
        "completed",
        "logical_usage",
        "known_tokens",
        "POST",
        "source_cost",
        "coverage",
        "complete",
        "evaluation_count",
    ],
)
def test_CLI_rejects_aggregate_or_expense_tampering(tmp_path, saved_inputs, fault):
    _, _, evaluation_path, public_path = saved_inputs
    public = dense.read_json(public_path)
    if fault == "f1":
        public["rows"][0]["f1"] = 0.75
    elif fault == "completed":
        public["rows"][0]["completed"] -= 1
    elif fault == "logical_usage":
        public["rows"][0]["usage_by_operation"] = {"reader": {"calls": 3}}
    elif fault == "known_tokens":
        public["new_physical_accounting"]["known_subtotal"]["llm_input_tokens"] = 999
    elif fault == "POST":
        public["new_POST"] += 1
    elif fault == "source_cost":
        public["historical_source_accounting"]["pilot_physical"] = {"invented": 999}
    elif fault == "coverage":
        public["new_terminal_cases"] -= 1
    elif fault == "complete":
        public["cost_complete"] = False
    else:
        evaluation = dense.read_json(evaluation_path)
        evaluation["rows"][0]["completed"] -= 1
        dense.write_json_atomic(evaluation_path, evaluation)
    dense.write_json_atomic(public_path, public)
    with pytest.raises(ValueError, match="(public_|evaluation_rebuild_)"):
        e3.main(
            [
                "--artifact-root",
                str(tmp_path),
                "--data-root",
                str(tmp_path),
                "--output",
                str(tmp_path / "rejected"),
            ]
        )
    assert not (tmp_path / "rejected.json").exists()


def test_CLI_blocks_network_even_when_called_without_external_patch(
    tmp_path, monkeypatch
):
    def tries_network(*args):
        socket.socket().connect(("127.0.0.1", 9))

    monkeypatch.setattr(e3, "build", tries_network)
    with pytest.raises(AssertionError, match="E3_network_forbidden"):
        e3.main(
            [
                "--artifact-root",
                str(tmp_path),
                "--data-root",
                str(tmp_path),
                "--output",
                str(tmp_path / "network"),
            ]
        )
    assert not (tmp_path / "network.json").exists()


@pytest.mark.parametrize("usage", [None, {"llm_input_tokens": 50}])
def test_CLI_rejects_new_unknown_or_partial_journal(tmp_path, saved_inputs, usage):
    _, manifest_path, _, public_path = saved_inputs
    journal_path = manifest_path.parent / "unknown.jsonl"
    journal = e3.accounting.Journal(
        journal_path, run_id="synthetic", method="dense", dataset="musique"
    )
    started = journal.start(
        phase="reader",
        operation="reader",
        provider="synthetic",
        model="synthetic",
        kind="llm",
        object_id="unknown",
    )
    journal.finish(started, status="unknown", usage=usage)
    manifest = dense.read_json(manifest_path)
    manifest["token_accounting"] = journal.reference()
    dense.write_json_atomic(manifest_path, manifest)
    # Reader sees the journal named by the manifest; make the fixed physical
    # journal agree, so rejection concerns unknown usage rather than a hash error.
    (manifest_path.parent / "usage.jsonl").write_bytes(journal_path.read_bytes())
    manifest["token_accounting"]["journal_file"] = "usage.jsonl"
    dense.write_json_atomic(manifest_path, manifest)
    public = dense.read_json(public_path)
    public["manifest_sha256"] = dense.sha256_file(manifest_path)
    dense.write_json_atomic(public_path, public)
    with pytest.raises(ValueError, match="new_unknown_or_incomplete_usage"):
        e3.main(
            [
                "--artifact-root",
                str(tmp_path),
                "--data-root",
                str(tmp_path),
                "--output",
                str(tmp_path / "unknown"),
            ]
        )
    assert not (tmp_path / "unknown.json").exists()


def test_public_CLI_never_exports_control_or_reserved_scores(tmp_path, monkeypatch):
    ids = [f"q{i}" for i in range(500)]

    def source(root, data, dataset):
        selected = []
        for method in e3.METHODS:
            for qid in ids:
                selected.append(
                    {
                        "dataset": dataset,
                        "method": method,
                        "question_id": qid,
                        "status": "completed",
                        "metrics": {
                            "em": 0.5,
                            "f1": 0.5,
                            "passage_recall_at_5": None if method == "raptor" else 0.5,
                            "supporting_provenance_coverage": 0.5,
                        },
                    }
                )
        return selected, ids, {"reader": {}, "files": {}}

    monkeypatch.setattr(e3, "load_dataset", source)
    prefix = tmp_path / "public"
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
    public = dense.read_json(prefix.with_suffix(".json"))
    assert len(public["question_scores"]) == 1800
    assert {r["question_id"] for r in public["question_scores"]} == set(ids[:300])
    assert not {r["question_id"] for r in public["question_scores"]} & set(ids[300:])
    assert all(x["n"] == 500 for x in public["datasets"])
    assert all(r["completed"] == 500 for x in public["datasets"] for r in x["rows"])
    assert public["question_scores_scope"].startswith("tuning300_only")
    assert (
        e3.e2.target.digest(public["question_scores"])
        == public["question_scores_sha256"]
    )
