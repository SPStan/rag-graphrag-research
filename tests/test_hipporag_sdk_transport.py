"""Opt-in tests of pinned HippoRAG using real OpenAI with mock HTTP only."""

from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest

from scripts import run_hipporag as runner
from scripts.token_accounting import Journal, read_records

pytestmark = pytest.mark.skipif(
    os.environ.get("HIPPORAG_SDK_SOURCE") is None,
    reason="requires isolated pinned HippoRAG SDK environment",
)


@pytest.fixture
def sdk(tmp_path):
    import httpx
    from hipporag.llm.openai_gpt import CacheOpenAI
    from hipporag.utils.config_utils import BaseConfig

    source = Path(os.environ["HIPPORAG_SDK_SOURCE"]).resolve()
    revision = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={source.as_posix()}",
            "-C",
            str(source),
            "rev-parse",
            "HEAD",
        ],
        text=True,
    ).strip()
    assert revision == runner.PROMPT_SOURCE_COMMIT
    assert metadata.version("openai") == "3.26.1"
    assert metadata.version("httpx") == "0.28.1"
    installed = Path(__import__(CacheOpenAI.__module__, fromlist=["__file__"]).__file__)
    assert installed.read_bytes().replace(b"\r\n", b"\n") == (
        source / "src/hipporag/llm/openai_gpt.py"
    ).read_bytes().replace(b"\r\n", b"\n")
    config = BaseConfig(
        llm_name="synthetic-sdk-test",
        llm_base_url="http://localhost:1/v1",
        save_dir=str(tmp_path),
        max_retry_attempts=0,
        dataset="hotpotqa",
        max_new_tokens=32,
    )
    llm = CacheOpenAI.from_experiment_config(config)
    runner.require_no_sdk_retries(llm)
    log = Journal(
        tmp_path / "tokens.jsonl",
        run_id="sdk-test",
        method="hipporag2",
        dataset="synthetic",
    )
    local = threading.local()
    requests = []

    def install(handler):
        def transport(request):
            assert request.url.host == "localhost"
            requests.append(request)
            return handler(request)

        llm.openai_client._client.close()
        llm.openai_client._client = httpx.Client(
            transport=httpx.MockTransport(transport)
        )

    yield llm, log, local, requests, install
    llm.close()


def response(request, content="Answer: synthetic", usage=True):
    import httpx

    payload = {
        "id": "chatcmpl-synthetic",
        "object": "chat.completion",
        "created": 0,
        "model": "synthetic-sdk-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    if usage:
        payload["usage"] = {
            "prompt_tokens": 9,
            "completion_tokens": 3,
            "total_tokens": 12,
        }
    return httpx.Response(200, json=payload, request=request)


@pytest.mark.parametrize("failure", [408, 409, 429, 500, "connect", "timeout"])
def test_sdk_zero_retries_counts_one_physical_attempt(sdk, failure):
    import httpx
    import openai

    llm, log, local, calls, install = sdk

    def fail(request):
        if failure == "connect":
            raise httpx.ConnectError("synthetic", request=request)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic", request=request)
        return httpx.Response(
            failure, json={"error": {"message": "synthetic"}}, request=request
        )

    install(fail)
    local.stage, local.passage_id = "openie_ner", "p-failed"
    runner.install_chat_accounting(llm, log, local, "synthetic-sdk-test")
    with pytest.raises(openai.APIError):
        llm.infer(messages=[{"role": "user", "content": "synthetic failure"}])
    assert len(calls) == 1
    records = read_records(log.path)
    assert [r["event"] for r in records] == ["started", "finished"]
    assert all(r["object_id"] == "p-failed" and r["phase"] == "index" for r in records)
    assert log.summary()["attempts"] == 1
    assert not log.summary()["complete"]


def test_sdk_cache_and_missing_usage(sdk):
    llm, log, local, calls, install = sdk
    install(response)
    local.stage, local.question_id = "qa", "q-cache"
    runner.install_chat_accounting(llm, log, local, "synthetic-sdk-test")
    messages = [{"role": "user", "content": "synthetic cache"}]
    assert llm.infer(messages=messages)[2] is False
    assert llm.infer(messages=messages)[2] is True
    assert len(calls) == 1
    assert log.summary()["attempts"] == 1
    assert log.summary()["known_subtotal"]["llm_input_tokens"] == 9
    install(lambda request: response(request, usage=False))
    with pytest.raises(ValueError, match="usage"):
        llm.infer(messages=[{"role": "user", "content": "synthetic unknown usage"}])
    assert len(calls) == 2
    assert log.summary()["attempts"] == 2
    assert not log.summary()["complete"]
    assert log.summary()["known_subtotal"]["llm_input_tokens"] == 9


def test_real_openie_workers_preserve_passage_and_phase(sdk):
    from hipporag.information_extraction.openie_openai import OpenIE

    llm, log, local, calls, install = sdk
    barrier = threading.Barrier(2)

    def serve(request):
        barrier.wait(timeout=20)
        payload = json.loads(request.content)
        is_ner = payload.get("max_tokens") == 512
        content = (
            '{"named_entities": ["Alpha", "Beta"]}'
            if is_ner
            else '{"triples": [["Alpha", "relates", "Beta"]]}'
        )
        return response(request, content)

    install(serve)
    openie = OpenIE(llm, max_workers=2)
    rag = SimpleNamespace(
        qa_llm=llm,
        global_config=llm.global_config,
        openie=openie,
        embedding_model=SimpleNamespace(
            encode=lambda _: pytest.fail("embedding not requested")
        ),
        index=lambda _: None,
        retrieve=lambda _: llm.infer(
            messages=[{"role": "user", "content": "synthetic retrieval"}]
        ),
        qa=lambda _: llm.infer(
            messages=[{"role": "user", "content": "synthetic reader"}]
        ),
    )
    corpus = [
        {"id": f"p{i}", "title": f"Title {i}", "text": f"Synthetic passage {i}"}
        for i in range(2)
    ]
    runner.instrument_models(
        rag,
        corpus,
        {},
        [],
        threading.Lock(),
        run_id=log.run_id,
        model_digest="synthetic",
        local_context=local,
        journal=log,
    )
    runner.install_chat_accounting(llm, log, local, "synthetic-sdk-test")
    ner, triples = openie.batch_openie(
        {p["id"]: {"content": p["title"] + "\n" + p["text"]} for p in corpus}
    )
    assert all(not r.metadata.get("error") for r in [*ner.values(), *triples.values()])
    assert len(calls) == 4
    started = [r for r in read_records(log.path) if r["event"] == "started"]
    assert {(r["operation"], r["object_id"], r["phase"]) for r in started} == {
        (stage, pid, "index")
        for stage in ("openie_ner", "openie_triples")
        for pid in ("p0", "p1")
    }
    assert getattr(local, "passage_id", None) is None
    install(response)
    local.question_id = "q-main"
    rag.retrieve([])
    rag.qa([])
    started = [r for r in read_records(log.path) if r["event"] == "started"]
    assert [(r["operation"], r["phase"], r["object_id"]) for r in started[-2:]] == [
        ("graph_retrieval", "retrieval", "q-main"),
        ("qa", "reader", "q-main"),
    ]
    assert len(calls) == log.summary()["attempts"] == 6
    assert log.summary()["complete"]
    assert log.summary()["known_subtotal"]["llm_input_tokens"] == 54


def test_http_positive_control_detects_enabled_sdk_retry(sdk):
    import httpx
    import openai

    llm, _log, _local, calls, install = sdk
    install(
        lambda request: httpx.Response(
            429,
            json={"error": {"message": "synthetic"}},
            headers={"retry-after-ms": "1"},
            request=request,
        )
    )
    enabled = llm.openai_client.with_options(max_retries=1)
    with pytest.raises(RuntimeError, match="retries"):
        runner.require_no_sdk_retries(
            SimpleNamespace(max_retries=1, openai_client=enabled)
        )
    with pytest.raises(openai.RateLimitError):
        enabled.chat.completions.create(
            model="synthetic-sdk-test",
            messages=[{"role": "user", "content": "synthetic positive control"}],
        )
    assert len(calls) == 2
