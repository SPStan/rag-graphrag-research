"""Run the published historical operator with fake HTTP and isolated input files."""

from pathlib import Path
import runpy
import sys
from types import SimpleNamespace

import pytest
import requests

from scripts import run_dense as dense
from scripts.token_accounting import Journal, recorded_call

OPERATOR = Path(__file__).resolve().parents[1] / "docs/operators/operator.py"


@pytest.fixture
def operator_fixture(tmp_path, monkeypatch):
    root = tmp_path
    program = root / "docs/operators/operator.py"
    program.parent.mkdir(parents=True)
    program.write_bytes(OPERATOR.read_bytes())
    prior_dir = root / "results/raw/raptor-smoke/prior"
    prior_dir.mkdir(parents=True)
    prior_journal = Journal(
        prior_dir / "tokens.jsonl", run_id="prior", method="raptor", dataset="musique"
    )

    def old_timeout():
        raise requests.ReadTimeout()

    with pytest.raises(requests.ReadTimeout):
        recorded_call(
            prior_journal,
            old_timeout,
            phase="index",
            operation="summary",
            provider="target_api",
            model="qwen",
            kind="llm",
        )
    prior_path = prior_dir / "manifest.json"
    dense.write_json_atomic(
        prior_path,
        {
            "run_id": "prior",
            "generation": {"base_url": "https://example.invalid/v1"},
            "token_accounting": prior_journal.reference(),
        },
    )
    request_path = prior_dir / "index-summary-50.request.json"
    dense.write_json_atomic(
        request_path,
        {
            "model": "qwen",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": "A short passage"}],
        },
    )
    baseline_path = root / "results/summary/raptor-smoke.json"

    def update_baseline():
        dense.write_json_atomic(
            baseline_path,
            {
                "run_id": "prior",
                "artifacts": {
                    "manifest_sha256": dense.sha256_file(prior_path),
                    "first_summary_request_sha256": dense.sha256_file(request_path),
                },
            },
        )

    update_baseline()
    env_file = root / "target.env"
    env_file.write_text(
        "TARGET_API_BASE_URL=https://example.invalid/v1\nTARGET_API_MODEL=qwen\nLITELLM_API_KEY=test-only\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGET_API_ENV_FILE", str(env_file))
    monkeypatch.setattr(dense, "git_snapshot", lambda: {"commit": "offline-fixture"})
    calls = []

    def run(body=None, timeout=False):
        class Response:
            status_code = 200

            def json(self):
                return body

            def raise_for_status(self):
                pass

        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            if timeout:
                raise requests.ReadTimeout()
            return Response()

        monkeypatch.setattr(requests.Session, "post", post)
        original_path = sys.path.copy()
        try:
            runpy.run_path(str(program), run_name="__main__")
        finally:
            sys.path[:] = original_path

    return root, request_path, update_baseline, calls, run


def reply(usage=True):
    body = {
        "choices": [
            {"finish_reason": "stop", "message": {"content": "A useful summary."}}
        ]
    }
    if usage:
        body["usage"] = {"prompt_tokens": 350, "completion_tokens": 375}
    return body


def manifest(root):
    return dense.read_json(
        next((root / "results/raw/raptor-summary-diagnostic").glob("*/manifest.json"))
    )


def test_published_operator_makes_one_post_and_refuses_second(operator_fixture):
    root, _, _, calls, run = operator_fixture
    run(reply())
    result = manifest(root)
    assert result["status"] == "completed"
    assert result["token_accounting"]["summary"]["attempts"] == len(calls) == 1
    assert result["token_accounting"]["summary"]["complete"]
    assert not result["aggregate_accounting"]["complete"]
    assert result["aggregate_total"] is None
    assert result["aggregate_accounting"]["known_subtotal"]["llm_input_tokens"] == 350
    assert not result["tree_or_reader_started"]
    assert calls[0][1]["timeout"] == (5, 300)
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["json"]["max_tokens"] == 512
    with pytest.raises(FileExistsError):
        run(reply())
    assert len(calls) == 1


@pytest.mark.parametrize("problem", ["timeout", "missing_usage"])
def test_operator_stops_and_retains_unknown_usage(operator_fixture, problem):
    root, _, _, calls, run = operator_fixture
    with pytest.raises(SystemExit) as exc:
        run(reply(usage=problem != "missing_usage"), timeout=problem == "timeout")
    assert exc.value.code == 1
    result = manifest(root)
    assert result["status"] == "failed"
    assert len(calls) == 1
    assert not result["token_accounting"]["summary"]["complete"]
    assert not result["aggregate_accounting"]["complete"]
    assert result["aggregate_total"] is None
    with pytest.raises(FileExistsError):
        run(reply())
    assert len(calls) == 1


@pytest.mark.parametrize("problem", ["request_sha", "budget"])
def test_operator_input_guards_fail_before_http(operator_fixture, problem):
    _, request_path, update_baseline, calls, run = operator_fixture
    payload = dense.read_json(request_path)
    payload["messages"][0]["content"] = "x" * 6000
    dense.write_json_atomic(request_path, payload)
    if problem == "budget":
        update_baseline()
    with pytest.raises(
        ValueError,
        match="SHA mismatch" if problem == "request_sha" else "budget mismatch",
    ):
        run(reply())
    assert calls == []


def test_operator_refuses_retry_adapter_before_http(operator_fixture, monkeypatch):
    root, _, _, calls, run = operator_fixture
    monkeypatch.setattr(
        requests.Session,
        "get_adapter",
        lambda *args: SimpleNamespace(max_retries=SimpleNamespace(total=1)),
    )
    with pytest.raises(SystemExit):
        run(reply())
    assert calls == []
    result = manifest(root)
    assert result["status"] == "failed"
    assert result["token_accounting"]["summary"]["attempts"] == 0
