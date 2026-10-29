"""S500 uses the existing shared CLI with synthetic clients; no real HTTP."""

import copy
from pathlib import Path

import pytest
import test_e2_continuation as continuation

from scripts import e2_evaluation as e2, e2_s500 as s500, run_dense as dense
from scripts import run_dense_target as runner

scenario = continuation.scenario
pilot_scenario = continuation.pilot_scenario


@pytest.fixture
def approved(pilot_scenario, monkeypatch):
    s = pilot_scenario
    s.state["reader_outcomes"] = []
    s.child_plan, s.output = s.pilot_plan, s.pilot_output
    continuation.run_method(s, "dense", monkeypatch)
    source = dense.read_json(s.output / "manifest.json")
    refs = e2.result_references(s.plan, source, s.output)
    cases = {}
    for qid in ("q0", "q1"):
        key = e2.case_key("musique", "dense", qid)
        path, sha = refs[key]
        cases[key] = {"path": str(path), "sha256": sha, "status": "completed"}
    pins = {str(p): dense.sha256_file(p) for p in s.output.rglob("*") if p.is_file()}
    pins.update(s.plan["pilot_reuse"]["files"])
    pins[str(s.pilot_plan)] = dense.sha256_file(s.pilot_plan)
    plan = copy.deepcopy(s.plan)
    data = plan["datasets"]["musique"]
    data["question_ids"] = [f"q{i}" for i in range(5)]
    raw = s.root / "data/processed/musique/queries.json"
    data["queries_sha256"] = runner.digest(dense.read_json(raw)[:5])
    plan.update(
        version=s500.VERSION,
        datasets={"musique": data},
        http_authorized=True,
        max_combined_tokens=500000,
        max_posts=2100,
        max_llm_posts=1200,
        max_embedding_posts=900,
        reader_calls=900,
        filter_calls=300,
        pilot_reuse={"contexts": {}, "readers": {}, "files": {}},
        parent_run={
            "plan": str(s.pilot_plan),
            "directory": str(s.output),
            "run_id": source["run_id"],
            "files": pins,
            "cases": cases,
        },
        s500={
            "worklist": "synthetic",
            "authorization": "synthetic",
            "source_global_cost": {"historical_unknown": 1, "reserve": 22545},
        },
    )
    s.parent_bytes = {p: Path(p).read_bytes() for p in pins}
    s.child_plan, s.output = s.root / "s500-plan.json", s.root / "s500"
    dense.write_json_atomic(s.child_plan, plan)
    s.frozen = copy.deepcopy(plan)
    monkeypatch.setattr(s500, "EXPECTED_IDS", 5)
    monkeypatch.setattr(s500, "prepare", lambda *a: copy.deepcopy(s.frozen))
    s.initial_posts = len(s.state["posts"])
    return s


def test_actual_runner_only_missing_and_deduplicated_accounting(approved, monkeypatch):
    s = approved
    for method in e2.METHODS:
        continuation.run_method(s, method, monkeypatch)
    manifest = dense.read_json(s.output / "manifest.json")
    assert manifest["status"] == "completed"
    assert len(manifest["results"]) == 13
    assert len(e2.result_references(s.frozen, manifest, s.output)) == 15
    assert len(s.state["posts"]) - s.initial_posts == 31
    posts = len(s.state["posts"])
    for method in e2.METHODS:
        continuation.run_method(s, method, monkeypatch)
    assert len(s.state["posts"]) == posts
    report = s500.write_report(s.child_plan, s.output, s.root / "report")
    assert report["comparison_complete"] and report["new_POST"] == 31
    assert report["historical_source_accounting"]["historical_unknown"] == 1
    assert [r["fresh_e2e_cases"] for r in report["rows"]] == [3, 5, 5]
    assert all(r["completed"] == 5 and r["not_attempted"] == 0 for r in report["rows"])
    assert report["rows"][2]["passage_recall_at_5"] is None
    assert report["new_physical_accounting"]["complete"]
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_dense_target",
            "--shared-plan",
            str(s.child_plan),
            "--output-dir",
            str(s.output),
            "--summarize-shared",
            str(s.root / "cli-report"),
        ],
    )
    runner.main()
    assert dense.read_json(s.root / "cli-report.json")["model_posts"] == 31
    assert all(Path(p).read_bytes() == body for p, body in s.parent_bytes.items())


@pytest.mark.parametrize("fault", ["unknown", "transport", "budget", "model"])
def test_actual_runner_stops_without_retry_and_keeps_usage(
    approved, monkeypatch, fault
):
    s = approved
    s.state["fault"] = fault
    continuation.run_method(s, "dense", monkeypatch)
    manifest = dense.read_json(s.output / "manifest.json")
    assert manifest["status"] == "failed"
    posts = len(s.state["posts"])
    assert posts - s.initial_posts <= 2
    with pytest.raises(ValueError, match="failed_or_changed"):
        continuation.run_method(s, "dense", monkeypatch)
    assert len(s.state["posts"]) == posts
    report = s500.write_report(s.child_plan, s.output, s.root / "interrupted")
    assert report["comparison_complete"] is False
    assert report["rows"][0]["not_attempted"] > 0
    if fault == "unknown":
        assert not report["new_physical_accounting"]["complete"]
        assert sum(report["new_physical_accounting"]["known_subtotal"].values()) > 0


@pytest.mark.parametrize(
    "change", ["reader_options", "index", "code_pin", "parent_pin"]
)
def test_actual_runner_rejects_pins_before_post(approved, monkeypatch, change):
    s = approved
    plan = dense.read_json(s.child_plan)
    if change == "reader_options":
        plan["reader_options"]["max_tokens"] = 1024
    elif change == "index":
        plan["datasets"]["musique"]["indexes"][0]["manifest_sha256"] = "changed"
    elif change == "code_pin":
        plan["code_sha256"]["scripts/run_dense.py"] = "changed"
    else:
        Path(next(iter(plan["parent_run"]["files"]))).write_text(
            "changed", encoding="utf-8"
        )
    dense.write_json_atomic(s.child_plan, plan)
    with pytest.raises(ValueError):
        continuation.run_method(s, "dense", monkeypatch)
    assert len(s.state["posts"]) == s.initial_posts


def test_actual_runner_reader_length_continues_but_filter_failure_stops(
    approved, monkeypatch
):
    s = approved
    s.state["reader_outcomes"] = ["length"]
    continuation.run_method(s, "dense", monkeypatch)
    report = e2.summary(s.frozen, s.output)
    assert report["rows"][0]["attempted_failed"] == 1
    assert report["rows"][0]["completed"] == 4
    s.state["filter_failure"] = True
    continuation.run_method(s, "hipporag2", monkeypatch)
    assert dense.read_json(s.output / "manifest.json")["status"] == "failed"


def test_budget_and_scope_guards_precede_physical_attempt(approved):
    s = approved
    calls = e2.Calls(s.output, s.frozen, run_id="guard-test")
    payload = e2.answer_only_payload("Which city?", {"passages": []})
    for dataset, qid, op, method in [
        ("hotpotqa", "q2", "reader", "dense"),
        ("musique", "q0", "reader", "dense"),
        ("musique", "outside", "reader", "dense"),
        ("musique", "q2", "filter", "dense"),
    ]:
        with pytest.raises(ValueError):
            calls.call(payload, dataset=dataset, qid=qid, operation=op, method=method)
    calls.plan["max_combined_tokens"] = 1
    with pytest.raises(ValueError, match="pre_POST_budget"):
        calls.call(
            payload, dataset="musique", qid="q2", operation="reader", method="dense"
        )
    assert list(calls.directory.glob("*.json")) == []
    assert len(s.state["posts"]) == s.initial_posts


def test_authorization_and_legacy_semantics():
    auth = dense.read_json(s500.AUTHORIZATION)
    s500.validate_authorization(auth)
    with pytest.raises(ValueError):
        s500.validate_authorization({**auth, "new_token_cap": s500.TOKEN_CAP + 1})
    old = "def reader():\n    return 512\n"
    with pytest.raises(ValueError, match="legacy_runner"):
        s500.compatible_runner(old, old.replace("512", "1024"))
    with pytest.raises(ValueError, match="only_frozen"):
        s500.verify({"version": s500.VERSION, "datasets": {"hotpotqa": {}}})


@pytest.mark.parametrize("block", ["worker", "other_directory", "response"])
def test_actual_runner_durable_claims_and_corrupted_response(
    approved, monkeypatch, block
):
    s = approved
    continuation.run_method(s, "dense", monkeypatch)
    posts = len(s.state["posts"])
    if block == "worker":
        (s.output / "running.lock").write_text("123", encoding="utf-8")
    elif block == "other_directory":
        s.output = s.root / "second-output"
    else:
        path = next(s.output.glob("*.response.json"))
        path.write_text("{}", encoding="utf-8")
    with pytest.raises((ValueError, FileExistsError)):
        continuation.run_method(s, "dense", monkeypatch)
    assert len(s.state["posts"]) == posts


def test_execution_preparation_cli_is_offline_and_refuses_changed_plan(
    approved, monkeypatch
):
    from scripts import full_experiment as full

    s = approved
    monkeypatch.setattr(full, "ROOT", s.root)
    source = s.root / full.PLAN
    source.parent.mkdir(parents=True, exist_ok=True)
    dense.write_json_atomic(
        source, {"e1_plan": s.frozen["e1_plan"], "e1_workspace": str(s.root)}
    )
    output = s.root / "execution.json"
    args = [
        "--artifact-root",
        str(s.root),
        "--data-root",
        str(s.root),
        "--index-root",
        str(s.root),
        "--execution-plan",
        str(output),
    ]
    full.main(["prepare-musique-execution", *args])
    full.main(["verify-musique-execution", *args])
    plan = dense.read_json(output)
    plan["max_combined_tokens"] += 1
    dense.write_json_atomic(output, plan)
    with pytest.raises(ValueError, match="cannot_be_overwritten"):
        full.main(["prepare-musique-execution", *args])
    with pytest.raises(ValueError, match="plan_changed"):
        full.main(["verify-musique-execution", *args])
    with pytest.raises(ValueError, match="roots_changed"):
        full.main(
            ["prepare-musique-execution", *args, "--data-root", str(s.root / "other")]
        )
    assert len(s.state["posts"]) == s.initial_posts
