"""Offline contract checks for the bounded target API smoke test."""

import json

import pytest
import requests

from scripts.check_target_api import (
    finite_embeddings,
    run,
    safe_json,
    save_run,
    settings,
)


def config():
    return settings(
        {
            "TARGET_API_BASE_URL": "https://example.test/v1",
            "LITELLM_API_KEY": "TEST-SECRET",
            "TARGET_API_MODEL": "iairlab/qwen3.8-27b",
        }
    )


class Reply:
    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


class LocalSession:
    def __init__(self, prompt_tokens=8):
        self.prompt_tokens = prompt_tokens
        self.post_count = 0

    def get(self, url, **kwargs):
        assert url.endswith("/api/tags")
        return Reply({"models": [{"name": "bge-m3:latest", "digest": "digest-1"}]})

    def post(self, url, **kwargs):
        self.post_count += 1
        assert kwargs["json"]["truncate"] is False
        assert len(kwargs["json"]["input"]) == 2
        return Reply(
            {
                "embeddings": [[0.1, 0.2], [0.3, 0.4]],
                "prompt_eval_count": self.prompt_tokens,
            }
        )


class RemoteSession:
    def __init__(
        self,
        usage=True,
        status=200,
        content="четыре",
        prompt_tokens=20,
        total_tokens=None,
        expected_max_tokens=32,
        thinking_switch="chat-template",
    ):
        self.usage = usage
        self.status = status
        self.content = content
        self.prompt_tokens = prompt_tokens
        self.total_tokens = total_tokens
        self.expected_max_tokens = expected_max_tokens
        self.thinking_switch = thinking_switch
        self.post_count = 0

    def post(self, url, **kwargs):
        self.post_count += 1
        assert url == "https://example.test/v1/chat/completions"
        assert kwargs["allow_redirects"] is False
        if self.thinking_switch == "chat-template":
            assert kwargs["json"]["chat_template_kwargs"] == {"enable_thinking": False}
            assert "enable_thinking" not in kwargs["json"]
        else:
            assert kwargs["json"]["enable_thinking"] is False
        assert kwargs["json"]["max_tokens"] == self.expected_max_tokens
        if self.status != 200:
            return Reply(status=self.status)
        return Reply(
            {
                "id": "response-1",
                "model": "iairlab/qwen3.8-27b",
                "choices": [
                    {"message": {"content": self.content}, "finish_reason": "stop"}
                ],
                "usage": (
                    self.usage
                    if isinstance(self.usage, dict)
                    else {
                        "prompt_tokens": self.prompt_tokens,
                        "completion_tokens": 2,
                        "total_tokens": self.total_tokens,
                    }
                    if self.usage
                    else None
                ),
            }
        )


def test_settings_require_key_and_https_before_requests():
    with pytest.raises(ValueError, match="LITELLM_API_KEY"):
        settings(
            {"TARGET_API_BASE_URL": "https://example.test/v1", "TARGET_API_MODEL": "m"}
        )
    with pytest.raises(ValueError, match="HTTPS"):
        settings(
            {
                "TARGET_API_BASE_URL": "http://example.test/v1",
                "LITELLM_API_KEY": "x",
                "TARGET_API_MODEL": "m",
            }
        )


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"embeddings": [[1.0]]}, "embedding_count_mismatch"),
        ({"embeddings": [[1.0], [1.0, 2.0]]}, "embedding_dimension_mismatch"),
        ({"embeddings": [[1.0], [float("nan")]]}, "embedding_non_finite"),
        ({"embeddings": [[1.0], [float("inf")]]}, "embedding_non_finite"),
    ],
)
def test_invalid_embeddings_stop_before_generation(payload, error):
    with pytest.raises(ValueError, match=error):
        finite_embeddings(payload)


def test_success_has_one_local_and_one_remote_request_with_separate_usage():
    local, remote = LocalSession(), RemoteSession()
    result = run(config(), local, remote)
    assert result["status"] == "verified"
    assert result["embeddings"]["dimension"] == 2
    assert result["embeddings"]["prompt_tokens"] == 8
    assert result["generation"]["prompt_tokens"] == 20
    assert result["generation"]["completion_tokens"] == 2
    assert (local.post_count, remote.post_count) == (1, 1)
    assert "TEST-SECRET" not in safe_json(result, "TEST-SECRET")


def test_missing_local_usage_stops_before_remote_request():
    local, remote = LocalSession(prompt_tokens=None), RemoteSession()
    result = run(config(), local, remote)
    assert result["error_kind"] == "local_embedding_usage_missing"
    assert result["embeddings"]["status"] == "blocked"
    assert remote.post_count == 0


def test_excess_local_usage_stops_before_remote_request():
    remote = RemoteSession()
    result = run(config(), LocalSession(prompt_tokens=50_001), remote)
    assert result["error_kind"] == "local_embedding_token_limit_exceeded"
    assert result["embeddings"]["prompt_tokens"] == 50_001
    assert result["request_attempts"]["remote_generation"] == 0
    assert remote.post_count == 0


def test_empty_remote_content_records_blocker_without_retry():
    remote = RemoteSession(content=None)
    result = run(config(), LocalSession(), remote)
    assert result["status"] == "blocked"
    assert result["generation"]["error_kind"] == "remote_answer_missing"
    assert result["generation"]["prompt_tokens"] == 20
    assert result["generation"]["request_parameters"]["max_tokens"] == 32
    assert result["request_attempts"] == {"local_embedding": 1, "remote_generation": 1}
    assert remote.post_count == 1


def test_combined_token_limit_blocks_even_if_remote_alone_is_below_limit():
    result = run(config(), LocalSession(), RemoteSession(prompt_tokens=49_995))
    assert result["status"] == "blocked"
    assert result["error_kind"] == "combined_token_limit_exceeded"


def test_reported_total_tokens_also_enforces_limit():
    result = run(config(), LocalSession(), RemoteSession(total_tokens=50_001))
    assert result["status"] == "blocked"
    assert result["error_kind"] == "remote_token_limit_exceeded"
    assert result["generation"]["prompt_tokens"] == 20
    assert result["generation"]["completion_tokens"] == 2
    assert result["generation"]["total_tokens_reported"] == 50_001
    assert result["generation"]["usage_status"] == "complete"


def test_partial_remote_usage_is_preserved_when_check_stops():
    remote = RemoteSession(usage={"prompt_tokens": 17})
    result = run(config(), LocalSession(), remote)
    assert result["status"] == "blocked"
    assert result["error_kind"] == "remote_usage_missing"
    assert result["generation"]["prompt_tokens"] == 17
    assert result["generation"]["completion_tokens"] is None
    assert result["generation"]["usage_status"] == "partial"
    assert remote.post_count == 1


def test_known_partial_total_above_limit_is_preserved():
    remote = RemoteSession(usage={"prompt_tokens": 17, "total_tokens": 50_001})
    result = run(config(), LocalSession(), remote)
    assert result["error_kind"] == "remote_token_limit_exceeded"
    assert result["generation"]["prompt_tokens"] == 17
    assert result["generation"]["total_tokens_reported"] == 50_001
    assert result["generation"]["usage_status"] == "partial"


def test_bounded_generation_diagnostic_skips_local_embedding():
    class NoLocalCalls:
        def get(self, *args, **kwargs):
            raise AssertionError("local GET is not allowed in generation-only mode")

        def post(self, *args, **kwargs):
            raise AssertionError("local POST is not allowed in generation-only mode")

    remote = RemoteSession(expected_max_tokens=256)
    result = run(config(), NoLocalCalls(), remote, generation_only=True, max_tokens=256)
    assert result["status"] == "verified"
    assert result["request_attempts"] == {"local_embedding": 0, "remote_generation": 1}
    assert result["generation"]["request_parameters"]["max_tokens"] == 256
    assert remote.post_count == 1


def test_chat_template_switch_is_sent_without_top_level_switch():
    remote = RemoteSession(expected_max_tokens=64, thinking_switch="chat-template")
    result = run(
        config(),
        LocalSession(),
        remote,
        generation_only=True,
        max_tokens=64,
        thinking_switch="chat-template",
    )
    assert result["status"] == "verified"
    assert result["generation"]["request_parameters"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    assert remote.post_count == 1


def test_legacy_top_level_switch_remains_available_for_diagnostics():
    remote = RemoteSession(expected_max_tokens=64, thinking_switch="top-level")
    result = run(
        config(),
        LocalSession(),
        remote,
        generation_only=True,
        max_tokens=64,
        thinking_switch="top-level",
    )
    assert result["status"] == "verified"
    assert result["generation"]["request_parameters"]["enable_thinking"] is False
    assert remote.post_count == 1


@pytest.mark.parametrize(
    "remote,expected",
    [
        (RemoteSession(usage=False), "remote_usage_missing"),
        (RemoteSession(status=401), "http_401"),
    ],
)
def test_remote_failure_stops_without_retry_and_reports_safe_reason(remote, expected):
    result = run(config(), LocalSession(), remote)
    assert result["status"] == "blocked"
    assert result["error_kind"] == expected
    assert remote.post_count == 1
    assert "TEST-SECRET" not in json.dumps(result)


def test_report_redacts_secret_even_if_backend_echoes_it():
    assert "TEST-SECRET" not in safe_json({"answer": "TEST-SECRET"}, "TEST-SECRET")


def test_existing_report_is_not_overwritten_or_followed_by_requests(tmp_path):
    output = tmp_path / "report.json"
    output.write_text("existing", encoding="utf-8")
    local, remote = LocalSession(), RemoteSession()
    with pytest.raises(FileExistsError):
        save_run(output, config(), local, remote)
    assert output.read_text(encoding="utf-8") == "existing"
    assert (local.post_count, remote.post_count) == (0, 0)


def test_unwritable_report_stops_before_requests(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    original_open = type(output).open

    def denied_open(path, *args, **kwargs):
        if path == output:
            raise PermissionError("unwritable report")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(type(output), "open", denied_open)
    local, remote = LocalSession(), RemoteSession()
    with pytest.raises(PermissionError, match="unwritable report"):
        save_run(output, config(), local, remote)
    assert (local.post_count, remote.post_count) == (0, 0)


def test_reserved_report_cannot_be_replaced_during_request(tmp_path):
    output = tmp_path / "report.json"

    class RacingRemote(RemoteSession):
        def post(self, url, **kwargs):
            with pytest.raises(FileExistsError):
                output.open("x", encoding="utf-8")
            return super().post(url, **kwargs)

    result = save_run(output, config(), LocalSession(), RacingRemote())
    assert result["status"] == "verified"
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "verified"
