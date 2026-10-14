"""Offline checks for bounded target OpenIE execution and accounting."""

import hashlib
import json
from types import SimpleNamespace

import pytest
import requests

from scripts import preflight_hipporag_repair_prompts as preflight


def fixture():
    cases = [
        {
            "source_attempt": {
                "stage": "openie_ner",
                "passage_id": f"p{i}",
                "status": "truncated",
            },
            "messages": [{"role": "user", "content": "private passage"}],
        }
        for i in range(5)
    ]
    snapshot = json.dumps(cases).encode()
    rows = [
        {
            "stage": "openie_ner",
            "passage_id": f"p{i}",
            "input_tokens": 2,
            "output_cap": 1024,
            "total_reserved": 1026,
            "rendered_sha256": hashlib.sha256(b"rendered").hexdigest(),
        }
        for i in range(5)
    ]
    counts = {
        "source_snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
        "cases": rows,
        "context_window": 262144,
        "options": {"add_generation_prompt": True, "enable_thinking": False},
    }

    class Tokenizer:
        def apply_chat_template(self, messages, *, tokenize, **options):
            assert options == counts["options"]
            return [1, 2] if tokenize else "rendered"

        def encode(self, text, *, add_special_tokens):
            assert not add_special_tokens
            return [1, 2]

    return cases, snapshot, counts, Tokenizer()


@pytest.mark.parametrize("bad", ["snapshot", "count", "render", "identity", "window"])
def test_native_input_mismatch_blocks_transport(bad):
    _, snapshot, counts, tokenizer = fixture()
    if bad == "snapshot":
        snapshot += b" "
    elif bad == "count":
        counts["cases"][0]["input_tokens"] += 1
    elif bad == "render":
        counts["cases"][0]["rendered_sha256"] = "bad"
    elif bad == "identity":
        counts["cases"][0]["passage_id"] = "different"
    else:
        counts["context_window"] = 1025
    with pytest.raises(ValueError):
        preflight.verify_native_cases(snapshot, counts, tokenizer)


def test_native_inputs_are_checked_and_shared_claim_prevents_replay(tmp_path):
    cases, snapshot, counts, tokenizer = fixture()
    assert preflight.verify_native_cases(snapshot, counts, tokenizer) == cases
    claim = preflight.claim_target_cases(
        tmp_path, counts["source_snapshot_sha256"], "first-output-dir"
    )
    with pytest.raises(FileExistsError):
        preflight.claim_target_cases(
            tmp_path, counts["source_snapshot_sha256"], "another-output-dir"
        )
    assert json.loads(claim.read_text())["run_id"] == "first-output-dir"


@pytest.mark.parametrize(
    "mode,expected_attempts",
    [
        ("success", 5),
        ("count_mismatch", 1),
        ("unknown_usage", 1),
        ("truncated", 1),
        ("timeout", 1),
    ],
)
def test_execution_stops_on_first_problem_and_persists_cost(
    tmp_path, monkeypatch, mode, expected_attempts
):
    cases, _, counts, _ = fixture()
    session = requests.Session()
    calls = []

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            body = {
                "choices": [
                    {
                        "finish_reason": "length" if mode == "truncated" else "stop",
                        "message": {"content": '{"named_entities":["entity"]}'},
                    }
                ]
            }
            if mode != "unknown_usage":
                body["usage"] = {
                    "prompt_tokens": 3 if mode == "count_mismatch" else 2,
                    "completion_tokens": 4,
                }
            return body

    def post(url, **kwargs):
        calls.append(kwargs)
        if mode == "timeout":
            raise requests.ReadTimeout()
        return Response()

    monkeypatch.setattr(session, "post", post)
    config = {
        "base_url": "https://example.invalid/v1",
        "model": "iairlab/qwen3.8-27b",
        "key": "fake-secret",
    }

    def parse(*args, **kwargs):
        return ["entity"]

    directory = tmp_path / "run"
    result = preflight.execute_target_cases(
        cases, counts, config, parse, session, directory, "r"
    )
    assert (
        len(calls)
        == result["token_accounting"]["summary"]["attempts"]
        == expected_attempts
    )
    assert result["ready_for_indexing"] is False
    assert result["status"] == ("completed" if mode == "success" else "failed")
    assert result["server_usage_verified"] == (mode == "success")
    assert result["token_accounting"]["summary"]["complete"] == (
        mode not in ("unknown_usage", "timeout")
    )
    assert all(
        call["allow_redirects"] is False and call["timeout"] == (5, 120)
        for call in calls
    )
    assert (directory / "manifest.json").is_file()
    assert "fake-secret" not in (directory / "manifest.json").read_text()


def test_retry_adapter_is_refused(tmp_path):
    cases, _, counts, _ = fixture()
    session = SimpleNamespace(
        get_adapter=lambda url: SimpleNamespace(max_retries=SimpleNamespace(total=1))
    )
    result = preflight.execute_target_cases(
        cases,
        counts,
        {"base_url": "https://example.invalid/v1", "model": "iairlab/qwen3.8-27b"},
        None,
        session,
        tmp_path / "run",
        "r",
    )
    assert result["error_code"] == "transport_retries_must_be_zero"
    assert result["token_accounting"]["summary"]["attempts"] == 0
