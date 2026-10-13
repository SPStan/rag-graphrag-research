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
        manifest["failed_reader_response"]["answer_extraction_status"]
        == "missing_answer_marker"
    )
    assert (path / manifest["failed_reader_response"]["file"]).is_file()
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


@pytest.mark.parametrize(
    "payload, reason",
    [
        (
            {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
            "reader_response_structure_invalid",
        ),
        (
            {
                "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
            "reader_response_structure_invalid",
        ),
        (
            {
                "choices": [
                    {"message": {"content": "Answer: yes"}, "finish_reason": "stop"}
                ]
            },
            "missing_usage_stop",
        ),
        (
            {
                "choices": [
                    {"message": {"content": "Answer: yes"}, "finish_reason": "length"}
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
            "reader_format_or_finish_reason_invalid",
        ),
    ],
)
def test_all_invalid_responses_saved_before_validation(
    setup, monkeypatch, payload, reason
):
    plan, queries, corpus, labels, config, local, remote, path, _ = setup
    calls = []

    def send(*a, **k):
        calls.append(1)
        return response(payload)

    monkeypatch.setattr(remote, "post", send)
    manifest_path, manifest = target.execute(
        plan, queries, corpus, labels, config, local, remote, path
    )
    assert manifest["status"] == "failed"
    assert manifest["errors"][0]["reason"] == reason
    assert len(calls) == 1
    assert manifest["observed_question_ids"] == []
    attempt = manifest["reader_attempts"][0]
    assert json.loads((path / attempt["response_file"]).read_text()) == payload
    assert json.loads((path / attempt["request_file"]).read_text())["payload"][
        "messages"
    ]
    assert attempt["response_sha256"]
    assert attempt["diagnostics"]["content_type"]
    summary = verified_reference(manifest, manifest_path)["summary"]
    assert summary["attempts"] == 3
    assert summary["complete"] == ("usage" in payload)


def test_target_parser_distinguishes_prose_heading_from_answer_line():
    raw = "Thought:\n4. **Synthesize the answer:** Use the passage.\n\nAnswer: example population\n"
    assert target.dense.extract_reader_answer(raw)[1] == "ambiguous_answer_marker"
    assert target.dense.extract_target_reader_answer(raw) == (
        "example population",
        "ok",
    )
    assert target.dense.extract_target_reader_answer("Reasoning. Answer: inline") == (
        "",
        "missing_answer_marker",
    )
    assert (
        target.dense.extract_target_reader_answer("Answer: first\nAnswer: second")[1]
        == "ambiguous_answer_marker"
    )
    assert (
        target.dense.extract_target_reader_answer("Answer: \nNo final answer")[1]
        == "missing_answer_marker"
    )


def test_cli_refuses_reusing_one_diagnostic_prior_manifest(setup, monkeypatch):
    import itertools
    import sys

    base, queries, corpus, labels, config, local, remote, root, calls = setup
    output = root / "results" / "raw"
    first = dict(
        base,
        kind="dense_target_reader_diagnostic",
        parent_plan_sha256=target.digest(base),
        question_ids=["q0"],
        token_limit_per_dataset=20000,
    )
    prior_path, prior = target.execute(
        first, queries[:1], corpus, labels[:1], config, local, remote, output
    )
    monkeypatch.setattr(target, "ROOT", root)
    monkeypatch.setattr(
        target,
        "prepare",
        lambda dataset, _: (dict(base, dataset=dataset), queries, corpus, labels),
    )
    monkeypatch.setattr(target.api, "settings", lambda _: config)
    sessions = itertools.cycle([local, remote])
    monkeypatch.setattr(target.requests, "Session", lambda: next(sessions))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dense-target",
            "--dataset",
            "musique",
            "--diagnostic-question",
            "q0",
            "--diagnostic-prior-run",
            str(prior_path),
            "--execute",
        ],
    )
    target.main()
    assert len(calls) == 2
    children = [
        json.loads(p.read_text())
        for p in output.glob("*.manifest.json")
        if json.loads(p.read_text()).get("plan", {}).get("diagnostic_prior_run_id")
        == prior["run_id"]
    ]
    assert len(children) == 1
    assert children[0]["plan"]["token_limit_per_dataset"] == (
        20000 - sum(prior["token_accounting"]["summary"]["known_subtotal"].values())
    )
    # Delete only the synthetic claim to prove historical manifests alone stop reuse.
    target.diagnostic_claim_path(prior_path, prior["run_id"]).unlink()
    with pytest.raises(SystemExit, match="already consumed"):
        target.main()
    assert len(calls) == 2
    assert len(list(output.glob("*.manifest.json"))) == 2


def synthetic_diagnostic(tmp_path, run_id, plan, tokens=None):
    journal = Journal(
        tmp_path / f"{run_id}.tokens.jsonl",
        run_id=run_id,
        method="dense",
        dataset="musique",
    )
    start = journal.start(
        phase="reader",
        operation="reader",
        provider="target_api",
        model="fake",
        kind="llm",
    )
    journal.finish(
        start,
        status="success",
        usage={"llm_input_tokens": tokens, "llm_output_tokens": 0},
    )
    path = tmp_path / f"{run_id}.manifest.json"
    manifest = {
        "run_id": run_id,
        "plan": plan,
        "expected_question_ids": plan["question_ids"],
        "token_accounting": journal.reference(),
    }
    target.dense.write_json_atomic(path, manifest)
    return path


@pytest.mark.parametrize("grandchild", [False, True])
def test_diagnostic_budget_includes_all_children_and_descendants(tmp_path, grandchild):
    plan = {
        "kind": "dense_target_reader_diagnostic",
        "parent_plan_sha256": "pinned",
        "question_ids": ["q0"],
    }
    prior = synthetic_diagnostic(tmp_path, "prior", plan, 1000)
    synthetic_diagnostic(
        tmp_path, "child1", dict(plan, diagnostic_prior_run_id="prior"), 9500
    )
    synthetic_diagnostic(
        tmp_path,
        "child2",
        dict(plan, diagnostic_prior_run_id="child1" if grandchild else "prior"),
        9500,
    )
    with pytest.raises(SystemExit, match="budget exhausted"):
        target.diagnostic_budget(prior, plan, tmp_path)


def test_diagnostic_unknown_child_cost_refuses_continuation(tmp_path):
    plan = {
        "kind": "dense_target_reader_diagnostic",
        "parent_plan_sha256": "pinned",
        "question_ids": ["q0"],
    }
    prior = synthetic_diagnostic(tmp_path, "prior", plan, 1000)
    synthetic_diagnostic(tmp_path, "child", dict(plan, diagnostic_prior_run_id="prior"))
    with pytest.raises(SystemExit, match="incomplete or unverified cost"):
        target.diagnostic_budget(prior, plan, tmp_path)


def test_diagnostic_reservation_survives_crash_before_manifest(setup, monkeypatch):
    base, queries, corpus, labels, config, local, remote, root, calls = setup
    plan = dict(
        base,
        kind="dense_target_reader_diagnostic",
        parent_plan_sha256="pinned",
        question_ids=["q0"],
    )
    prior = synthetic_diagnostic(root, "prior", plan, 1000)
    continuation = dict(
        plan, diagnostic_prior_run_id="prior", token_limit_per_dataset=19000
    )
    monkeypatch.setattr(
        target.dense,
        "git_snapshot",
        lambda: (_ for _ in ()).throw(RuntimeError("synthetic crash")),
    )
    with pytest.raises(RuntimeError, match="synthetic crash"):
        target.execute(
            continuation,
            queries[:1],
            corpus,
            labels[:1],
            config,
            local,
            remote,
            root,
            diagnostic_prior_path=prior,
        )
    with pytest.raises(SystemExit, match="already consumed"):
        target.execute(
            continuation,
            queries[:1],
            corpus,
            labels[:1],
            config,
            local,
            remote,
            root,
            diagnostic_prior_path=prior,
        )
    assert not calls
    assert len(list(root.glob("*.manifest.json"))) == 1


def test_parallel_continuations_allow_only_one_transport_attempt(setup, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    base, queries, corpus, labels, config, local, remote, root, calls = setup
    plan = dict(
        base,
        kind="dense_target_reader_diagnostic",
        parent_plan_sha256="pinned",
        question_ids=["q0"],
    )
    prior = synthetic_diagnostic(root, "prior", plan, 1000)
    continuation = dict(
        plan, diagnostic_prior_run_id="prior", token_limit_per_dataset=19000
    )
    original = target.diagnostic_budget
    barrier = threading.Barrier(2)

    def both_preflights_pass(*args):
        result = original(*args)
        barrier.wait(timeout=10)
        return result

    monkeypatch.setattr(target, "diagnostic_budget", both_preflights_pass)

    def launch(index):
        try:
            return target.execute(
                continuation,
                queries[:1],
                corpus,
                labels[:1],
                config,
                local,
                remote,
                root / f"worktree-{index}" / "results" / "raw",
                diagnostic_prior_path=prior,
            )[1]["status"]
        except SystemExit as exc:
            assert "already consumed" in str(exc)
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(launch, range(2)))
    assert sorted(outcomes) == ["blocked", "completed"]
    assert len(calls) == 1


def test_one_prior_blocks_continuation_in_another_output_directory(setup):
    base, queries, corpus, labels, config, local, remote, root, calls = setup
    prior_dir = root / "A"
    prior_dir.mkdir()
    plan = dict(
        base,
        kind="dense_target_reader_diagnostic",
        parent_plan_sha256="pinned",
        question_ids=["q0"],
    )
    prior = synthetic_diagnostic(prior_dir, "prior", plan, 1000)
    continuation = dict(
        plan, diagnostic_prior_run_id="prior", token_limit_per_dataset=19000
    )
    output_b, output_c = root / "B" / "results" / "raw", root / "C" / "results" / "raw"
    _, child = target.execute(
        continuation,
        queries[:1],
        corpus,
        labels[:1],
        config,
        local,
        remote,
        output_b,
        diagnostic_prior_path=prior,
    )
    assert child["status"] == "completed"
    claim = target.diagnostic_claim_path(prior, "prior")
    assert claim.parent == prior_dir.resolve()
    assert json.loads(claim.read_text())["child_run_id"] == child["run_id"]
    assert not list(output_b.glob(".diagnostic-*"))
    with pytest.raises(SystemExit, match="already consumed"):
        target.execute(
            continuation,
            queries[:1],
            corpus,
            labels[:1],
            config,
            local,
            remote,
            output_c,
            diagnostic_prior_path=root / "C" / ".." / "A" / prior.name,
        )
    assert len(calls) == 1
    assert len(list(output_b.glob("*.manifest.json"))) == 1
    assert not list(output_c.glob("*.manifest.json"))
