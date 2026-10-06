"""Offline contract checks for the bounded target API smoke test."""

import json

import pytest
import requests

from scripts.check_target_api import finite_embeddings, run, safe_json, settings


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
    ):
        self.usage = usage
        self.status = status
        self.content = content
        self.prompt_tokens = prompt_tokens
        self.total_tokens = total_tokens
        self.post_count = 0

    def post(self, url, **kwargs):
        self.post_count += 1
        assert url == "https://example.test/v1/chat/completions"
        assert kwargs["allow_redirects"] is False
        assert kwargs["json"]["enable_thinking"] is False
        assert kwargs["json"]["max_tokens"] == 32
        if self.status != 200:
            return Reply(status=self.status)
        return Reply(
            {
                "id": "response-1",
                "model": "iairlab/qwen3.8-27b",
                "choices": [
                    {"message": {"content": self.content}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": self.prompt_tokens,
                    "completion_tokens": 2,
                    "total_tokens": self.total_tokens,
                }
                if self.usage
                else None,
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
