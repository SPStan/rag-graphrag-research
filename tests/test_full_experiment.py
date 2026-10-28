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
        for p in s.output.glob("question-*.json")
        if dense.read_json(p)["status"] == "completed"
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
    "change", ["options", "index", "payload", "result_sha", "checkpoint", "missing"]
)
def test_changed_or_missing_artifact_never_compatible(saved_case, change):
    s, producer, result, path, sha = saved_case
    plan, result = copy.deepcopy(producer), copy.deepcopy(result)
    if change == "options":
        plan["reader_options"]["max_tokens"] = 1024
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
            logical["musique/" + m][op] = {
                "known_operations": 2,
                "unknown_operations": 1,
                "known_subtotal": {
                    "llm_input_tokens": 20,
                    "llm_output_tokens": 2,
                    "embedding_input_tokens": 0,
                },
            }
    bounds = {
        "musique/" + k: {"synthetic_top5_message_bytes": 1000}
        for k in ("raptor", "dense_or_hippo")
    }
    value = full.budget(config, {"musique": {"q": "Which?"}}, plan, bounds, logical)
    assert value["new_posts_upper"] == {"reader": 3, "filter": 1, "query_embedding": 3}
    assert value["new_posts_total_upper"] == 7
    assert value["forecast_known_combined_tokens"] == 77
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
