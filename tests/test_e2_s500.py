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


@pytest.fixture
def stopped_raptor(approved, monkeypatch):
    s = approved
    for method in ("dense", "hipporag2"):
        continuation.run_method(s, method, monkeypatch)
    original_post = runner.requests.Session.post
    s.state["sealed_test_fault"] = True

    def disconnected(self, *args, **kwargs):
        response = original_post(self, *args, **kwargs)
        payload = kwargs.get("json")
        if s.state["sealed_test_fault"] and "messages" in payload:
            raise runner.requests.ConnectionError(
                "RemoteDisconnected: remote end closed connection without response"
            )
        return response

    monkeypatch.setattr(runner.requests.Session, "post", disconnected)
    continuation.run_method(s, "raptor", monkeypatch)
    assert dense.read_json(s.output / "manifest.json")["status"] == "failed"
    s.root_plan, s.root_output = s.child_plan, s.output
    monkeypatch.setattr(s500, "PARENT_PLAN_SHA", dense.sha256_file(s.root_plan))
    monkeypatch.setattr(s500, "EXPECTED_MISSING", 4)
    original_root = dense.read_json(s.root_plan)
    monkeypatch.setattr(s500, "prepare", lambda *args: copy.deepcopy(original_root))
    monkeypatch.setattr(
        s500,
        "verify_transport_runtime",
        lambda parent: s500.require(
            parent["code_sha256"] == original_root["code_sha256"], "runtime_changed"
        ),
    )
    auth = dense.read_json(
        s500.ROOT / "results/summary/e2-musique-s500-unattempted-authorization.json"
    )
    auth.update(
        parent_plan_sha256=dense.sha256_file(s.root_plan), expected_unattempted=4
    )
    s.auth = s.root / "unattempted-authorization.json"
    dense.write_json_atomic(s.auth, auth)
    s.physical_before = len(s.state["posts"])
    s.old_bytes = {p: p.read_bytes() for p in s.root_output.rglob("*") if p.is_file()}
    return s


def test_sealed_unknown_child_existing_runner_only_four_unattempted(
    stopped_raptor, monkeypatch
):
    s = stopped_raptor
    child = s500.prepare_unattempted(s.root_plan, s.root_output, s.auth)
    assert len(child["parent_run"]["cases"]) == 11
    assert len(child["remaining_cases"]) == 4
    assert child["max_posts"] == 8 and child["filter_calls"] == 0
    sealed = child["sealed_unknown"][0]
    assert sealed["retry"] == "forbidden" and sealed["reservation_tokens"] > 0
    records = e2.lineage_records(
        dense.read_json(s.root_plan),
        s.root_output,
        dense.read_json(s.root_output / "manifest.json"),
    )[0]
    from scripts.token_accounting import summarize

    assert (
        child["max_combined_tokens"]
        + sum(summarize(records)["known_subtotal"].values())
        + sealed["reservation_tokens"]
        == s.frozen["max_combined_tokens"]
    )
    s.state["sealed_test_fault"] = False
    s.child_plan, s.output = s.root / "unattempted.json", s.root / "unattempted"
    dense.write_json_atomic(s.child_plan, child)
    with pytest.raises(ValueError, match="only_RAPTOR"):
        continuation.run_method(s, "dense", monkeypatch)
    continuation.run_method(s, "raptor", monkeypatch)
    assert len(s.state["posts"]) - s.physical_before == 8
    continuation.run_method(s, "raptor", monkeypatch)
    assert len(s.state["posts"]) - s.physical_before == 8
    manifest = dense.read_json(s.output / "manifest.json")
    assert manifest["status"] == "completed" and len(manifest["results"]) == 4
    assert sealed["case_key"] not in manifest["results"]
    report = s500.write_report(s.child_plan, s.output, s.root / "final-report")
    assert report["comparison_complete"] and not report["cost_complete"]
    assert report["total_coverage"] == {
        "expected": 15,
        "completed": 14,
        "attempted_failed": 1,
        "not_attempted": 0,
    }
    assert report["new_POST"] == 8
    assert report["S500_physical_accounting"]["POST"] == len(records) // 2 + 8
    assert report["rows"][2]["S500_physical_usage"]["reader"]["unknown_operations"] == 1
    assert all(p.read_bytes() == body for p, body in s.old_bytes.items())
    with pytest.raises(ValueError, match="no_second_unknown_child"):
        s500.prepare_unattempted(s.child_plan, s.output, s.auth)


@pytest.mark.parametrize(
    "change",
    ["authorization", "active_lock", "claim", "checkpoint", "response", "code_pin"],
)
def test_sealed_child_rejects_changed_evidence_before_http(stopped_raptor, change):
    s = stopped_raptor
    if change == "authorization":
        v = dense.read_json(s.auth)
        v["retry_unknown"] = True
        dense.write_json_atomic(s.auth, v)
    elif change == "active_lock":
        (s.root_output / "running.lock").write_text("active", encoding="utf-8")
    elif change == "code_pin":
        v = dense.read_json(s.root_plan)
        v["code_sha256"]["scripts/run_dense.py"] = "changed"
        dense.write_json_atomic(s.root_plan, v)
    elif change == "claim":
        p = s.root / ".cache" / f"e2-{runner.digest(s.frozen)}.claim.json"
        dense.write_json_atomic(p, {"directory": "other"})
    else:
        m = dense.read_json(s.root_output / "manifest.json")
        result = next(
            dense.read_json(s.root_output / f"question-{key}.json")
            for key in m["results"]
            if dense.read_json(s.root_output / f"question-{key}.json").get("fatal")
        )
        obj = result["operations"][-1]["journal_object_id"]
        dense.write_json_atomic(
            s.root_output
            / (obj + (".response.json" if change == "response" else ".json")),
            {},
        )
    with pytest.raises(ValueError):
        s500.prepare_unattempted(s.root_plan, s.root_output, s.auth)
    assert len(s.state["posts"]) == s.physical_before


@pytest.mark.parametrize("cursor_field", ["cursor", "next_cursor"])
def test_local_tracking_reader_reads_all_2001_observations(cursor_field):
    from types import SimpleNamespace
    from scripts import track_dense

    requested = []

    def get_many(**kwargs):
        requested.append(kwargs["cursor"])
        n = len(requested)
        return SimpleNamespace(
            data=list(range(1000 if n < 3 else 1)),
            meta=SimpleNamespace(**{cursor_field: str(n) if n < 3 else None}),
        )

    client = SimpleNamespace(
        api=SimpleNamespace(observations=SimpleNamespace(get_many=get_many))
    )
    assert len(track_dense.get_all_langfuse_observations(client, "trace")) == 2001
    assert requested == [None, "1", "2"]


def test_tracking_reader_repeated_cursor_and_ast_boundary():
    from types import SimpleNamespace
    from scripts import track_dense, full_experiment as full

    client = SimpleNamespace(
        api=SimpleNamespace(
            observations=SimpleNamespace(
                get_many=lambda **kw: SimpleNamespace(
                    data=[1], meta=SimpleNamespace(cursor="same")
                )
            )
        )
    )
    with pytest.raises(RuntimeError, match="repeated cursor"):
        track_dense.get_all_langfuse_observations(client, "trace")
    old = "def get_all_langfuse_observations(client, trace_id):\n    return []\ndef export():\n    return 512\n"
    full.compatible_tracking_reader(old, old.replace("return []", "return [1]"))
    with pytest.raises(ValueError, match="outside_observation_reader"):
        full.compatible_tracking_reader(old, old.replace("512", "1024"))


def test_report_regeneration_preserves_bound_evidence(approved, monkeypatch):
    """Exercise the shared runner's report entry, not just the appendix helper."""
    s = approved
    for method in e2.METHODS:
        continuation.run_method(s, method, monkeypatch)
    core = s500.write_report(s.child_plan, s.output, s.root / "initial")
    receipt = s.root / "receipt.json"
    dense.write_json_atomic(
        receipt, {"verified": True, "run_id": core["run_id"], "views": {}}
    )
    monkeypatch.setattr(s500, "ROOT", s.root)
    sections = {
        "terminal_audit": {
            k: core[k] for k in ("run_id", "plan_sha256", "manifest_sha256")
        },
        "tracking": {
            "receipt_relative_path": "receipt.json",
            "receipt_sha256": dense.sha256_file(receipt),
            "views": {},
        },
        "cumulative_E2_accounting": {"historical_unknown": 1},
    }
    sections["terminal_audit"].update(
        journal_sha256=dense.sha256_file(s.output / "usage.jsonl"),
        private_evaluation_sha256=dense.sha256_file(s.output / "evaluation.json"),
    )
    audit_path = s.root / "audit.json"
    dense.write_json_atomic(audit_path, sections["terminal_audit"])
    appendix = s.root / "results/summary/e2-musique-s500-evidence.json"
    evidence = {k: core[k] for k in ("run_id", "plan_sha256", "manifest_sha256")}
    evidence.update(
        raw_directory_name=s.output.name,
        sections=sections,
        sections_sha256=runner.digest(sections),
        terminal_audit_relative_path="audit.json",
        artifact_sha256={
            "receipt.json": dense.sha256_file(receipt),
            "audit.json": dense.sha256_file(audit_path),
        },
    )
    dense.write_json_atomic(appendix, evidence)
    before = {p: p.read_bytes() for p in s.output.rglob("*") if p.is_file()}
    posts = len(s.state["posts"])
    for name in ("rebuild-one", "rebuild-two"):
        # Same route as --summarize-shared, with a separate public output.
        monkeypatch.setattr(
            "sys.argv",
            [
                "run_dense_target",
                "--shared-plan",
                str(s.child_plan),
                "--output-dir",
                str(s.output),
                "--summarize-shared",
                str(s.root / name),
            ],
        )
        runner.main()
    first = dense.read_json(s.root / "rebuild-one.json")
    assert first == dense.read_json(s.root / "rebuild-two.json")
    assert all(first[k] == v for k, v in sections.items())
    assert before == {p: p.read_bytes() for p in before}
    assert len(s.state["posts"]) == posts
    for key in ("run_id", "plan_sha256", "manifest_sha256"):
        changed = copy.deepcopy(evidence)
        changed[key] = "wrong"
        dense.write_json_atomic(appendix, changed)
        with pytest.raises(ValueError, match="evidence_run_binding"):
            e2.write_report(s.child_plan, s.output, s.root / "rejected")
    changed = copy.deepcopy(evidence)
    changed["sections"]["terminal_audit"]["invented_verified"] = True
    changed["sections_sha256"] = runner.digest(changed["sections"])
    dense.write_json_atomic(appendix, changed)
    with pytest.raises(ValueError, match="evidence_audit_changed"):
        e2.write_report(s.child_plan, s.output, s.root / "rejected")
    dense.write_json_atomic(appendix, evidence)
    receipt.write_text("changed")
    with pytest.raises(ValueError, match="evidence_artifact_changed"):
        e2.write_report(s.child_plan, s.output, s.root / "rejected")
