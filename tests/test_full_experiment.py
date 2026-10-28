"""S500 freeze gates, including results produced by the existing E2 runner."""

import copy
import json
from collections import defaultdict

import pytest
import requests

from scripts import e2_evaluation as e2, e2_pilot as pilot, full_experiment as full
from scripts import run_dense as dense, run_dense_target as target
from scripts.token_accounting import read_records
import test_e2_continuation as continuation

scenario = continuation.scenario
pilot_scenario = continuation.pilot_scenario
sealed_transport_scenario = continuation.sealed_transport_scenario
run_method = continuation.run_method


def test_pinned_splits_and_3000_cases():
    identities = set()
    for dataset in target.DATASETS:
        ids = dense.read_json(full.ROOT / f"data/ids/{dataset}_s500.json")[
            "question_ids"
        ]
        split = dense.read_json(full.ROOT / f"data/ids/{dataset}_comparison_split.json")
        full.check_split(ids, split)
        for method in e2.METHODS:
            identities.update(e2.case_key(dataset, method, qid) for qid in ids)
        for bad in (ids[:-1], ids[::-1], [ids[0]] * 500):
            with pytest.raises(ValueError):
                full.check_split(bad, split)
    assert len(identities) == 3000


@pytest.fixture
def saved_case(pilot_scenario, monkeypatch):
    s = pilot_scenario
    plan = dense.read_json(s.pilot_plan)
    for key in full.CONTRACT:
        plan.setdefault(key, key)
    plan["sealed_unknown"] = []
    plan["message_utf8_bytes_limit"] = 65536
    dense.write_json_atomic(s.pilot_plan, plan)
    monkeypatch.setattr(pilot, "verify", lambda p: None)
    s.child_plan, s.output = s.pilot_plan, s.pilot_output
    run_method(s, "dense", monkeypatch)
    result = next(
        dense.read_json(p)
        for p in sorted(s.output.glob("question-*.json"))
        if dense.read_json(p)["status"] == "completed"
        and any(not op.get("reused") for op in dense.read_json(p)["operations"])
    )
    path = s.output / (
        "question-"
        + e2.case_key(result["dataset"], result["method"], result["question_id"])
        + ".json"
    )
    sha = dense.sha256_file(path)
    return s, plan, result, path, sha


def check_saved(saved, plan=None, result=None, sha=None):
    s, producer, r, path, original_sha = saved
    return full.classify(
        plan or producer,
        producer,
        s.output,
        result or r,
        sha or original_sha,
        {r["question_id"]: r["question"]},
        read_records(s.output / "usage.jsonl"),
    )


def test_existing_runner_result_is_reused_without_transport(saved_case):
    s, plan, result, _, _ = saved_case
    before = len(s.state["posts"])
    assert check_saved(saved_case)[0] == "compatible_completed"
    assert len(s.state["posts"]) == before
    changed = copy.deepcopy(plan)
    changed["message_utf8_bytes_limit"] = 65535  # admission is not reader semantics
    assert check_saved(saved_case, plan=changed)[0] == "compatible_completed"
    assert result["reader_request_sha256"] == target.digest(
        e2.configured_reader_payload(plan, result["question"], result["retrieval"])
    )


@pytest.mark.parametrize(
    "change",
    [
        "options",
        "endpoint",
        "corpus",
        "index",
        "payload",
        "result_sha",
        "checkpoint",
        "missing",
    ],
)
def test_changed_or_missing_artifact_never_compatible(saved_case, change):
    s, producer, result, path, sha = saved_case
    plan, result = copy.deepcopy(producer), copy.deepcopy(result)
    if change == "options":
        plan["reader_options"]["max_tokens"] = 1024
    elif change == "endpoint":
        plan["endpoint"] = "http://changed.invalid"
    elif change == "corpus":
        plan["datasets"][result["dataset"]]["corpus_sha256"] = "changed"
    elif change == "index":
        plan["datasets"][result["dataset"]]["indexes"][0]["manifest_sha256"] = "changed"
    elif change == "payload":
        result["retrieval"]["passages"][0]["text"] += "changed"
    elif change == "result_sha":
        sha = "0" * 64
    elif change == "missing":
        path.unlink()
    else:
        op = next(o for o in result["operations"] if not o.get("reused"))
        (s.output / (op["journal_object_id"] + ".response.json")).write_text("{}")
    assert check_saved(saved_case, plan, result, sha)[0] == "incompatible"


def test_unapproved_failure_is_not_a_missing_case(saved_case):
    result = copy.deepcopy(saved_case[2])
    result.update(
        status="attempted_failed",
        fatal=True,
        answer="",
        raw_answer="",
        error={"type": "ConnectionError", "reason": "RemoteDisconnected"},
    )
    assert check_saved(saved_case, result=result)[0] == "incompatible"


def test_budget_separates_logical_forecast_and_reservations():
    config = [
        {"dataset": "musique", "method": m, "missing_ids": ["q"]} for m in e2.METHODS
    ]
    plan = {
        "embedding_model": "bge-m3:latest",
        "message_utf8_bytes_limit": 65536,
        "query_utf8_bytes_limit": 4096,
    }
    logical = defaultdict(dict)
    for m in e2.METHODS:
        for op in ("reader", "query_embedding") + (
            ("filter",) if m == "hipporag2" else ()
        ):
            row = logical["musique/" + m][op] = full.usage_row()
            for _ in range(2):
                full.observe_usage(
                    row,
                    {
                        "operation": op,
                        "logical_usage": {
                            "llm_input_tokens": 10 if op != "query_embedding" else None,
                            "llm_output_tokens": 1 if op != "query_embedding" else None,
                            "embedding_input_tokens": 10
                            if op == "query_embedding"
                            else None,
                        },
                    },
                )
    bounds = {
        "musique/" + k: {"synthetic_top5_message_bytes": 1000}
        for k in ("raptor", "dense_or_hippo")
    }
    value = full.budget(config, {"musique": {"q": "Which?"}}, plan, bounds, logical)
    assert value["new_posts_upper"] == {"reader": 3, "filter": 1, "query_embedding": 3}
    assert value["new_posts_total_upper"] == 7
    assert value["forecast_known_combined_tokens"] == 74
    assert value["conservative_combined_tokens"] == sum(
        value["conservative_reservations_by_operation"].values()
    )
    assert not value["authorized"] and not value["reserve_is_measured_usage"]
    bounds["musique/raptor"]["synthetic_top5_message_bytes"] = 65537
    with pytest.raises(ValueError, match="overflow"):
        full.budget(config, {"musique": {"q": "Which?"}}, plan, bounds, logical)


def test_actual_reader_blocks_network_and_gold_and_relocates(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    new.mkdir()
    roots = full.Roots(
        new,
        tmp_path / "data",
        tmp_path / "index",
        old,
        {
            "data_root": str(tmp_path / "prior-data"),
            "workspace": str(tmp_path / "prior-index"),
        },
    )
    dense.write_json_atomic(new / "safe.json", {"id": "q"})
    with full.offline_io(roots):
        assert dense.read_json(old / "safe.json") == {"id": "q"}
        with pytest.raises(ValueError, match="gold_read_forbidden"):
            dense.read_json(old / "labels.json")
        with pytest.raises(RuntimeError, match="HTTP_forbidden"):
            requests.post("http://127.0.0.1:1/model", json={})
    assert roots.safe(old / "safe.json") == "artifact:safe.json"


def test_cli_determinism_and_verify_rejects_drift(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "manifest.json"
    value = {
        "counts": {
            "compatible_completed": 1199,
            "terminal_failure": 1,
            "missing": 1800,
        },
        "budget_proposal": {"authorized": False},
    }
    monkeypatch.setattr(full, "freeze", lambda *args: copy.deepcopy(value))
    args = [
        "--data-root",
        str(tmp_path),
        "--artifact-root",
        str(tmp_path),
        "--index-root",
        str(tmp_path),
        "--manifest",
        str(manifest),
    ]
    full.main(["prepare", *args])
    before = manifest.read_bytes()
    full.main(["prepare", *args])
    assert before == manifest.read_bytes()
    full.main(["verify", *args])
    manifest.write_text(json.dumps({**value, "counts": {"missing": 3000}}))
    with pytest.raises(ValueError, match="manifest_changed"):
        full.main(["verify", *args])
    assert '"HTTP": 0' in capsys.readouterr().out


def test_irrelevant_null_fields_are_not_unknown():
    totals = dict.fromkeys(full.FIELDS, 0)
    full.usage_add(
        totals,
        {
            "logical_usage": {
                "llm_input_tokens": None,
                "llm_output_tokens": None,
                "embedding_input_tokens": 20,
            }
        },
    )
    assert totals == {
        "llm_input_tokens": 0,
        "llm_output_tokens": 0,
        "embedding_input_tokens": 20,
    }


def test_relevant_usage_status_preserves_unknown():
    assert full.usage_complete(
        {
            "operation": "query_embedding",
            "logical_usage": {
                "llm_input_tokens": None,
                "llm_output_tokens": None,
                "embedding_input_tokens": 20,
            },
        }
    )
    assert full.usage_complete(
        {
            "operation": "reader",
            "logical_usage": {
                "llm_input_tokens": 20,
                "llm_output_tokens": 2,
                "embedding_input_tokens": None,
            },
        }
    )
    assert not full.usage_complete(
        {
            "operation": "reader",
            "logical_usage": {
                "llm_input_tokens": None,
                "llm_output_tokens": None,
                "embedding_input_tokens": None,
            },
        }
    )


def test_sealed_case_keeps_identity_and_never_posts(
    sealed_transport_scenario, monkeypatch
):
    s = sealed_transport_scenario
    producer = dense.read_json(s.issued)
    result = next(
        dense.read_json(p)
        for p in s.issued_output.glob("question-*.json")
        if dense.read_json(p)["status"] == "attempted_failed"
    )
    key = e2.case_key(result["dataset"], result["method"], result["question_id"])
    path = s.issued_output / ("question-" + key + ".json")
    # Synthetic runner fixture deliberately omits production model metadata.
    monkeypatch.setattr(
        full,
        "CONTRACT",
        tuple(k for k in full.CONTRACT if k in producer and k in s.sealed),
    )
    before = len(s.state["posts"])
    status, reason = full.classify(
        s.sealed,
        producer,
        s.issued_output,
        result,
        dense.sha256_file(path),
        {result["question_id"]: result["question"]},
        read_records(s.issued_output / "usage.jsonl"),
    )
    assert status == "terminal_failure" and reason == "sealed_unknown_no_retry"
    assert len(s.state["posts"]) == before
    assert s.sealed["sealed_unknown"][0]["retry"] == "forbidden"


def test_published_manifest_accounts_for_every_case_and_scope():
    m = dense.read_json(full.ROOT / full.PUBLIC)
    counts = {"compatible_completed": 0, "terminal_failure": 0, "missing": 0}
    keys = set()
    for c in m["configurations"]:
        ids = m["datasets"][c["dataset"]]["ordered_ids"]
        assert [r["question_id"] for r in c["cases"]] + c["missing_ids"] == ids
        for row in c["cases"]:
            counts[row["status"]] += 1
        counts["missing"] += len(c["missing_ids"])
        for qid in ids:
            keys.add(e2.case_key(c["dataset"], c["method"], qid))
    assert m["data_source"]["repository"] == "osunlp/HippoRAG_2"
    assert m["data_source"]["lock_sha256"] == dense.sha256_file(
        full.ROOT / "data/sources.lock.json"
    )
    assert len(keys) == m["cases"] == 3000
    assert (
        counts
        == m["counts"]
        == {"compatible_completed": 1199, "terminal_failure": 1, "missing": 1800}
    )
    assert m["budget_proposal"]["new_posts_total_upper"] == 4200
    assert sum(m["pilot_physical"]["known_subtotal"].values()) == 3799313
    assert sum(m["development_physical"]["known_subtotal"].values()) == 237340
    assert sum(m["source_reuse_subset_of_development"].values()) == 91871
    assert not m["pilot_physical"]["complete"]
    assert m["sealed_unknown"][0]["reservation_tokens"] == 22545
    assert "case_key" not in m["sealed_unknown"][0]
    assert m["sealed_unknown"][0]["case_id_sha256"] == e2.case_key(
        "hotpotqa", "raptor", "5adbe75455429944faac23af"
    )
    for producer in m["pilot_provenance"]:
        assert {p["file"] for p in producer["runtime_code_sha256"]} == set(
            e2.CODE_FILES
        )
    assert (
        sum(
            r["unknown_operations"]
            for c in m["logical_reused_usage_by_configuration"].values()
            for r in c.values()
        )
        == 1
    )
    assert not m["executable"] and not m["http_authorized"]

    def safe(value):
        if isinstance(value, str):
            assert not (len(value) > 2 and value[1:3] in (":/", ":\\"))
        elif isinstance(value, dict):
            assert not {"answer", "question", "text", "raw_answer"} & set(value)
            for v in value.values():
                safe(v)
        elif isinstance(value, list):
            for v in value:
                safe(v)

    safe(m)


def test_partial_known_reporting_and_complete_only_forecast():
    row = full.usage_row()
    for incoming, outgoing in ((100, 10), (50, None), (None, None)):
        full.observe_usage(
            row,
            {
                "operation": "reader",
                "logical_usage": {
                    "llm_input_tokens": incoming,
                    "llm_output_tokens": outgoing,
                    "embedding_input_tokens": None,
                },
            },
        )
    assert row["known_subtotal"]["llm_input_tokens"] == 150
    assert row["known_subtotal"]["llm_output_tokens"] == 10
    assert row["forecast_complete"] == {
        "operations": 1,
        "subtotal": {
            "llm_input_tokens": 100,
            "llm_output_tokens": 10,
            "embedding_input_tokens": 0,
        },
        "maximum_operation_tokens": 110,
    }
    assert row["partial_operations"] == row["fully_unknown_operations"] == 1
    assert row["unknown_operations"] == 2
    config = [{"dataset": "musique", "method": "dense", "missing_ids": ["q"]}]
    plan = {
        "embedding_model": "bge",
        "message_utf8_bytes_limit": 65536,
        "query_utf8_bytes_limit": 4096,
    }
    embedding = full.usage_row()
    full.observe_usage(
        embedding,
        {
            "operation": "query_embedding",
            "logical_usage": {"embedding_input_tokens": 2},
        },
    )
    bounds = {"musique/dense_or_hippo": {"synthetic_top5_message_bytes": 1000}}
    logical = {"musique/dense": {"reader": row, "query_embedding": embedding}}
    result = full.budget(config, {"musique": {"q": "Which?"}}, plan, bounds, logical)
    assert result["forecast_tokens_by_operation"]["reader/llm_input_tokens"] == 100
    assert result["forecast_known_combined_tokens"] == 112
    proposal = result["operational_budget_proposal"]
    assert proposal["pilot_maximum_allocation_tokens"] == 112
    assert proposal["proposed_new_token_cap"] == 112 + 1000 + 1024 + 2048 + 512
    assert not proposal["authorized"] and not proposal["completion_guaranteed"]
    for observation in (full.usage_row(), None):
        if observation is None:
            logical["musique/dense"].pop("reader")
        else:
            full.observe_usage(
                observation, {"operation": "reader", "logical_usage": {}}
            )
            logical["musique/dense"]["reader"] = observation
            assert observation["fully_unknown_operations"] == 1
        result = full.budget(
            config, {"musique": {"q": "Which?"}}, plan, bounds, logical
        )
        assert result["forecast_known_combined_tokens"] is None
        assert result["forecast_tokens_by_operation"]["reader/llm_input_tokens"] is None
        assert result["operational_budget_proposal"]["proposed_new_token_cap"] is None
        assert result["forecast_missing_observations"] == ["musique/dense/reader"]


def test_existing_transport_refuses_insufficient_budget_before_post():
    from unittest.mock import Mock

    session, journal = Mock(), Mock()
    journal.summary.return_value = {"known_subtotal": {"llm_input_tokens": 150}}
    payload = {"model": e2.MODEL, "messages": [], "max_tokens": 512}
    reserve = len(json.dumps(payload, ensure_ascii=False).encode()) + 2048 + 512
    with pytest.raises(ValueError, match="token_budget_reservation_exceeded"):
        target.checked_post(
            session,
            "http://unused.invalid",
            payload,
            journal,
            phase="reader",
            operation="reader",
            provider="target_api",
            model=e2.MODEL,
            kind="llm",
            object_id="blocked",
            token_limit=150 + reserve - 1,
        )
    session.post.assert_not_called()


def test_musique_worklist_complete_partition_and_pending_budget():
    source = dense.read_json(full.ROOT / full.PUBLIC)
    value = full.musique_worklist(source)
    assert value["counts"] == {
        "expected_cases": 1500,
        "inherited_completed": 600,
        "not_attempted": 900,
        "terminal_failures": 0,
    }
    budget = value["budget_proposal"]
    assert budget["proposed_new_token_cap"] == 5990220
    assert budget["new_posts_upper"] == {
        "reader": 900,
        "filter": 300,
        "query_embedding": 900,
    }
    assert budget["new_posts_total_upper"] == 2100
    assert (
        not value["executable"]
        and not value["http_authorized"]
        and not value["execution_complete"]
    )
    assert not budget["authorized"] and not budget["completion_guaranteed"]
    assert (
        value["historical_accounting"]["out_of_scope_sealed_unknown"]
        == source["sealed_unknown"]
    )
    assert all(
        len(m["inherited_results"]) == 200 and len(m["new_question_ids"]) == 300
        for m in value["methods"]
    )
    changed = copy.deepcopy(source)
    changed["configurations"][0]["cases"][0]["status"] = "terminal_failure"
    with pytest.raises(ValueError, match="not_completed"):
        full.musique_worklist(changed)
    changed = copy.deepcopy(source)
    changed["datasets"]["musique"]["ordered_ids"].reverse()
    with pytest.raises(ValueError, match="ID_pin"):
        full.musique_worklist(changed)


def test_musique_cli_stages_and_verifies_without_transport(tmp_path, monkeypatch):
    source = dense.read_json(full.ROOT / full.PUBLIC)
    monkeypatch.setattr(full, "freeze", lambda *args: copy.deepcopy(source))

    def forbidden(*args, **kwargs):
        raise AssertionError("model_transport_forbidden")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    output = tmp_path / "musique.json"
    args = [
        "--artifact-root",
        str(tmp_path),
        "--data-root",
        str(tmp_path),
        "--index-root",
        str(tmp_path),
        "--dataset-plan",
        str(output),
    ]
    full.main(["prepare-musique", *args])
    original = output.read_bytes()
    full.main(["verify-musique", *args])
    full.main(["prepare-musique", *args])
    assert output.read_bytes() == original
    with pytest.raises(SystemExit):
        full.main(["prepare-musique", *args, "--execute"])
    value = dense.read_json(output)
    value["counts"]["not_attempted"] = 0
    dense.write_json_atomic(output, value)
    with pytest.raises(ValueError, match="worklist_changed"):
        full.main(["verify-musique", *args])
