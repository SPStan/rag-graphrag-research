from unittest.mock import Mock, patch

import pytest
import requests

from scripts import e1_summary_recovery as r
from scripts import run_dense as d
from scripts import run_e1 as e
from scripts.token_accounting import Journal
from tests.test_e1_summary_probe import body, setup_probe


def adoption_fixture(tmp_path):
    prior, plan, corpus, parent, original_path = setup_probe(tmp_path)
    row = plan["rows"][5]
    row["embedding_options"] = e.RAPTOR_EMBEDDING_OPTIONS
    d.write_json_atomic(prior, plan)
    for producer in plan["rows"][:2]:
        mp = tmp_path / producer["output"] / "manifest.json"
        manifest = d.read_json(mp)
        manifest["plan_sha256"] = e.target.digest(plan)
        d.write_json_atomic(mp, manifest)
    prepared = e.prepare_summary_probe(prior, original_path)
    pp = tmp_path / "probe.json"
    d.write_json_atomic(pp, prepared)
    response = Mock(status_code=200)
    response.json.return_value = body("supported " * 315)
    with patch("requests.Session.post", return_value=response):
        with pytest.raises(ValueError, match="compact_complete"):
            e.execute_summary_probe(
                pp,
                {
                    "LITELLM_API_KEY": "test",
                    "TARGET_API_MODEL": plan["model"],
                    "TARGET_API_BASE_URL": plan["endpoint"],
                },
                d.sha256_file(pp),
            )
    probe = parent.parent / "hotpotqa-summary-probe1"
    cache, _, _ = e.verified_checkpoints(probe / "manifest.json")
    key, item = next(iter(cache.items()))
    original = d.read_json(original_path)
    record = r.audit_response(plan, row, original, d.read_json(item["path"]), 550)
    proof = tmp_path / "native.json"
    d.write_json_atomic(
        proof,
        {
            "response_sha256": item["sha256"],
            "gguf_sha256": r.GGUF_SHA,
            "library_sha256": r.DLL_SHA,
            "native_tokens_with_special": 550,
            "control_tokens": 2104,
        },
    )
    record.update(
        parent_output=parent.relative_to(tmp_path).as_posix(),
        probe_output=probe.relative_to(tmp_path).as_posix(),
        parent_manifest_sha256=d.sha256_file(parent / "manifest.json"),
        probe_manifest_sha256=d.sha256_file(probe / "manifest.json"),
        original_payload_path=original_path.name,
        original_payload_file_sha256=d.sha256_file(original_path),
        context_sha256=e.target.digest(original["messages"][1]["content"]),
        fallback_request_sha256=key,
        response_sha256=item["sha256"],
        native_proof_path=proof.name,
        native_proof_sha256=d.sha256_file(proof),
        semantic_review={
            "status": "supported_by_input_context",
            "claims": [{"status": "supported"}],
        },
    )
    path = tmp_path / "adoption.json"
    d.write_json_atomic(path, record)
    return prior, plan, corpus, parent, path, original, item


@pytest.fixture
def prepared(tmp_path):
    with (
        patch.object(e, "ROOT", tmp_path),
        patch.object(e, "code_dirty", return_value=False),
        patch.object(e, "git", return_value="pin"),
        patch.object(
            e,
            "load_corpus",
            return_value=(
                [
                    {"id": "a", "title": "A", "text": "text"},
                    {"id": "b", "title": "B", "text": "text"},
                ],
                {},
            ),
        ),
        patch.object(r, "NativeBGE") as native,
    ):
        native.return_value.count.return_value = 550
        yield adoption_fixture(tmp_path)


def continuation(prior, path):
    return r.prepare_continuation(
        prior, path, {"gguf_path": "unused", "library_dir": "unused"}
    )


def test_claim_replay_and_no_double_cost(tmp_path, prepared):
    prior, old, _, parent, path, original, item = prepared
    (tmp_path / "results/summary").mkdir(parents=True, exist_ok=True)
    before = e.export(old, prior)
    plan = continuation(prior, path)
    row = plan["rows"][5]
    assert row["token_limit"] == e.LIMITS["raptor"] - 30
    assert row["prior_budget_charge"] == 30
    with pytest.raises(FileExistsError):
        continuation(prior, path)
    folder = tmp_path / row["output"]
    folder.mkdir()
    j = Journal(
        folder / "usage.jsonl",
        run_id=row["run_id"],
        method="raptor",
        dataset="hotpotqa",
    )
    runner = e.Transport(plan, row, {"LITELLM_API_KEY": "test"}, folder, j)
    original_key = row["summary_adoption"]["original_request_sha256"]
    assert original_key not in runner.parent_cache
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        for _ in range(2):
            answer = runner.generate(original["messages"], 4096, "summary")
            assert len(answer[0].split()) == 315
    assert j.summary()["attempts"] == 0
    assert sum(p["cache_hits"] for p in j.summary()["phases"]) == 2
    mapping = d.read_json(folder / "summary-fallbacks.json")
    assert mapping[original_key]["fallback_request_sha256"] != original_key
    assert mapping[original_key]["producer_run_id"] == item["run_id"]
    after = e.export(plan, prior)
    assert after["physical_known_tokens"] == before["physical_known_tokens"]
    assert after["budget_charge_upper_bound"] == before["budget_charge_upper_bound"]
    assert d.read_json(parent / "manifest.json")["status"] == "failed"
    runner.close()


@pytest.mark.parametrize(
    "changed", ["response", "parent", "payload", "proof", "association", "active"]
)
def test_changed_evidence_rejected_before_claim_http(tmp_path, prepared, changed):
    prior, _, _, parent, path, _, item = prepared
    record = d.read_json(path)
    if changed == "response":
        item["path"].write_text("{}", encoding="utf-8")
    elif changed == "parent":
        (parent / "manifest.json").write_text('{"status":"failed"}', encoding="utf-8")
    elif changed in ("payload", "proof"):
        (
            tmp_path
            / record[
                "original_payload_path" if changed == "payload" else "native_proof_path"
            ]
        ).write_text("{}", encoding="utf-8")
    elif changed == "active":
        (parent / "running.lock").write_text("1")
    else:
        record["fallback_request_sha256"] = "changed"
        d.write_json_atomic(path, record)
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        with pytest.raises(ValueError):
            continuation(prior, path)
    assert not (parent / "summary-resume-once.claim.json").exists()


@pytest.mark.parametrize("change", ["length", "unknown", "overflow", "empty"])
def test_hard_acceptance_conditions(prepared, change):
    _, plan, _, _, _, original, item = prepared
    response = d.read_json(item["path"])
    count = 550
    if change == "length":
        response["choices"][0]["finish_reason"] = "length"
    elif change == "unknown":
        response.pop("usage")
    elif change == "empty":
        response["choices"][0]["message"]["content"] = " "
    else:
        count = 4097
    with pytest.raises(ValueError):
        r.audit_response(plan, plan["rows"][5], original, response, count)


@pytest.mark.parametrize("failure", ["unknown", "length", "adoption_sha"])
def test_new_failure_manifest_preserves_cost_and_ancestors(tmp_path, prepared, failure):
    prior, _, corpus, parent, path, _, _ = prepared
    plan = continuation(prior, path)
    row = plan["rows"][5]
    old_sha = d.sha256_file(parent / "manifest.json")
    if failure == "adoption_sha":
        row["summary_adoption"]["sha256"] = "wrong"

    def builder(corpus, runner, directory, source):
        return runner.generate([], 4096, "summary")

    response = Mock(status_code=200)
    response.json.return_value = body("incomplete", "length")
    with (
        patch.object(e, "verify_plan", return_value=corpus),
        patch("scripts.e1_indexers.raptor_index", side_effect=builder),
        patch(
            "requests.Session.post",
            side_effect=requests.ConnectionError("timeout")
            if failure == "unknown"
            else None,
            return_value=response,
        ) as post,
    ):
        with pytest.raises((ValueError, requests.ConnectionError)):
            e.execute(plan, row, {"LITELLM_API_KEY": "test"})
    result = d.read_json(tmp_path / row["output"] / "manifest.json")
    assert result["status"] == "failed"
    summary = result["token_accounting"]["summary"]
    assert summary["attempts"] == (0 if failure == "adoption_sha" else 1)
    assert summary["complete"] == (failure != "unknown")
    assert summary["known_subtotal"]["llm_output_tokens"] == (
        5 if failure == "length" else 0
    )
    assert post.call_count == (0 if failure == "adoption_sha" else 1)
    reserve = e.current_unknown_reservation(tmp_path / row["output"])
    assert (reserve > 0) if failure == "unknown" else reserve == 0
    assert d.sha256_file(parent / "manifest.json") == old_sha


def test_new_embedding_overflow_stops_before_http(tmp_path, prepared):
    prior, _, _, _, path, _, _ = prepared
    plan = continuation(prior, path)
    row = plan["rows"][5]
    folder = tmp_path / row["output"]
    folder.mkdir()
    journal = Journal(
        folder / "usage.jsonl",
        run_id=row["run_id"],
        method="raptor",
        dataset="hotpotqa",
    )
    runner = e.Transport(plan, row, {}, folder, journal)
    runner.native_bge.count.return_value = 4097
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        with pytest.raises(ValueError, match="overflow_before_http"):
            runner.embed(["new summary"])
    assert journal.summary()["attempts"] == 0
    runner.close()


def test_continuation_physical_post_cap_precedes_http(tmp_path, prepared):
    prior, _, _, _, path, _, _ = prepared
    plan = continuation(prior, path)
    row = plan["rows"][5]
    folder = tmp_path / row["output"]
    folder.mkdir()
    journal = Journal(
        folder / "usage.jsonl",
        run_id=row["run_id"],
        method="raptor",
        dataset="hotpotqa",
    )
    runner = e.Transport(plan, row, {}, folder, journal)
    summary = journal.summary()
    summary["attempts"] = r.POLICY["max_new_posts"]
    with (
        patch.object(journal, "summary", return_value=summary),
        patch("requests.Session.request", side_effect=AssertionError("HTTP forbidden")),
    ):
        with pytest.raises(ValueError, match="request_limit_exceeded"):
            runner.generate([], 4096, "summary")
    assert journal.summary()["attempts"] == 0
    runner.close()


def network_fixture(tmp_path, prepared):
    prior, _, corpus, _, path, original, _ = prepared
    plan = continuation(prior, path)
    row = plan["rows"][5]
    pending = tmp_path / "native-plan.json"
    d.write_json_atomic(pending, plan)
    messages = [{"role": "user", "content": "next summary"}]

    def builder(corpus, runner, directory, source):
        runner.generate(original["messages"], 4096, "summary")
        runner.generate([], 4096, "summary")
        return runner.generate(messages, 4096, "summary")

    response = Mock(status_code=200)
    response.json.return_value = body("saved new summary")
    with (
        patch.object(e, "verify_plan", return_value=corpus),
        patch("scripts.e1_indexers.raptor_index", side_effect=builder),
        patch(
            "requests.Session.post",
            side_effect=[response, requests.ReadTimeout("TLS handshake")],
        ),
    ):
        with pytest.raises(requests.ReadTimeout):
            e.execute(plan, row, {"LITELLM_API_KEY": "test"})
    audit = tmp_path / "tls.log"
    audit.write_text(
        "do_handshake: The handshake operation timed out; read timeout=5; requests.exceptions.ReadTimeout",
        encoding="utf-8",
    )
    return pending, plan, row, audit, messages


def test_network_continuation_preserves_unknown_cache_and_total_limits(
    tmp_path, prepared
):
    prior, old, oldrow, audit, messages = network_fixture(tmp_path, prepared)
    plan = r.prepare_network_continuation(prior, audit)
    row = plan["rows"][5]
    reserve = e.current_unknown_reservation(tmp_path / oldrow["output"])
    assert row["token_limit"] == oldrow["token_limit"] - 15 - reserve
    assert row["max_new_posts"] == r.POLICY["max_new_posts"] - 2
    assert len(row["history_runs"]) == 3
    with pytest.raises(FileExistsError):
        r.prepare_network_continuation(prior, audit)
    folder = tmp_path / row["output"]
    folder.mkdir()
    journal = Journal(
        folder / "usage.jsonl",
        run_id=row["run_id"],
        method="raptor",
        dataset="hotpotqa",
    )
    runner = e.Transport(plan, row, {"LITELLM_API_KEY": "test"}, folder, journal)
    response = Mock(status_code=200)
    response.json.return_value = body("fresh answer")
    with patch("requests.Session.post", return_value=response) as post:
        text, _ = runner.generate([], 4096, "summary")
        assert text == "saved new summary"
        post.assert_not_called()
        with pytest.raises(ValueError, match="first_uncached_request_changed"):
            runner.generate([{"role": "user", "content": "wrong"}], 4096, "summary")
        post.assert_not_called()
        runner.generate(messages, 4096, "summary")
        assert post.call_count == 1
        assert post.call_args.kwargs["timeout"] == (30, 300)
        assert post.call_args.kwargs["allow_redirects"] is False
    assert journal.summary()["attempts"] == 1
    assert e.current_unknown_reservation(tmp_path / oldrow["output"]) == reserve
    runner.close()
    (tmp_path / "results/summary").mkdir(parents=True, exist_ok=True)
    before = e.export(old, prior)
    # The live child's new known usage is counted once, in addition to its history.
    after = e.export(plan, prior)
    public = after["rows"][5]
    assert public["network_first_request_sha256"] == row["network_first_request_key"]
    assert "network_first_request_key" not in public
    assert (
        before["budget_charge_upper_bound"] + 15 == after["budget_charge_upper_bound"]
    )
    assert before["physical_known_tokens"] + 15 == after["physical_known_tokens"]


@pytest.mark.parametrize(
    "change", ["audit", "reserve", "active", "exhausted", "second_stage"]
)
def test_network_rejects_unsafe_preparation_before_claim_or_http(
    tmp_path, prepared, change
):
    prior, plan, row, audit, _ = network_fixture(tmp_path, prepared)
    folder = tmp_path / row["output"]
    if change == "audit":
        audit.write_text("model read timed out after 300 seconds", encoding="utf-8")
    elif change == "active":
        (folder / "running.lock").write_text("1")
    elif change == "second_stage":
        plan["raptor_summary_network_resume"] = True
        d.write_json_atomic(prior, plan)
    elif change == "exhausted":
        row["max_new_posts"] = 0
        d.write_json_atomic(prior, plan)
    else:
        checkpoint = next(
            p
            for p in (folder / "requests").glob("*.json")
            if not p.name.endswith("response.json")
            and d.read_json(p)["status"] == "started"
        )
        saved = d.read_json(checkpoint)
        saved["reserved_tokens"] = 0
        d.write_json_atomic(checkpoint, saved)
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        with pytest.raises(ValueError):
            r.prepare_network_continuation(prior, audit)
    assert not (folder / "network-resume-once.claim.json").exists()


def test_network_second_timeout_is_saved_without_automatic_retry(tmp_path, prepared):
    prior, _, oldrow, audit, messages = network_fixture(tmp_path, prepared)
    plan = r.prepare_network_continuation(prior, audit)
    row = plan["rows"][5]
    old_sha = d.sha256_file(tmp_path / oldrow["output"] / "manifest.json")

    def builder(corpus, runner, directory, source):
        return runner.generate(messages, 4096, "summary")

    with (
        patch.object(e, "verify_plan", return_value=[]),
        patch("scripts.e1_indexers.raptor_index", side_effect=builder),
        patch(
            "requests.Session.post",
            side_effect=requests.ReadTimeout("new connection timeout"),
        ) as post,
    ):
        with pytest.raises(requests.ReadTimeout):
            e.execute(plan, row, {"LITELLM_API_KEY": "test"})
    result = d.read_json(tmp_path / row["output"] / "manifest.json")
    assert result["status"] == "failed"
    assert result["token_accounting"]["summary"]["attempts"] == 1
    assert not result["token_accounting"]["summary"]["complete"]
    assert post.call_count == 1
    assert e.current_unknown_reservation(tmp_path / row["output"]) > 0
    assert d.sha256_file(tmp_path / oldrow["output"] / "manifest.json") == old_sha


@pytest.mark.parametrize("change", ["audit_sha", "first_key", "prior_attempts"])
def test_network_runtime_binding_tampering_has_zero_http(tmp_path, prepared, change):
    prior, _, _, audit, _ = network_fixture(tmp_path, prepared)
    plan = r.prepare_network_continuation(prior, audit)
    row = plan["rows"][5]
    if change == "audit_sha":
        audit.write_text("changed", encoding="utf-8")
    elif change == "first_key":
        row["network_first_request_key"] = "changed"
    else:
        row["network_prior_attempts"] += 1
        row["max_new_posts"] -= 1
    folder = tmp_path / row["output"]
    folder.mkdir()
    journal = Journal(
        folder / "usage.jsonl",
        run_id=row["run_id"],
        method="raptor",
        dataset="hotpotqa",
    )
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        with pytest.raises(ValueError):
            e.Transport(plan, row, {}, folder, journal)
    assert journal.summary()["attempts"] == 0
