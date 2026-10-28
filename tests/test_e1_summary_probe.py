from unittest.mock import Mock, patch

import pytest
import requests

from scripts import run_e1 as e
from scripts import run_dense as d
from scripts.token_accounting import Journal
from tests.test_e1_raptor_resume import fixture, save


def setup_probe(tmp_path):
    prior, plan, corpus, _, _ = fixture(tmp_path)
    row = plan["rows"][5]
    folder = tmp_path / row["output"]
    folder.mkdir()
    journal = Journal(
        folder / "usage.jsonl",
        run_id=row["run_id"],
        method="raptor",
        dataset="hotpotqa",
    )
    runner = e.Transport(plan, row, {"LITELLM_API_KEY": "test-secret"}, folder, journal)
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": "Write a summary of the following, including as many key details as possible: supplied text:",
        },
    ]
    response = Mock(status_code=200)
    response.json.return_value = body("unfinished", "length")
    runner.session.post = Mock(return_value=response)
    with pytest.raises(ValueError, match="generation_not_complete"):
        runner.generate(messages, 4096, "summary")
    save(folder, row["run_id"], journal, "failed", error_type="ValueError")
    recovered = tmp_path / "recovered.json"
    payload = {
        **e.target.OPTIONS,
        "model": plan["model"],
        "messages": messages,
        "max_tokens": 4096,
    }
    d.write_json_atomic(recovered, payload)
    return prior, plan, corpus, folder, recovered


def body(text="A concise supported summary.", reason="stop"):
    return {
        "choices": [{"finish_reason": reason, "message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


@pytest.mark.parametrize("broken", [None, "payload", "active", "dirty", "artifact"])
def test_prepare_summary_probe_rejects_changed_inputs_without_http(tmp_path, broken):
    with patch.object(e, "ROOT", tmp_path):
        prior, plan, corpus, folder, recovered = setup_probe(tmp_path)
    if broken == "payload":
        payload = d.read_json(recovered)
        payload["messages"][1]["content"] += "changed"
        d.write_json_atomic(recovered, payload)
    elif broken == "active":
        (folder / "running.lock").write_text("1", encoding="utf-8")
    elif broken == "artifact":
        next((folder / "requests").glob("*.response.json")).write_text(
            "{}", encoding="utf-8"
        )
    with (
        patch.object(e, "ROOT", tmp_path),
        patch.object(e, "git", return_value="pin"),
        patch.object(e, "code_dirty", return_value=broken == "dirty"),
        patch.object(e, "load_corpus", return_value=(corpus, {})),
        patch("requests.Session.request", side_effect=AssertionError("HTTP forbidden")),
    ):
        if broken:
            with pytest.raises(ValueError):
                e.prepare_summary_probe(prior, recovered)
        else:
            prepared = e.prepare_summary_probe(prior, recovered)
            original = d.read_json(recovered)
            assert prepared["payload"]["messages"][1] == original["messages"][1]
            assert prepared["max_new_posts"] == 1
            assert not prepared["full_index_authorized"]
            assert prepared["payload"]["max_tokens"] == 1536
            assert prepared["remaining_before_probe"] == e.LIMITS["raptor"] - 15
            assert (
                prepared["reserved_tokens_upper_bound"]
                < prepared["remaining_before_probe"]
            )
        assert not (folder / "summary-probe-once.claim.json").exists()


@pytest.mark.parametrize("outcome", ["success", "length", "unknown", "word_limit"])
def test_summary_probe_one_post_claim_and_cost_survive_failure(tmp_path, outcome):
    with patch.object(e, "ROOT", tmp_path):
        prior, original, corpus, folder, recovered = setup_probe(tmp_path)
    config = {
        "LITELLM_API_KEY": "test-secret",
        "TARGET_API_MODEL": original["model"],
        "TARGET_API_BASE_URL": original["endpoint"],
    }
    with (
        patch.object(e, "ROOT", tmp_path),
        patch.object(e, "git", return_value="pin"),
        patch.object(e, "code_dirty", return_value=False),
        patch.object(e, "load_corpus", return_value=(corpus, {})),
    ):
        prepared = e.prepare_summary_probe(prior, recovered)
        probe = tmp_path / "probe.json"
        d.write_json_atomic(probe, prepared)
        approved = d.sha256_file(probe)
        (tmp_path / "results/summary").mkdir(parents=True)
        before = e.export(original, prior)
        response = Mock(status_code=200)
        response.json.return_value = body(
            "x " * 301 if outcome == "word_limit" else "compact summary",
            "length" if outcome == "length" else "stop",
        )

        def post(*args, **kwargs):
            assert (folder / "summary-probe-once.claim.json").exists()
            assert kwargs["allow_redirects"] is False
            if outcome == "unknown":
                raise requests.ConnectionError("timeout")
            return response

        with patch("requests.Session.post", side_effect=post) as sent:
            if outcome == "success":
                output = e.execute_summary_probe(probe, config, approved)
            else:
                with pytest.raises((ValueError, requests.ConnectionError)):
                    e.execute_summary_probe(probe, config, approved)
                output = folder.parent / "hotpotqa-summary-probe1"
            assert sent.call_count == 1
            with pytest.raises((ValueError, FileExistsError)):
                e.execute_summary_probe(probe, config, approved)
            assert sent.call_count == 1
        result = d.read_json(output / "manifest.json")
        assert result["status"] == ("completed" if outcome == "success" else "failed")
        assert not result["full_index_authorized"]
        assert result["token_accounting"]["summary"]["complete"] == (
            outcome != "unknown"
        )
        assert result["unknown_reserved_upper_bound"] == (
            prepared["reserved_tokens_upper_bound"] if outcome == "unknown" else 0
        )
        assert (
            d.sha256_file(folder / "manifest.json")
            == prepared["parent_manifest_sha256"]
        )
        report = e.export(original, prior)
        hotpot = next(
            r
            for r in report["rows"]
            if (r["method"], r["dataset"]) == ("raptor", "hotpotqa")
        )
        assert hotpot["cumulative_accounting"]["known_subtotal"][
            "llm_output_tokens"
        ] == (5 if outcome == "unknown" else 10)
        assert hotpot["summary_probe"]["status"] == result["status"]

        assert report["physical_known_tokens"] == before["physical_known_tokens"] + (
            0 if outcome == "unknown" else 15
        )
        assert report["budget_charge_upper_bound"] == before[
            "budget_charge_upper_bound"
        ] + (prepared["reserved_tokens_upper_bound"] if outcome == "unknown" else 15)


def test_summary_probe_invalid_sha_has_no_claim_or_http(tmp_path):
    probe = tmp_path / "probe.json"
    d.write_json_atomic(probe, {})
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        with pytest.raises(ValueError, match="exact_approved_sha"):
            e.execute_summary_probe(probe, {}, "wrong")


@pytest.mark.parametrize("options", [{}, {"allow_length": True}])
def test_partial_summary_is_never_a_usable_checkpoint(tmp_path, options):
    with patch.object(e, "ROOT", tmp_path):
        _, _, _, folder, _ = setup_probe(tmp_path)
    with pytest.raises(ValueError, match="resume_success_checkpoint_invalid"):
        e.verified_checkpoints(folder / "manifest.json", **options)
    cache, failures, _ = e.verified_checkpoints(
        folder / "manifest.json", allow_summary_length=True
    )
    assert not cache
    assert len(failures) == 1


def test_summary_probe_rejects_reported_output_beyond_cap():
    response = body()
    response["usage"]["completion_tokens"] = 1537
    with pytest.raises(ValueError, match="output_not_compact_complete"):
        e.validate_summary_probe(response)
