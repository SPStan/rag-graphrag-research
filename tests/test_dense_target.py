"""Offline checks of the target Dense path, including real Requests transport."""

import io
import json

import pytest
import requests
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.response import HTTPResponse

from scripts import run_dense_target as target
from scripts.token_accounting import Journal, verified_reference


def response(payload):
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps(payload).encode()
    return result


@pytest.fixture
def setup(tmp_path, monkeypatch):
    queries = [{"id": f"q{i}", "question": f"Question {i}?"} for i in range(5)]
    corpus = [
        {"id": f"p{i}", "title": f"T{i}", "text": f"Passage {i}"} for i in range(5)
    ]
    labels = [
        {"id": q["id"], "answer": "yes", "supporting_ids": ["p0"]} for q in queries
    ]
    plan = {"dataset": "musique", "question_ids": [q["id"] for q in queries]}
    config = {
        "model": "iairlab/qwen3.8-27b",
        "embedding_model": "bge-m3:latest",
        "key": "private-key",
        "base_url": "https://api.example/v1",
        "ollama_url": "http://127.0.0.1:11434",
    }
    local, remote = requests.Session(), requests.Session()
    monkeypatch.setattr(
        local,
        "get",
        lambda *a, **k: response(
            {"models": [{"name": "bge-m3:latest", "digest": "sha256:test"}]}
        ),
    )
    monkeypatch.setattr(
        local,
        "post",
        lambda url, **k: response(
            {
                "embeddings": [[1.0] + [0.0] * 1023 for _ in k["json"]["input"]],
                "prompt_eval_count": 7,
            }
        ),
    )
    calls = []

    def reader(url, **kwargs):
        calls.append(kwargs["json"])
        return response(
            {
                "model": config["model"],
                "choices": [
                    {"message": {"content": "Answer: yes"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 23, "completion_tokens": 4},
            }
        )

    monkeypatch.setattr(remote, "post", reader)
    return plan, queries, corpus, labels, config, local, remote, tmp_path, calls


@pytest.mark.parametrize("dataset", ["musique", "hotpotqa"])
def test_target_path_evaluates_each_id_without_gold_in_messages(setup, dataset):
    plan, queries, corpus, labels, config, local, remote, path, calls = setup
    plan["dataset"] = dataset
    manifest_path, manifest = target.execute(
        plan, queries, corpus, labels, config, local, remote, path
    )
    assert manifest["status"] == "completed"
    assert manifest["observed_question_ids"] == plan["question_ids"]
    assert manifest["uncompleted_question_ids"] == []
    assert len(calls) == 5
    assert all(
        payload["messages"][-1]["content"].endswith(
            f"Question: {query['question']}\nThought: "
        )
        for payload, query in zip(calls, queries)
    )
    assert all("supporting_ids" not in json.dumps(payload) for payload in calls)
    assert all(
        "Answer: yes" not in payload["messages"][-1]["content"] for payload in calls
    )
    accounting = verified_reference(manifest, manifest_path)
    assert accounting["summary"]["attempts"] == 11
    assert accounting["summary"]["known_subtotal"] == {
        "llm_input_tokens": 115,
        "llm_output_tokens": 20,
        "embedding_input_tokens": 42,
    }
    metrics = json.loads(
        manifest_path.with_suffix(".json")
        .with_name(manifest_path.name.replace("manifest", "metrics"))
        .read_text()
    )
    assert metrics["questions_evaluated"] == 5
    assert metrics["em"] == 1


def test_missing_usage_stops_without_next_question(setup, monkeypatch):
    plan, queries, corpus, labels, config, local, remote, path, _ = setup
    calls = []

    def missing(*a, **k):
        calls.append(1)
        return response(
            {
                "choices": [
                    {"message": {"content": "Answer: yes"}, "finish_reason": "stop"}
                ]
            }
        )

    monkeypatch.setattr(remote, "post", missing)
    manifest_path, manifest = target.execute(
        plan, queries, corpus, labels, config, local, remote, path
    )
    assert len(calls) == 1
    assert manifest["status"] == "failed"
    assert manifest["uncompleted_question_ids"] == plan["question_ids"]
    assert manifest["errors"][0]["reason"] == "missing_usage_stop"
    summary = verified_reference(manifest, manifest_path)["summary"]
    assert not summary["complete"]
    assert summary["known_subtotal"]["embedding_input_tokens"] == 14


def test_invalid_reader_preserves_usage_before_stop(setup, monkeypatch):
    plan, queries, corpus, labels, config, local, remote, path, _ = setup
    monkeypatch.setattr(
        remote,
        "post",
        lambda *a, **k: response(
            {
                "choices": [
                    {"message": {"content": "No marker"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 23, "completion_tokens": 4},
            }
        ),
    )
    _, manifest = target.execute(
        plan, queries, corpus, labels, config, local, remote, path
    )
    assert manifest["status"] == "failed"
    assert (
        manifest["token_accounting"]["summary"]["known_subtotal"]["llm_input_tokens"]
        == 23
    )
    assert manifest["token_accounting"]["summary"]["attempts"] == 3


def test_actual_requests_adapter_does_not_retry_500(tmp_path, monkeypatch):
    attempts = []

    def http_response(*args, **kwargs):
        attempts.append(1)
        return HTTPResponse(body=io.BytesIO(b"{}"), status=500, preload_content=False)

    monkeypatch.setattr(HTTPConnectionPool, "_make_request", http_response)
    journal = Journal(
        tmp_path / "run.tokens.jsonl",
        run_id="test",
        method="dense",
        dataset="synthetic",
    )
    with requests.Session() as session:
        assert session.get_adapter("http://127.0.0.1").max_retries.total == 0
        with pytest.raises(requests.HTTPError):
            target.checked_post(
                session,
                "http://127.0.0.1:9/chat",
                {},
                journal,
                phase="reader",
                operation="reader",
                provider="target_api",
                model="fake",
                kind="llm",
                object_id="q",
            )
    assert len(attempts) == 1
    assert journal.summary()["attempts"] == 1
    assert not journal.summary()["complete"]


def test_budget_blocks_before_transport(tmp_path):
    journal = Journal(
        tmp_path / "run.tokens.jsonl",
        run_id="test",
        method="dense",
        dataset="synthetic",
    )
    with requests.Session() as session, pytest.raises(ValueError, match="reservation"):
        target.checked_post(
            session,
            "https://example.invalid",
            {"messages": "x" * target.TOKEN_LIMIT},
            journal,
            phase="reader",
            operation="reader",
            provider="target_api",
            model="fake",
            kind="llm",
            object_id="q",
        )
    assert journal.summary()["attempts"] == 0
