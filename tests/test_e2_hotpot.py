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


def test_prepare_accepts_serialized_string_paths(tmp_path, monkeypatch):
    """verify loads paths from JSON strings, unlike initial default Path."""
    monkeypatch.setattr(hot, "ROOT", tmp_path)
    monkeypatch.setattr(hot, "CODE_FILES", ())
    history = tmp_path / "results/summary/e2-musique-s500.json"
    history.parent.mkdir(parents=True)
    history.write_text("{}", encoding="utf-8")
    auth = tmp_path / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        shared,
        "prepare_dataset",
        lambda *a, **kw: {"parent_run": {"files": {}}, "s500": {}},
    )
    assert hot.prepare("worklist.json", str(auth)) == hot.prepare(
        Path("worklist.json"), auth
    )
    assert hot.prepare("worklist.json", str(auth))["s500"][
        "authorization_sha256"
    ] == dense.sha256_file(auth)


def test_preclaim_code_only_rebind_preserves_budget_and_counter(approved):
    s = approved
    old_path = s.root / "old-plan.json"
    old = copy.deepcopy(s.frozen)
    old["code_sha256"] = {"old": "runtime"}
    dense.write_json_atomic(old_path, old)
    registry = s.root / "rebind.json"
    dense.write_json_atomic(
        registry,
        {
            "plan_sha256": dense.sha256_file(old_path),
            "output": str(s.output.resolve()),
            "automatic_resumes": 0,
        },
    )
    result = hot.admit_preclaim_rebind(old_path, s.child_plan, s.output, registry)
    assert result["automatic_resumes"] == 1
    assert result["admissions"][0]["physical_POST"] == 0
    assert dense.read_json(old_path) == old
    assert (
        dense.read_json(s.child_plan)["max_combined_tokens"]
        == old["max_combined_tokens"]
    )
    with pytest.raises(ValueError, match="registry_mismatch"):
        hot.admit_preclaim_rebind(old_path, s.child_plan, s.output, registry)


@pytest.mark.parametrize("change", ["output", "budget", "claim"])
def test_preclaim_rebind_cannot_evade_a_real_run_or_scientific_change(approved, change):
    s = approved
    old_path = s.root / "old-plan.json"
    old = copy.deepcopy(s.frozen)
    if change == "budget":
        old["max_combined_tokens"] -= 1
    dense.write_json_atomic(old_path, old)
    if change == "output":
        s.output.mkdir()
    if change == "claim":
        claim = (
            Path(old["e1_workspace"])
            / ".cache"
            / f"e2-{e2.target.digest(old)}.claim.json"
        )
        dense.write_json_atomic(claim, {"directory": "existing"})
    with pytest.raises(ValueError):
        hot.admit_preclaim_rebind(
            old_path, s.child_plan, s.output, s.root / "no-registry.json"
        )
    assert len(s.state["posts"]) == s.initial_posts


@pytest.fixture
def known_filter_stop(approved, monkeypatch):
    s = approved
    continuation.run_method(s, "dense", monkeypatch)
    original = e2.indexes.retrieve_hippo_query_only

    def malformed_filter(loaded, rag, question, query_vector, embedding_digest):
        rag.extraction_llm.handler([{"role": "user", "content": "filter-marker"}])
        raise ValueError("E2_filter_shape_invalid")

    monkeypatch.setattr(e2.indexes, "retrieve_hippo_query_only", malformed_filter)
    continuation.run_method(s, "hipporag2", monkeypatch)
    monkeypatch.setattr(e2.indexes, "retrieve_hippo_query_only", original)
    parent_path, parent_output = s.child_plan, s.output
    parent = dense.read_json(parent_path)
    monkeypatch.setattr(hot, "ROOT", s.root)
    monkeypatch.setattr(hot, "CODE_FILES", ())
    monkeypatch.setattr(hot, "PARENT_PLAN_SHA", dense.sha256_file(parent_path))
    monkeypatch.setattr(hot, "EXPECTED_MISSING", 9)
    monkeypatch.setattr(
        hot, "FILTER_CASE_KEY", e2.case_key("hotpotqa", "hipporag2", "q0")
    )
    monkeypatch.setattr(shared, "verify_transport_runtime", lambda *a, **kw: None)
    monkeypatch.setattr(hot, "prepare", lambda *a: copy.deepcopy(parent))
    auth = s.root / "continuation-auth.json"
    dense.write_json_atomic(
        auth,
        hot.continuation_authorization(
            dense.sha256_file(parent_path),
            dense.sha256_file(parent_output / "manifest.json"),
        ),
    )
    child = hot.prepare_unattempted(parent_path, parent_output, auth)
    s.root_plan, s.root_output, s.continuation_auth = parent_path, parent_output, auth
    s.child_plan, s.output = s.root / "unattempted.json", s.root / "unattempted"
    dense.write_json_atomic(s.child_plan, child)
    s.frozen = child
    s.registry = s.root / ".cache/e2-hotpotqa-s500-recoveries.json"
    dense.write_json_atomic(
        s.registry,
        {
            "plan_sha256": dense.sha256_file(parent_path),
            "output": str(parent_output.resolve()),
            "automatic_resumes": 1,
            "admissions": [],
        },
    )
    s.root_bytes = {
        str(p): p.read_bytes() for p in parent_output.iterdir() if p.is_file()
    }
    s.continuation_posts = len(s.state["posts"])
    return s


def test_unattempted_CLI_preserves_known_failures_budget_and_no_repayment(
    known_filter_stop, monkeypatch
):
    s = known_filter_stop
    old = dense.read_json(s.root_plan)
    parent_manifest = dense.read_json(s.root_output / "manifest.json")
    spent = parent_manifest["token_accounting"]["summary"]["known_subtotal"]
    assert s.frozen["max_combined_tokens"] == old["max_combined_tokens"] - sum(
        spent.values()
    )
    assert len(s.frozen["remaining_cases"]) == 9
    assert s.frozen["max_posts"] == 22  # 9reader+4filter+9BGE
    assert s.frozen["filter_calls"] == 4
    assert (
        hot.admit_unattempted(s.child_plan, s.output, s.registry)["automatic_resumes"]
        == 2
    )
    for method in ("hipporag2", "raptor"):
        continuation.run_method(s, method, monkeypatch)
    assert len(s.state["posts"]) - s.continuation_posts == 22
    count = len(s.state["posts"])
    for method in e2.METHODS:
        continuation.run_method(s, method, monkeypatch)
    assert len(s.state["posts"]) == count
    report = hot.write_report(s.child_plan, s.output, s.root / "combined")
    assert report["comparison_complete"]
    assert report["total_coverage"] == {
        "expected": 15,
        "completed": 13,
        "attempted_failed": 2,
        "not_attempted": 0,
    }
    assert report["S500_physical_accounting"]["POST"] == 28
    assert report["S500_physical_accounting"]["unknown_reservation_not_actual"] == 0
    assert report["S500_physical_accounting"]["cost_complete"] is True
    assert report["cost_complete"] is False
    assert report["execution_code_sha256"] == s.frozen["code_sha256"]
    assert report["report_code_sha256"] == dense.sha256_file(Path(shared.__file__))
    assert hot.write_report(s.child_plan, s.output, s.root / "combined-again") == report
    assert all(Path(p).read_bytes() == b for p, b in s.root_bytes.items())


@pytest.mark.parametrize(
    "change",
    ["parent_sha", "journal", "response", "claim", "authorization", "second_child"],
)
def test_known_failure_continuation_strict_pins(known_filter_stop, change):
    s = known_filter_stop
    if change == "parent_sha":
        s.root_plan.write_text("{}", encoding="utf-8")
    elif change == "journal":
        with (s.root_output / "usage.jsonl").open("a", encoding="utf-8") as f:
            f.write("{}\n")
    elif change == "response":
        next(s.root_output.glob("*.response.json")).write_text("{}", encoding="utf-8")
    elif change == "claim":
        parent = dense.read_json(s.root_plan)
        (
            Path(parent["e1_workspace"])
            / ".cache"
            / f"e2-{e2.target.digest(parent)}.claim.json"
        ).write_text("{}", encoding="utf-8")
    elif change == "authorization":
        s.continuation_auth.write_text("{}", encoding="utf-8")
    else:
        with pytest.raises(ValueError, match="only_original_failed_parent"):
            hot.prepare_unattempted(s.child_plan, s.output, s.continuation_auth)
        return
    with pytest.raises((ValueError, KeyError)):
        hot.prepare_unattempted(s.root_plan, s.root_output, s.continuation_auth)
    assert len(s.state["posts"]) == s.continuation_posts
