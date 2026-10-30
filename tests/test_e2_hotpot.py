"""Hot binding exercises the existing CLI; all HTTP is synthetic."""

import copy
from pathlib import Path
import pytest
import test_e2_continuation as continuation
from scripts import (
    e2_evaluation as e2,
    e2_hotpot as hot,
    e2_s500 as shared,
    run_dense as dense,
)

scenario = continuation.scenario


@pytest.fixture
def approved(scenario, monkeypatch):
    s = scenario
    parent = dense.read_json(s.parent_plan)
    parent.update(
        reader_version="shared-answer-only-v1",
        outcome_policy=e2.OUTCOME_POLICY,
        message_utf8_bytes_limit=65536,
    )
    parent["datasets"] = {"hotpotqa": parent["datasets"]["hotpotqa"]}
    parent["datasets"]["hotpotqa"]["question_ids"] = ["q0", "q1", "q2"]
    raw = s.root / "data/processed/hotpotqa/queries.json"
    parent["datasets"]["hotpotqa"]["queries_sha256"] = continuation.runner.digest(
        dense.read_json(raw)[:3]
    )
    source_plan = s.root / "hot-source-plan.json"
    dense.write_json_atomic(source_plan, parent)
    source = s.root / "hot-source"
    s.state["reader_outcomes"] = ["stop", "stop", "length"]
    with monkeypatch.context() as setup:
        setup.setattr(e2, "verify", lambda p: True)
        e2.execute(
            source_plan,
            source,
            "dense",
            approved_sha=dense.sha256_file(source_plan),
            config=s.config,
        )
    manifest = dense.read_json(source / "manifest.json")
    refs = e2.result_references(parent, manifest, source)
    cases = {
        k: {"path": str(p), "sha256": sha, "status": dense.read_json(p)["status"]}
        for k, (p, sha) in refs.items()
    }
    pins = {str(p): dense.sha256_file(p) for p in source.rglob("*") if p.is_file()}
    pins[str(source_plan)] = dense.sha256_file(source_plan)
    plan = copy.deepcopy(parent)
    plan["sealed_unknown"] = []
    plan["datasets"]["hotpotqa"]["question_ids"] = [f"q{i}" for i in range(5)]
    plan["datasets"]["hotpotqa"]["queries_sha256"] = continuation.runner.digest(
        dense.read_json(raw)[:5]
    )
    auth = s.root / "auth.json"
    dense.write_json_atomic(auth, dense.read_json(hot.AUTHORIZATION))
    history = s.root / "history.json"
    dense.write_json_atomic(
        history, {"cumulative_E2_accounting": {"known": 123, "unknown": 2}}
    )
    pins[str(history)] = dense.sha256_file(history)
    plan.update(
        version=hot.VERSION,
        http_authorized=True,
        max_combined_tokens=hot.TOKEN_CAP,
        max_posts=2100,
        max_llm_posts=1200,
        max_embedding_posts=900,
        reader_calls=900,
        filter_calls=300,
        pilot_reuse={"contexts": {}, "readers": {}, "files": {}},
        parent_run={
            "plan": str(source_plan),
            "directory": str(source),
            "run_id": manifest["run_id"],
            "files": pins,
            "cases": cases,
        },
        s500={
            "worklist": "synthetic",
            "authorization": str(auth),
            "authorization_sha256": dense.sha256_file(auth),
            "source_global_cost": {"reserve": 22545},
            "historical_E2_report": {
                "path": str(history),
                "sha256": dense.sha256_file(history),
            },
        },
    )
    s.child_plan, s.output = s.root / "hot-plan.json", s.root / "hot"
    dense.write_json_atomic(s.child_plan, plan)
    s.frozen = copy.deepcopy(plan)
    s.initial_posts = len(s.state["posts"])
    s.parent_bytes = {p: Path(p).read_bytes() for p in pins}
    monkeypatch.setattr(hot, "EXPECTED_IDS", 5)
    monkeypatch.setattr(shared, "EXPECTED_IDS", 5)
    monkeypatch.setattr(hot, "prepare", lambda *a: copy.deepcopy(s.frozen))
    return s


def test_cli_missing_only_failure_reuse_and_reproducible_report(approved, monkeypatch):
    s = approved
    for m in e2.METHODS:
        continuation.run_method(s, m, monkeypatch)
    n = len(s.state["posts"])
    for m in e2.METHODS:
        continuation.run_method(s, m, monkeypatch)
    assert len(s.state["posts"]) == n
    a = hot.write_report(s.child_plan, s.output, s.root / "report1")
    b = hot.write_report(s.child_plan, s.output, s.root / "report2")
    assert a == b and a["comparison_complete"]
    assert a["terminal_audit"] | {} == b["terminal_audit"]
    assert a["terminal_audit"]["expected"] == 15
    assert sum(r["attempted_failed"] for r in a["rows"]) == 1
    assert all(Path(p).read_bytes() == body for p, body in s.parent_bytes.items())


@pytest.mark.parametrize("fault", ["unknown", "transport", "budget", "model"])
def test_cli_fatal_stops_and_never_retries(approved, monkeypatch, fault):
    s = approved
    s.state["fault"] = fault
    continuation.run_method(s, "dense", monkeypatch)
    assert dense.read_json(s.output / "manifest.json")["status"] == "failed"
    n = len(s.state["posts"])
    with pytest.raises(ValueError, match="failed_or_changed"):
        continuation.run_method(s, "dense", monkeypatch)
    assert len(s.state["posts"]) == n


@pytest.mark.parametrize("change", ["cap", "auth", "parent", "model"])
def test_guard_rejects_before_post(approved, change):
    s = approved
    plan = dense.read_json(s.child_plan)
    if change == "cap":
        plan["max_combined_tokens"] = 1
    elif change == "auth":
        Path(plan["s500"]["authorization"]).write_text("{}", encoding="utf-8")
    elif change == "parent":
        plan["parent_run"]["cases"][e2.case_key("hotpotqa", "dense", "q3")] = {}
    payload = e2.answer_only_payload("Which city?", {"passages": []})
    if change == "model":
        payload["model"] = "wrong"
    calls = e2.Calls(s.output, plan, run_id="guard")
    with pytest.raises(ValueError):
        calls.call(
            payload, method="dense", dataset="hotpotqa", qid="q3", operation="reader"
        )
    assert len(s.state["posts"]) == s.initial_posts


def test_resume_clean_boundary_counter_and_exact_checkpoint_reuse(
    approved, monkeypatch
):
    s = approved
    continuation.run_method(s, "dense", monkeypatch)
    registry = s.root / "recoveries.json"
    dense.write_json_atomic(
        registry,
        {
            "plan_sha256": dense.sha256_file(s.child_plan),
            "output": str(s.output.resolve()),
            "automatic_resumes": 0,
        },
    )
    before = len(s.state["posts"])
    for count in (1, 2):
        assert (
            hot.resume_preflight(s.child_plan, s.output, registry)["automatic_resumes"]
            == count
        )
        continuation.run_method(s, "dense", monkeypatch)
        assert len(s.state["posts"]) == before
    with pytest.raises(ValueError, match="recovery_limit"):
        hot.resume_preflight(s.child_plan, s.output, registry)
    (s.output / "running.lock").write_text("123", encoding="utf-8")
    with pytest.raises(ValueError, match="active_or_stale_lock"):
        hot.resume_preflight(s.child_plan, s.output, registry)


def test_resume_failed_run_and_unbound_checkpoint_forbidden(approved, monkeypatch):
    s = approved
    s.state["fault"] = "transport"
    continuation.run_method(s, "dense", monkeypatch)
    registry = s.root / "recoveries.json"
    dense.write_json_atomic(
        registry,
        {
            "plan_sha256": dense.sha256_file(s.child_plan),
            "output": str(s.output.resolve()),
            "automatic_resumes": 0,
        },
    )
    with pytest.raises(ValueError, match="clean_method_boundary"):
        hot.resume_preflight(s.child_plan, s.output, registry)
    assert dense.read_json(registry)["automatic_resumes"] == 0
