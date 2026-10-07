"""Offline contract checks for physical request accounting."""

from types import SimpleNamespace
import sys
import threading

import pytest
import requests

from scripts import check_target_api, run_dense, run_hipporag
from scripts import track_dense
from scripts.token_accounting import (
    Journal,
    recorded_call,
    read_records,
    summarize,
    verified_reference,
)


def journal(tmp_path):
    return Journal(
        tmp_path / "run.tokens.jsonl",
        run_id="run-1",
        method="dense",
        dataset="synthetic",
    )


def test_phases_partial_replay_and_conflict(tmp_path):
    log = journal(tmp_path)
    index = log.start(
        phase="index",
        operation="embedding",
        provider="local_ollama",
        model="bge",
        kind="embedding",
    )
    log.finish(index, status="success", usage={"embedding_input_tokens": 19})
    query = log.start(
        phase="retrieval",
        operation="embedding",
        provider="local_ollama",
        model="bge",
        kind="embedding",
    )
    log.finish(query, status="success", usage={"embedding_input_tokens": 7})
    reader = log.start(
        phase="reader",
        operation="reader",
        provider="target_api",
        model="qwen",
        kind="llm",
    )
    log.finish(
        reader, status="success", usage={"llm_input_tokens": 23, "llm_output_tokens": 4}
    )
    first = log.summary()
    assert first["known_subtotal"] == {
        "llm_input_tokens": 23,
        "llm_output_tokens": 4,
        "embedding_input_tokens": 26,
    }
    assert first["complete"]
    failed = log.start(
        phase="reader",
        operation="reader",
        provider="target_api",
        model="qwen",
        kind="llm",
        operation_id=reader["operation_id"],
        attempt_no=2,
    )
    log.finish(failed, status="unknown", error_code="ReadTimeout")
    rows = read_records(log.path)
    partial = summarize(rows + [rows[-1]])
    assert partial["known_subtotal"] == first["known_subtotal"]
    assert not partial["complete"]
    assert partial["attempts"] == 4
    with pytest.raises(ValueError, match="conflicting"):
        summarize(rows + [{**rows[-1], "llm_input_tokens": 5}])


def test_started_survives_timeout_and_write_failure_blocks_transport(
    tmp_path, monkeypatch
):
    log = journal(tmp_path)
    sent = []

    def timeout():
        sent.append(1)
        raise requests.ReadTimeout()

    with pytest.raises(requests.ReadTimeout):
        recorded_call(
            log,
            timeout,
            phase="reader",
            operation="reader",
            provider="target_api",
            model="qwen",
            kind="llm",
        )
    assert len(sent) == 1
    assert read_records(log.path)[-1]["llm_input_tokens"] is None

    def cannot_write(_row):
        raise OSError("disk unavailable")

    monkeypatch.setattr(log, "_append", cannot_write)
    with pytest.raises(OSError):
        recorded_call(
            log,
            lambda: sent.append(2),
            phase="reader",
            operation="reader",
            provider="target_api",
            model="qwen",
            kind="llm",
        )
    assert sent == [1]


def test_dense_transport_records_before_vector_validation(tmp_path):
    log = journal(tmp_path)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"prompt_eval_count": 11, "embeddings": []}

    session = SimpleNamespace(post=lambda *args, **kwargs: Response())
    payload = run_dense.post_json(
        session,
        "/api/embed",
        {},
        accounting=(
            log,
            {
                "phase": "retrieval",
                "operation": "query_embedding",
                "provider": "local_ollama",
                "model": "bge",
                "kind": "embedding",
            },
        ),
    )
    assert payload["embeddings"] == []
    assert log.summary()["known_subtotal"]["embedding_input_tokens"] == 11


def test_hipporag_sdk_cache_boundary_and_thread_context(tmp_path):
    log = Journal(
        tmp_path / "hippo.jsonl",
        run_id="hippo",
        method="hipporag2",
        dataset="synthetic",
    )
    context = threading.local()
    context.stage = "openie_ner"
    context.passage_id = "p1"
    calls = []

    def create(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=9, completion_tokens=3),
            id="response-1",
            _request_id="request-1",
        )

    completions = SimpleNamespace(create=create)
    llm = SimpleNamespace(
        openai_client=SimpleNamespace(chat=SimpleNamespace(completions=completions))
    )
    run_hipporag.install_chat_accounting(llm, log, context, "qwen")
    completions.create()
    assert len(calls) == 1
    assert log.summary()["known_subtotal"]["llm_input_tokens"] == 9
    assert read_records(log.path)[-1]["object_id"] == "p1"


def test_target_api_fake_response_usage_and_secret_absence(tmp_path):
    log = Journal(
        tmp_path / "api.jsonl",
        run_id="api",
        method="target_api_smoke",
        dataset="synthetic",
    )
    config = {
        "model": "qwen",
        "base_url": "https://example.test/v1",
        "key": "private-token",
    }

    class Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "id": "r1",
                "usage": {"prompt_tokens": 23, "completion_tokens": 4},
                "choices": [{"message": {"content": "four"}, "finish_reason": "stop"}],
            }

    session = SimpleNamespace(post=lambda *args, **kwargs: Response())
    record = check_target_api.remote_generation(session, config, {}, journal=log)
    assert record["status"] == "verified"
    assert log.summary()["known_subtotal"]["llm_output_tokens"] == 4
    assert "private-token" not in log.path.read_text(encoding="utf-8")


def test_manifest_reference_verifies_run_and_keeps_legacy_unknown(tmp_path):
    log = journal(tmp_path)
    started = log.start(
        phase="index",
        operation="embedding",
        provider="local_ollama",
        model="bge",
        kind="embedding",
    )
    log.finish(started, status="success", usage={"embedding_input_tokens": 3})
    manifest_path = tmp_path / "run.manifest.json"
    assert (
        verified_reference({"run_id": "old"}, manifest_path)["status"]
        == "legacy_unknown"
    )
    manifest = {"run_id": "run-1", "token_accounting": log.reference()}
    assert verified_reference(manifest, manifest_path)["summary"]["complete"]
    manifest["run_id"] = "other"
    with pytest.raises(ValueError, match="run_mismatch"):
        verified_reference(manifest, manifest_path)


def test_cache_hit_has_no_new_physical_cost(tmp_path):
    log = journal(tmp_path)
    log.cache_hit(
        phase="index",
        operation="index_embedding",
        provider="local_ollama",
        model="bge",
        kind="embedding",
        object_id="cached_index",
    )
    summary = log.summary()
    assert summary["attempts"] == 0
    assert summary["known_subtotal"]["embedding_input_tokens"] == 0
    assert summary["phases"][0]["cache_hits"] == 1
    assert not summary["historical_cache_cost_complete"]


def test_explicit_retry_and_unfinished_attempt(tmp_path):
    log = journal(tmp_path)
    first = log.start(
        phase="reader",
        operation="reader",
        provider="target_api",
        model="qwen",
        kind="llm",
    )
    log.finish(first, status="error", error_code="HTTPError")
    second = log.start(
        phase="reader",
        operation="reader",
        provider="target_api",
        model="qwen",
        kind="llm",
        operation_id=first["operation_id"],
        attempt_no=2,
    )
    log.finish(
        second, status="success", usage={"llm_input_tokens": 5, "llm_output_tokens": 2}
    )
    third = log.start(
        phase="reader",
        operation="reader",
        provider="target_api",
        model="qwen",
        kind="llm",
    )
    assert len({first["attempt_id"], second["attempt_id"], third["attempt_id"]}) == 3
    summary = log.summary()
    assert summary["attempts"] == 3
    assert summary["phases"][0]["unfinished"] == 1
    assert summary["known_subtotal"]["llm_input_tokens"] == 5
    assert not summary["complete"]


def test_langfuse_root_exports_verified_incomplete_summary(tmp_path, monkeypatch):
    log = journal(tmp_path)
    known = log.start(
        phase="reader",
        operation="reader",
        provider="target_api",
        model="qwen",
        kind="llm",
    )
    log.finish(
        known, status="success", usage={"llm_input_tokens": 23, "llm_output_tokens": 4}
    )
    unknown = log.start(
        phase="reader",
        operation="reader",
        provider="target_api",
        model="qwen",
        kind="llm",
    )
    log.finish(unknown, status="unknown", error_code="ReadTimeout")
    manifest = {"run_id": "run-1", "token_accounting": log.reference()}
    accounting = verified_reference(manifest, tmp_path / "run.manifest.json")
    assert accounting["status"] == "verified"

    class Observation:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def update(self, **_kwargs):
            pass

    class FakeClient:
        def __init__(self, **_kwargs):
            self.observations = []

        def auth_check(self):
            return True

        def start_as_current_observation(self, **kwargs):
            self.observations.append(kwargs)
            return Observation(kwargs)

        def get_current_trace_id(self):
            return "trace-1"

        def flush(self):
            pass

        def get_trace_url(self, **_kwargs):
            return "http://localhost/trace-1"

        def shutdown(self):
            pass

    client = FakeClient()
    monkeypatch.setitem(
        sys.modules, "langfuse", SimpleNamespace(Langfuse=lambda **_kwargs: client)
    )
    monkeypatch.setattr(
        track_dense,
        "dotenv_values",
        lambda _path: {
            "LANGFUSE_BASE_URL": "http://localhost:3000",
            "LANGFUSE_PUBLIC_KEY": "fake",
            "LANGFUSE_SECRET_KEY": "fake",
        },
    )
    monkeypatch.setattr(
        track_dense,
        "get_all_langfuse_observations",
        lambda *_args: [
            SimpleNamespace(name=name)
            for name in (
                "dense-rag-run",
                "question",
                "query-embedding",
                "retrieval",
                "generation",
            )
        ],
    )
    monkeypatch.setattr(track_dense, "verify_langfuse_trace", lambda *_args: {})
    row = {
        "question_id": "q1",
        "question": "question",
        "top_k": 5,
        "embedding_model": {"name": "bge"},
        "generation_model": {"name": "qwen"},
        "reader_prompt_version": "v1",
        "prompt_tokens": 23,
        "completion_tokens": 4,
    }
    payload = {
        "run_id": "run-1",
        "dataset": "synthetic",
        "rows": [row],
        "questions": [{"row": row, "retrieved_passages": []}],
        "manifest": manifest,
        "token_accounting": accounting,
        "metrics": {"em": 0, "token_f1": 0, "recall_at_k": 0},
    }
    track_dense.export_langfuse(payload, base_dir=tmp_path)
    root = client.observations[0]["metadata"]
    assert root["token_accounting_status"] == "verified"
    assert root["token_accounting_summary"]["known_subtotal"]["llm_input_tokens"] == 23
    assert root["token_accounting_summary"]["attempts"] == 2
    assert (
        root["token_accounting_summary"]["phases"][0]["unknown_fields"][
            "llm_input_tokens"
        ]
        == 1
    )
    assert root["token_accounting_complete"] is False
    assert root["historical_cache_cost_complete"] is True
    generation = next(
        item for item in client.observations if item["name"] == "generation"
    )
    assert generation["usage_details"] == {"input": 23, "output": 4}


def test_hipporag_runner_rejects_enabled_sdk_retries():
    llm = SimpleNamespace(max_retries=0, openai_client=SimpleNamespace(max_retries=0))
    run_hipporag.require_no_sdk_retries(llm)
    llm.openai_client.max_retries = 2
    with pytest.raises(RuntimeError, match="retries are not disabled"):
        run_hipporag.require_no_sdk_retries(llm)
