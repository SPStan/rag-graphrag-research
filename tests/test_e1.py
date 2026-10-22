"""Offline spending guards and actual pinned SDK index/save/reload checks."""

import os
import json
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pytest
import requests

from scripts import run_e1 as e1
from scripts import e1_indexers
from scripts import run_dense as dense
from scripts.token_accounting import Journal


def transport(tmp_path, body=None, limit=100000):
    journal = Journal(
        tmp_path / "usage.jsonl", run_id="run", method="dense", dataset="musique"
    )
    plan = {
        "model": "qwen",
        "embedding_model": "bge-m3:latest",
        "endpoint": "https://example.invalid/v1",
    }
    session = requests.Session()
    response = Mock(status_code=200)
    response.json.return_value = body or {
        "embeddings": [[1.0] * 1024],
        "prompt_eval_count": 7,
    }
    session.post = Mock(return_value=response)
    runner = e1.Transport(
        plan,
        {"method": "dense", "dataset": "musique", "token_limit": limit},
        {"LITELLM_API_KEY": "test-secret"},
        tmp_path,
        journal,
        session,
    )
    return runner, session


def test_checkpoint_replay_does_not_send_twice(tmp_path):
    runner, session = transport(tmp_path)
    a = runner.embed(["text"])
    b = runner.embed(["text"])
    assert np.array_equal(a, b)
    assert session.post.call_count == 1
    assert runner.journal.summary()["attempts"] == 1
    assert runner.journal.summary()["known_subtotal"]["embedding_input_tokens"] == 7
    assert session.post.call_args.kwargs["allow_redirects"] is False
    assert session.post.call_args.kwargs["timeout"] == (5, 300)


def test_budget_rejected_before_post(tmp_path):
    runner, session = transport(tmp_path, limit=100)
    with pytest.raises(ValueError, match="budget_reservation"):
        runner.embed(["text"])
    session.post.assert_not_called()
    assert runner.journal.summary()["attempts"] == 0


@pytest.mark.parametrize(
    "body",
    [
        {"embeddings": [[1.0] * 1024]},
        {"embeddings": [[1.0] * 3], "prompt_eval_count": 7},
    ],
)
def test_unknown_or_invalid_response_blocks_replay(tmp_path, body):
    runner, session = transport(tmp_path, body)
    with pytest.raises(ValueError):
        runner.embed(["text"])
    with pytest.raises(ValueError):
        runner.embed(["text"])
    assert session.post.call_count == 1


def test_current_unknown_uses_saved_reserve_not_zero(tmp_path):
    runner, session = transport(tmp_path)
    session.post.side_effect = requests.ConnectionError("failed")
    with pytest.raises(requests.ConnectionError):
        runner.embed(["text"])
    checkpoint = next((tmp_path / "requests").glob("*.json"))
    reserve = dense.read_json(checkpoint)["reserved_tokens"]
    assert e1.current_unknown_reservation(tmp_path) == reserve
    assert reserve > 0
    dense.write_json_atomic(checkpoint, {"status": "started"})
    assert e1.current_unknown_reservation(tmp_path) is None


def test_changed_checkpoint_is_rejected(tmp_path):
    runner, session = transport(tmp_path)
    runner.embed(["text"])
    path = next((tmp_path / "requests").glob("*.response.json"))
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="changed_checkpoint"):
        runner.embed(["text"])
    assert session.post.call_count == 1


def test_checkpoint_without_physical_attempt_is_rejected(tmp_path):
    runner, session = transport(tmp_path)
    runner.embed(["text"])
    runner.journal.path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="changed_checkpoint"):
        runner.embed(["text"])
    assert session.post.call_count == 1


def test_timeout_remains_unknown_and_cannot_retry(tmp_path):
    runner, session = transport(tmp_path)
    session.post.side_effect = requests.ReadTimeout()
    with pytest.raises(requests.ReadTimeout):
        runner.embed(["text"])
    assert runner.journal.summary()["complete"] is False
    with pytest.raises(ValueError, match="cannot_continue"):
        runner.embed(["another text"])
    assert session.post.call_count == 1


def test_canonical_lock_rejects_concurrent_run(tmp_path):
    with e1.exclusive(tmp_path):
        with pytest.raises(FileExistsError):
            with e1.exclusive(tmp_path):
                pass
    assert not (tmp_path / "running.lock").exists()


def test_dense_reload_covers_ids(tmp_path):
    runner, _ = transport(tmp_path)
    result = e1.dense_index([{"id": "a", "title": "T", "text": "x"}], runner, tmp_path)
    assert result == {"passages": 1, "dimension": 1024, "reload_model_calls": 0}


def test_raptor_explicit_physical_batch_preserves_full_input(tmp_path):
    runner, session = transport(tmp_path)
    runner.row.update(
        method="raptor", embedding_options=dict(e1.RAPTOR_EMBEDDING_OPTIONS)
    )
    text = "full summary\n" * 100
    runner.embed([text])
    payload = session.post.call_args.kwargs["json"]
    assert payload["input"] == [text]
    assert payload["truncate"] is False
    assert payload["options"] == {"num_ctx": 4096, "num_batch": 4096}


@pytest.mark.parametrize(
    "method,options",
    [
        ("dense", {"num_ctx": 4096, "num_batch": 4096}),
        ("hipporag2", {"num_ctx": 4096, "num_batch": 4096}),
        ("raptor", {"num_ctx": 4096, "num_batch": 2048}),
    ],
)
def test_embedding_batch_policy_rejects_unapproved_configuration(
    tmp_path, method, options
):
    runner, session = transport(tmp_path)
    runner.row.update(method=method, embedding_options=options)
    with pytest.raises(ValueError, match="unsupported_RAPTOR"):
        runner.embed(["summary"])
    session.post.assert_not_called()


def test_batch_fix_replays_verified_old_payload_without_paying_again(tmp_path):
    runner, session = transport(tmp_path)
    runner.row.update(
        method="raptor", embedding_options=dict(e1.RAPTOR_EMBEDDING_OPTIONS)
    )
    old_payload = {
        "model": runner.plan["embedding_model"],
        "input": ["summary"],
        "truncate": False,
    }
    key = e1.target.digest(
        {"payload": old_payload, "kind": "embedding", "operation": "index_embedding"}
    )
    response = tmp_path / "parent.response.json"
    dense.write_json_atomic(
        response, {"embeddings": [[1.0] * 1024], "prompt_eval_count": 7}
    )
    runner.parent_cache[key] = {
        "path": response,
        "sha256": dense.sha256_file(response),
        "run_id": "parent",
        "producer_complete": False,
        "operation": "index_embedding",
        "kind": "embedding",
        "provider": "local_ollama",
        "model": runner.plan["embedding_model"],
    }
    runner.embed(["summary"])
    session.post.assert_not_called()
    assert runner.journal.summary()["attempts"] == 0
    assert not runner.journal.summary()["historical_cache_cost_complete"]
    response.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="parent_response_changed"):
        runner.embed(["summary"])
    session.post.assert_not_called()


def failed_remote_fixture(tmp_path):
    directory = tmp_path / "indexes/e1/batch/hipporag2/musique"
    directory.mkdir(parents=True)
    original = {
        "kind": "E1_full_corpus_indexing",
        "batch_id": "batch",
        "data_root": str(tmp_path),
        "workspace": str(tmp_path.resolve()),
        "model": "qwen",
        "endpoint": "https://example.invalid/v1",
        "embedding_model": "bge-m3:latest",
        "embedding_digest": "digest",
        "parameters": e1.PARAMETERS,
        "combined_token_limit": 68000000,
        "rows": [
            {
                "method": m,
                "dataset": d,
                "run_id": f"{m}-{d}",
                "code_commit": "old",
                "token_limit": e1.LIMITS[m],
                "output": f"indexes/e1/batch/{m}/{d}",
            }
            for m in e1.METHODS
            for d in e1.DATASETS
        ],
    }
    row = original["rows"][2]
    journal = Journal(
        directory / "usage.jsonl",
        run_id=row["run_id"],
        method="hipporag2",
        dataset="musique",
    )
    session = requests.Session()
    body = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"named_entities":["Alice"]}'},
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    response = Mock(status_code=200)
    response.json.return_value = body
    session.post = Mock(return_value=response)
    runner = e1.Transport(
        original, row, {"LITELLM_API_KEY": "test-secret"}, directory, journal, session
    )
    messages = [{"role": "user", "content": "NER passage"}]
    runner.generate(messages, 1024, "openie_ner")
    session.post.side_effect = requests.ConnectionError("RemoteDisconnected")
    with pytest.raises(requests.ConnectionError):
        runner.generate(
            [{"role": "user", "content": "triples passage"}], 3072, "openie_triples"
        )
    manifest = {
        "status": "failed",
        "run_id": row["run_id"],
        "seconds": 1,
        "token_accounting": journal.reference(),
        "artifacts": {
            p.relative_to(directory).as_posix(): dense.sha256_file(p)
            for p in directory.rglob("*")
            if p.is_file()
        },
    }
    dense.write_json_atomic(directory / "manifest.json", manifest)
    path = tmp_path / "prior-plan.json"
    dense.write_json_atomic(path, original)
    return path, directory, messages


def test_network_resume_cache_budget_unknown_and_single_claim(tmp_path):
    prior, parent, messages = failed_remote_fixture(tmp_path)
    old_manifest_sha = dense.sha256_file(parent / "manifest.json")
    with (
        patch.object(e1, "ROOT", tmp_path),
        patch.object(e1, "code_dirty", return_value=False),
        patch.object(e1, "git", return_value="new"),
    ):
        plan = e1.network_resume_plan(prior)
        row = plan["rows"][2]
        assert row["verified_response_cache_count"] == 1
        assert row["prior_run"]["summary"]["complete"] is False
        assert row["token_limit"] + row["prior_budget_charge"] == 20000000
        assert row["prior_budget_charge"] > 15
        assert dense.sha256_file(parent / "manifest.json") == old_manifest_sha
        with pytest.raises(FileExistsError):
            e1.network_resume_plan(prior)
        directory = tmp_path / row["output"]
        directory.mkdir(parents=True)
        journal = Journal(
            directory / "usage.jsonl",
            run_id=row["run_id"],
            method="hipporag2",
            dataset="musique",
        )
        session = requests.Session()
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [
                {"finish_reason": "stop", "message": {"content": '{"triples":[]}'}}
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 7},
        }
        session.post = Mock(return_value=response)
        runner = e1.Transport(
            plan, row, {"LITELLM_API_KEY": "test-secret"}, directory, journal, session
        )
        _, metadata = runner.generate(messages, 1024, "openie_ner")
        assert metadata["cache_hit"] is True
        session.post.assert_not_called()
        assert journal.summary()["attempts"] == 0
        assert journal.summary()["historical_cache_cost_complete"] is False
        triples = [{"role": "user", "content": "triples passage"}]
        runner.generate(triples, 3072, "openie_triples")
        runner.generate(triples, 3072, "openie_triples")
        assert session.post.call_count == 1
        assert session.post.call_args.kwargs["headers"]["Connection"] == "close"
        assert journal.summary()["known_subtotal"]["llm_input_tokens"] == 20
        assert journal.summary()["attempts"] == 1
        (tmp_path / "results/summary").mkdir(parents=True)
        result = e1.export(plan, prior)
        assert result["physical_known_tokens"] == 42
        assert result["cost_complete"] is False
        assert result["rows"][2]["cumulative_accounting"]["complete"] is False


def test_changed_parent_response_rejected_before_http(tmp_path):
    prior, parent, _ = failed_remote_fixture(tmp_path)
    with (
        patch.object(e1, "ROOT", tmp_path),
        patch.object(e1, "code_dirty", return_value=False),
        patch.object(e1, "git", return_value="new"),
    ):
        plan = e1.network_resume_plan(prior)
        next((parent / "requests").glob("*.response.json")).write_text(
            "{}", encoding="utf-8"
        )
        row = plan["rows"][2]
        directory = tmp_path / row["output"]
        directory.mkdir(parents=True)
        journal = Journal(
            directory / "usage.jsonl",
            run_id=row["run_id"],
            method="hipporag2",
            dataset="musique",
        )
        session = requests.Session()
        session.post = Mock()
        with pytest.raises(ValueError, match="artifact_changed"):
            e1.Transport(plan, row, {}, directory, journal, session)
        session.post.assert_not_called()


def loop_body():
    content = json.dumps(
        {"triples": [["A", "visits", "B"], ["B", "in", "C"], ["A", "uses", "D"]] * 56}
    )[:-2]
    return {
        "choices": [{"finish_reason": "length", "message": {"content": content}}],
        "usage": {"prompt_tokens": 736, "completion_tokens": 3072},
    }


def test_repetition_diagnostic_does_not_accept_partial_text():
    stats = e1.triple_cycle(loop_body()["choices"][0]["message"]["content"])
    assert stats == {"complete_tuples": 168, "unique_tuples": 3, "cycle": True}
    assert not e1.triple_cycle(
        json.dumps({"triples": [[str(i), "in", "B"] for i in range(100)]})
    )["cycle"]


def test_cycle_repair_counts_both_attempts_and_replays_only_valid_result(tmp_path):
    runner, session = transport(tmp_path, loop_body())
    runner.plan["cycle_repair"] = e1.CYCLE_REPAIR
    length = session.post.return_value
    valid = Mock(status_code=200)
    valid.json.return_value = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": '{"triples":[["A","visits","B"]]}'},
            }
        ],
        "usage": {"prompt_tokens": 800, "completion_tokens": 20},
    }
    session.post.side_effect = [length, valid]
    messages = [{"role": "user", "content": "triples"}]
    content, _ = runner.generate(messages, 3072, "openie_triples")
    assert json.loads(content)["triples"] == [["A", "visits", "B"]]
    runner.generate(messages, 3072, "openie_triples")
    assert session.post.call_count == 2
    assert (
        session.post.call_args.kwargs["json"]["messages"][-1]["content"]
        == e1.CYCLE_REPAIR["instruction"]
    )
    summary = runner.journal.summary()
    assert summary["attempts"] == 2
    assert summary["known_subtotal"]["llm_output_tokens"] == 3092
    assert summary["complete"] is True
    assert len(runner.repairs) == 1


def test_second_loop_stops_without_third_attempt(tmp_path):
    runner, session = transport(tmp_path, loop_body())
    runner.plan["cycle_repair"] = e1.CYCLE_REPAIR
    messages = [{"role": "user", "content": "triples"}]
    with pytest.raises(ValueError, match="generation_not_complete"):
        runner.generate(messages, 3072, "openie_triples")
    with pytest.raises(ValueError, match="unresolved_cycle"):
        runner.generate(messages, 3072, "openie_triples")
    assert session.post.call_count == 2
    assert runner.journal.summary()["known_subtotal"]["llm_output_tokens"] == 6144
    diagnostic = e1.failure_diagnostic(tmp_path)
    assert diagnostic["finish_reason"] == "length"
    assert diagnostic["corrective_request"] is True
    assert diagnostic["usage_status"] == "complete"
    assert diagnostic["repetition"]["cycle"] is True
    assert "content" not in diagnostic


def test_legitimate_long_response_does_not_trigger_cycle_repair(tmp_path):
    body = loop_body()
    body["choices"][0]["message"]["content"] = json.dumps(
        {"triples": [[str(i), "in", "B"] for i in range(100)]}
    )[:-2]
    runner, session = transport(tmp_path, body)
    runner.plan["cycle_repair"] = e1.CYCLE_REPAIR
    with pytest.raises(ValueError, match="generation_not_complete"):
        runner.generate([], 3072, "openie_triples")
    assert session.post.call_count == 1
    assert not runner.repairs


@pytest.mark.parametrize(
    "blocked", [None, "lock", "tampered", "started", "incomplete_dense"]
)
def test_independent_raptor_preserves_failed_history_and_never_restarts_hippo(
    tmp_path, blocked
):
    prior, failed, _ = failed_remote_fixture(tmp_path)
    plan = dense.read_json(prior)
    plan["rows"][2]["cycle_repair_request_key"] = "a" * 64
    for row in plan["rows"][:2]:
        directory = tmp_path / row["output"]
        directory.mkdir(parents=True)
        journal = Journal(
            directory / "usage.jsonl",
            run_id=row["run_id"],
            method="dense",
            dataset=row["dataset"],
        )
        attempt = journal.start(
            phase="index",
            operation="index_embedding",
            provider="local_ollama",
            model="bge",
            kind="embedding",
        )
        journal.finish(attempt, status="success", usage={"embedding_input_tokens": 7})
        dense.write_json_atomic(
            directory / "manifest.json",
            {
                "status": "completed",
                "run_id": row["run_id"],
                "seconds": 1,
                "token_accounting": journal.reference(),
                "artifacts": {"usage.jsonl": dense.sha256_file(journal.path)},
            },
        )
    dense.write_json_atomic(prior, plan)
    sha = dense.sha256_file(prior)
    if blocked == "lock":
        (failed / "running.lock").write_text("123", encoding="utf-8")
    elif blocked == "tampered":
        next((failed / "requests").glob("*.response.json")).write_text(
            "{}", encoding="utf-8"
        )
    elif blocked == "started":
        directory = tmp_path / plan["rows"][4]["output"]
        directory.mkdir(parents=True)
        (directory / "usage.jsonl").write_text("", encoding="utf-8")
    elif blocked == "incomplete_dense":
        path = tmp_path / plan["rows"][0]["output"] / "manifest.json"
        manifest = dense.read_json(path)
        manifest["status"] = "failed"
        dense.write_json_atomic(path, manifest)
    with (
        patch.object(e1, "ROOT", tmp_path),
        patch.object(e1, "code_dirty", return_value=False),
        patch.object(e1, "git", return_value="new"),
        patch("requests.Session.request", side_effect=AssertionError("HTTP forbidden")),
    ):
        if blocked:
            with pytest.raises(ValueError):
                e1.independent_raptor_plan(prior)
            assert not prior.with_suffix(".raptor-once.claim.json").exists()
            return
        child = e1.independent_raptor_plan(prior)
        assert child["rows"][:4] == plan["rows"][:4]
        assert child["rows"][4]["code_commit"] == "new"
        assert child["combined_token_limit"] == plan["combined_token_limit"]
        assert dense.sha256_file(prior) == sha
        with pytest.raises(FileExistsError):
            e1.independent_raptor_plan(prior)
        with patch.object(e1, "requests") as http:
            with pytest.raises(ValueError, match="only_raptor"):
                e1.verify_plan(child, child["rows"][2], {})
            http.get.assert_not_called()
        (tmp_path / "results/summary").mkdir(parents=True)
        exported = e1.export(child, prior)
        assert exported["cost_complete"] is False
        assert exported["physical_known_tokens"] == 29
        assert exported["rows"][2]["cycle_repair_request_sha256"] == "a" * 64
        assert "cycle_repair_request_key" not in exported["rows"][2]
        assert child["rows"][2]["cycle_repair_request_key"] == "a" * 64


def test_wrong_probe_is_rejected_before_http(tmp_path):
    runner, session = transport(tmp_path)
    runner.require_repair_key = True
    runner.row["cycle_repair_request_key"] = "another-request"
    with pytest.raises(ValueError, match="probe_request"):
        runner.generate([], 3072, "openie_triples")
    session.post.assert_not_called()


def test_cycle_resume_verifies_inherited_cache_and_all_cost_history(tmp_path):
    prior, _, messages = failed_remote_fixture(tmp_path)
    with (
        patch.object(e1, "ROOT", tmp_path),
        patch.object(e1, "code_dirty", return_value=False),
        patch.object(e1, "git", return_value="new"),
        patch.object(e1, "load_corpus", return_value=([{"id": "source"}], {})),
    ):
        network = e1.network_resume_plan(prior)
        row = network["rows"][2]
        directory = tmp_path / row["output"]
        directory.mkdir(parents=True)
        journal = Journal(
            directory / "usage.jsonl",
            run_id=row["run_id"],
            method="hipporag2",
            dataset="musique",
        )
        runner = e1.Transport(
            network, row, {"LITELLM_API_KEY": "test-secret"}, directory, journal
        )
        response = Mock(status_code=200)
        response.json.return_value = loop_body()
        runner.session.post = Mock(return_value=response)
        runner.generate(messages, 1024, "openie_ner")
        with pytest.raises(ValueError, match="generation_not_complete"):
            runner.generate(
                [{"role": "user", "content": "triple cycle"}], 3072, "openie_triples"
            )
        manifest = {
            "status": "failed",
            "run_id": row["run_id"],
            "seconds": 2,
            "token_accounting": journal.reference(),
            "artifacts": {
                p.relative_to(directory).as_posix(): dense.sha256_file(p)
                for p in directory.rglob("*")
                if p.is_file()
            },
        }
        dense.write_json_atomic(directory / "manifest.json", manifest)
        plan_path = tmp_path / "network.json"
        dense.write_json_atomic(plan_path, network)
        child = e1.cycle_resume_plan(plan_path, "source")
        resumed = child["rows"][2]
        assert len(resumed["history_runs"]) == 2
        assert len(resumed["resume_sources"]) == 2
        assert resumed["token_limit"] == row["token_limit"] - 3808
        assert resumed["prior_budget_charge"] == row["prior_budget_charge"] + 3808
        assert resumed["cycle_diagnostic"]["unique_tuples"] == 3
        with pytest.raises(FileExistsError):
            e1.cycle_resume_plan(plan_path, "source")
        (tmp_path / "results/summary").mkdir(parents=True)
        report = e1.export(child, plan_path)
        assert report["physical_known_tokens"] == 3823
        assert report["cost_complete"] is False
        assert report["budget_charge_upper_bound"] > 3823
        assert report["rows"][2]["cumulative_seconds"] == 3


def test_local_failure_continuation_preserves_unknown_and_shared_claim(tmp_path):
    corpus = [{"id": str(i), "title": "Title", "text": f"text {i}"} for i in range(33)]
    rows = [
        {
            "method": method,
            "dataset": dataset,
            "run_id": f"{method}-{dataset}",
            "code_commit": "old",
            "token_limit": e1.LIMITS[method],
            "output": f"indexes/e1/batch/{method}/{dataset}",
        }
        for method in e1.METHODS
        for dataset in e1.DATASETS
    ]
    original = {
        "batch_id": "batch",
        "rows": rows,
        "data_root": str(tmp_path),
        "embedding_model": "bge-m3:latest",
        "combined_token_limit": 68000000,
        "parameters": {},
    }
    root = tmp_path / rows[1]["output"]
    root.mkdir(parents=True)
    (root / "requests").mkdir()
    journal = Journal(
        root / "usage.jsonl",
        run_id=rows[1]["run_id"],
        method="dense",
        dataset="hotpotqa",
    )
    good = journal.start(
        phase="index",
        operation="index_embedding",
        provider="local_ollama",
        model="bge",
        kind="embedding",
    )
    journal.finish(good, status="success", usage={"embedding_input_tokens": 7})
    bad = journal.start(
        phase="index",
        operation="index_embedding",
        provider="local_ollama",
        model="bge",
        kind="embedding",
    )
    journal.finish(bad, status="error")
    payload = {
        "model": "bge-m3:latest",
        "input": [f"{r['title']}\n{r['text']}" for r in corpus[32:]],
        "truncate": False,
    }
    key = e1.target.digest(
        {"payload": payload, "kind": "embedding", "operation": "index_embedding"}
    )
    dense.write_json_atomic(
        root / "requests" / f"{key}.json", {"status": "started", "request_sha256": key}
    )
    dense.write_json_atomic(
        root / "requests" / f"{key}.response.json",
        {"error": "/tokenize: Only one usage of each socket address"},
    )
    manifest = {
        "status": "failed",
        "run_id": rows[1]["run_id"],
        "seconds": 1,
        "token_accounting": journal.reference(),
        "artifacts": {
            p.relative_to(root).as_posix(): dense.sha256_file(p)
            for p in root.rglob("*")
            if p.is_file()
        },
    }
    dense.write_json_atomic(root / "manifest.json", manifest)
    prior = tmp_path / "prior.json"
    dense.write_json_atomic(prior, original)
    prior_sha = dense.sha256_file(prior)
    with (
        patch.object(e1, "ROOT", tmp_path),
        patch.object(e1, "code_dirty", return_value=False),
        patch.object(e1, "git", return_value="new"),
        patch.object(e1, "load_corpus", return_value=(corpus, {})),
    ):
        child = e1.continuation_plan(prior)
        row = child["rows"][1]
        assert row["prior_run"]["summary"]["complete"] is False
        assert row["prior_budget_charge"] > 7
        assert row["token_limit"] + row["prior_budget_charge"] == 2000000
        assert row["output"].endswith("-continuation1")
        assert dense.sha256_file(prior) == prior_sha
        assert (
            dense.sha256_file(root / "manifest.json")
            == row["prior_run"]["manifest_sha256"]
        )
        with pytest.raises(FileExistsError):
            e1.continuation_plan(prior)
        # Reporting keeps the unknown prior, even before the child sends a request.
        child.update(model="qwen", embedding_digest="digest")
        (tmp_path / "results/summary").mkdir(parents=True)
        result = e1.export(child, prior)
        assert result["physical_known_tokens"] == 7
        assert result["cost_complete"] is False
        assert result["rows"][1]["cumulative_accounting"]["complete"] is False
        child_path = tmp_path / "continued.json"
        dense.write_json_atomic(child_path, child)
        sealed = e1.seal_unstarted_plan(child_path)
        assert sealed["preflight_revisions"]
        current = tmp_path / row["output"]
        current.mkdir(parents=True)
        (current / "usage.jsonl").write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="cannot_change_started"):
            e1.seal_unstarted_plan(child_path)


def test_parent_plan_path_from_json_and_preflight_binding(tmp_path):
    parent = tmp_path / "parent.json"
    parent.write_text("{}", encoding="utf-8")
    rows = [
        {
            "method": m,
            "dataset": d,
            "token_limit": e1.LIMITS[m],
            "code_commit": "new",
            "output": f"indexes/e1/batch/{m}/{d}",
        }
        for m in e1.METHODS
        for d in e1.DATASETS
    ]
    corpus = [{"id": "a", "title": "T", "text": "x"}]
    rows[0].update(corpus={}, corpus_fingerprint=dense.corpus_fingerprint(corpus))
    plan = {
        "kind": "E1_full_corpus_indexing",
        "batch_id": "batch",
        "workspace": str(tmp_path.resolve()),
        "data_root": str(tmp_path),
        "parameters": e1.PARAMETERS,
        "rows": rows,
        "combined_token_limit": 68000000,
        "model": "qwen",
        "endpoint": "https://example.invalid/v1",
        "embedding_model": "bge-m3:latest",
        "embedding_digest": "digest",
        "parent_plan": {"path": str(parent), "sha256": dense.sha256_file(parent)},
    }
    config = {"TARGET_API_MODEL": "qwen", "TARGET_API_BASE_URL": plan["endpoint"]}
    response = Mock()
    response.json.return_value = {
        "models": [{"name": "bge-m3:latest", "digest": "digest"}]
    }
    with (
        patch.object(e1, "ROOT", tmp_path),
        patch.object(e1, "git", return_value="new"),
        patch.object(e1, "code_dirty", return_value=False),
        patch.object(e1, "load_corpus", return_value=(corpus, {})),
        patch.object(e1.requests, "get", return_value=response) as get,
    ):
        assert e1.verify_plan(plan, rows[0], config) == corpus
        get.reset_mock()
        rows[0]["output"] = "another-output"
        with pytest.raises(ValueError, match="plan_or_code"):
            e1.verify_plan(plan, rows[0], config)
        get.assert_not_called()


@pytest.mark.skipif(
    not os.environ.get("E1_HIPPO_SOURCE"),
    reason="isolated pinned HippoRAG SDK required",
)
@pytest.mark.parametrize("mixed", [False, True])
def test_real_hipporag_sdk_index_and_reload_without_http(tmp_path, mixed):
    class Fake:
        plan = {"endpoint": "https://example.invalid", "model": "qwen"}
        row = {
            "dataset": "musique",
            "cycle_probe_source_id": "a",
            **({"resume_kind": "mixed_native"} if mixed else {}),
        }
        journal = Journal(
            tmp_path / "usage.jsonl",
            run_id="fake",
            method="hipporag2",
            dataset="musique",
        )

        def embed(self, texts):
            return dense.normalize_rows(
                np.random.default_rng(42).normal(size=(len(texts), 1024))
            )

        def generate(self, messages, cap, operation, response_format):
            result = (
                '{"named_entities": ["Alice", "Paris"]}'
                if operation == "openie_ner"
                else '{"triples": [["Alice", "visits", "Paris"]]}'
            )
            return result, {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "finish_reason": "stop",
                "extractor_model": "iairlab/gpt-oss-120b" if mixed else "qwen",
                "triples_request_sha256": e1.target.digest(messages),
            }

    corpus = [
        {"id": "a", "title": "Paris", "text": "Alice visits Paris."},
        {"id": "b", "title": "France", "text": "Paris is in France."},
    ]
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        result = e1_indexers.hipporag_index(
            corpus, Fake(), tmp_path, Path(os.environ["E1_HIPPO_SOURCE"])
        )
    assert result["passages"] == 2
    assert result["graph_nodes"] >= 2
    assert result["reload_model_calls"] == 0
    assert dense.read_json(tmp_path / "cycle-probe.json")["status"] == "passed"
    if mixed:
        outcomes = dense.read_json(tmp_path / "openie-validation.json")
        assert all(
            r["extractor_model"] == "iairlab/gpt-oss-120b" and r["raw_triples"] == 1
            for r in outcomes.values()
        )


@pytest.mark.skipif(
    not os.environ.get("E1_RAPTOR_SOURCE"), reason="isolated pinned RAPTOR SDK required"
)
def test_real_raptor_sdk_index_reuses_dense_and_reloads(tmp_path):
    corpus = [
        {"id": str(i), "title": f"Topic {i}", "text": f"Some research detail {i}."}
        for i in range(50)
    ]
    producer = tmp_path / "indexes/e1/fake/dense/musique"
    producer.mkdir(parents=True)
    vectors = np.random.default_rng(42).normal(size=(50, 1024))
    np.savez_compressed(
        producer / "vectors.npz", ids=[r["id"] for r in corpus], vectors=vectors
    )
    journal = Journal(
        producer / "usage.jsonl", run_id="producer", method="dense", dataset="musique"
    )
    event = journal.start(
        phase="index",
        operation="index_embedding",
        provider="local_ollama",
        model="BGE",
        kind="embedding",
    )
    journal.finish(event, status="success", usage={"embedding_input_tokens": 100})
    plan = {"batch_id": "fake", "embedding_model": "BGE"}
    dense.write_json_atomic(
        producer / "manifest.json",
        {
            "status": "completed",
            "run_id": "producer",
            "plan_sha256": e1.target.digest(plan),
            "token_accounting": journal.reference(),
            "artifacts": {"vectors.npz": dense.sha256_file(producer / "vectors.npz")},
        },
    )

    class Fake:
        row = {"dataset": "musique"}
        journal = Journal(
            tmp_path / "usage.jsonl", run_id="fake", method="raptor", dataset="musique"
        )

        def embed(self, texts):
            return dense.normalize_rows(
                np.random.default_rng(44).normal(size=(len(texts), 1024))
            )

        def generate(self, messages, cap, operation):
            return "A short summary of the clustered research passages.", {}

    runner = Fake()
    runner.plan = {
        **plan,
        "parent_plan": {"digest": "another-plan"},
        "lineage": [{"digest": e1.target.digest(plan)}],
    }
    with (
        patch.object(e1_indexers, "ROOT", tmp_path),
        patch("requests.Session.request", side_effect=AssertionError("HTTP forbidden")),
    ):
        result = e1_indexers.raptor_index(
            corpus, runner, tmp_path, Path(os.environ["E1_RAPTOR_SOURCE"])
        )
    assert result["passages"] == 50
    assert result["summaries"] > 0
    assert result["reload_model_calls"] == 0
    assert runner.journal.summary()["historical_cache_cost_complete"] is True

    # Reproduce the pinned numerical failure, then test our terminal policy.
    from raptor.cluster_utils import perform_clustering

    for count in (2, 3, 4):
        with pytest.raises(ValueError, match="n_neighbors must be greater than 1"):
            perform_clustering(np.ones((count, 1024)), dim=10, threshold=0.1)
        nodes = list(range(count))
        assert e1_indexers.raptor_cluster_nodes(
            nodes,
            "BGE",
            tokenizer=Mock(),
            cluster_fn=Mock(side_effect=AssertionError("UMAP forbidden")),
        ) == [[n] for n in nodes]


@pytest.mark.parametrize("kind", ["passages", "raptor_nodes"])
def test_offline_common_reader_replay_metrics_and_no_gold_in_prompt(kind):
    retrieval = {
        "kind": kind,
        "passages": [{"id": "a", "title": "Synthetic", "text": "A is in B."}],
        "source_ids": ["a"],
    }
    query = {"id": "synthetic", "question": "Where is A?"}
    label = {"id": "synthetic", "answer": "SECRET_GOLD", "supporting_ids": ["a"]}
    messages = dense.build_reader_messages(query["question"], retrieval["passages"])
    assert "SECRET_GOLD" not in json.dumps(messages)
    payload = {
        **e1.target.OPTIONS,
        "model": "iairlab/qwen3.8-27b",
        "messages": messages,
    }
    key = e1.target.digest({"payload": payload, "kind": "llm", "operation": "reader"})
    body = {
        "choices": [{"finish_reason": "stop", "message": {"content": "Answer: B"}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 3},
    }
    responses = {key: {"response": body, "response_sha256": e1.target.digest(body)}}
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        result = e1_indexers.replay_cached_reader(query, retrieval, responses, label)
        assert result["new_model_calls"] == 0
        assert result["historical_cost_complete"] is None
        assert result["metrics"]["supporting_provenance_coverage"] == 1
        assert result["metrics"]["passage_recall_at_5"] == (
            1 if kind == "passages" else None
        )
        with pytest.raises(ValueError, match="cache_miss"):
            e1_indexers.replay_cached_reader(query, retrieval, {}, label)
        body["usage"].pop("completion_tokens")
        with pytest.raises(ValueError, match="response_changed"):
            e1_indexers.replay_cached_reader(query, retrieval, responses, label)
        responses[key]["response_sha256"] = e1.target.digest(body)
        with pytest.raises(ValueError, match="unknown_usage"):
            e1_indexers.replay_cached_reader(query, retrieval, responses, label)
        body["usage"]["completion_tokens"] = 3
        body["choices"][0]["finish_reason"] = "length"
        responses[key]["response_sha256"] = e1.target.digest(body)
        with pytest.raises(ValueError, match="not_complete"):
            e1_indexers.replay_cached_reader(query, retrieval, responses, label)


def test_offline_ready_dense_integrity_and_no_embedding_fallback(tmp_path):
    corpus = [{"id": "a", "title": "Synthetic", "text": "A is in B."}]
    plan = {"embedding_digest": "fixed"}
    row = {
        "method": "dense",
        "output": "ready",
        "corpus_fingerprint": dense.corpus_fingerprint(corpus),
    }
    directory = tmp_path / "ready"
    directory.mkdir()
    np.savez_compressed(
        directory / "vectors.npz", ids=["a"], vectors=np.ones((1, 1024))
    )
    journal = Journal(
        directory / "usage.jsonl", run_id="producer", method="dense", dataset="musique"
    )
    journal.cache_hit(
        phase="index",
        operation="embedding",
        provider="local_ollama",
        model="bge",
        kind="embedding",
        object_id="a",
        producer_run_id="old",
        producer_usage_complete=False,
    )
    manifest = {
        "status": "completed",
        "plan_sha256": e1.target.digest(plan),
        "run_id": "producer",
        "token_accounting": journal.reference(),
        "artifacts": {"vectors.npz": dense.sha256_file(directory / "vectors.npz")},
    }
    dense.write_json_atomic(directory / "manifest.json", manifest)
    before = (directory / "manifest.json").read_bytes()
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        loaded = e1_indexers.load_ready_e1(plan, row, corpus, tmp_path)
        result = e1_indexers.retrieve_ready_e1(
            loaded, "Synthetic?", np.ones(1024), embedding_digest="fixed"
        )
        assert result["source_ids"] == ["a"] and result["new_embedding_calls"] == 0
        with pytest.raises(ValueError, match="model_changed"):
            e1_indexers.retrieve_ready_e1(
                loaded, "Synthetic?", np.ones(1024), embedding_digest="changed"
            )
        with pytest.raises(ValueError):
            e1_indexers.retrieve_ready_e1(
                loaded, "Synthetic?", np.zeros(1024), embedding_digest="fixed"
            )
        assert (directory / "manifest.json").read_bytes() == before
        (directory / "vectors.npz").write_bytes(b"changed")
        with pytest.raises(ValueError, match="artifact_changed"):
            e1_indexers.load_ready_e1(plan, row, corpus, tmp_path)


@pytest.fixture
def mixed_transport_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(e1, "verify_schema_recovery", lambda *a: ({"cases": []}, {}))
    monkeypatch.setattr(e1, "verify_mixed_approval", lambda *a: None)
    monkeypatch.setattr(e1, "verify_mixed_adoption", lambda *a: {})

    def make(out="run"):
        directory = tmp_path / out
        directory.mkdir()
        journal = Journal(
            directory / "usage.jsonl", run_id=out, method="hipporag2", dataset="musique"
        )
        plan = {
            "model": "qwen",
            "embedding_model": "bge",
            "endpoint": "https://example.invalid/v1",
            "mixed_extractor": e1.MIXED_EXTRACTOR,
            "mixed_claim_root": str(tmp_path / "canonical"),
        }
        row = {
            "method": "hipporag2",
            "dataset": "musique",
            "resume_kind": "mixed_native",
            "token_limit": 100000,
            "max_new_posts": 40000,
            "max_llm_posts": 4814,
        }
        session = requests.Session()
        runner = e1.Transport(
            plan, row, {"LITELLM_API_KEY": "fake"}, directory, journal, session
        )
        return runner, session

    return make


def mixed_messages():
    return [
        {"role": "system", "content": "Extract triples."},
        {"role": "user", "content": "A is in B."},
    ]


def mixed_body(finish="stop", unknown=False):
    content = (
        '{"triples":[["A","in","B"]]}'
        if finish == "stop"
        else '{"triples":' + json.dumps([["A", "in", "B"]] * 15)[:-1]
    )
    return {
        "choices": [{"finish_reason": finish, "message": {"content": content}}],
        "usage": {"prompt_tokens": 10, **({} if unknown else {"completion_tokens": 8})},
    }


@pytest.mark.parametrize(
    "failure,posts",
    [
        ("none", 2),
        ("primary_unknown", 1),
        ("primary_http", 1),
        ("ordinary_length", 1),
        ("fallback_unknown", 2),
        ("fallback_length", 2),
    ],
)
def test_mixed_bounded_routing_and_model_usage(mixed_transport_factory, failure, posts):
    runner, session = mixed_transport_factory()
    first = mixed_body("length", failure == "primary_unknown")
    if failure == "ordinary_length":
        first["choices"][0]["message"]["content"] = '{"triples":['
    second = mixed_body(
        "length" if failure == "fallback_length" else "stop",
        failure == "fallback_unknown",
    )
    replies = []
    for body in [first, second]:
        reply = Mock(status_code=200)
        reply.json.return_value = body
        replies.append(reply)
    if failure == "primary_http":
        replies[0].status_code = 400
        replies[0].raise_for_status.side_effect = requests.HTTPError("synthetic")
    session.post = Mock(side_effect=replies)
    if failure == "none":
        _, metadata = runner.generate(
            mixed_messages(), 3072, "openie_triples", {"type": "json_object"}
        )
        assert metadata["extractor_model"] == "iairlab/gpt-oss-120b"
        assert runner.journal.summary()["known_subtotal"]["llm_input_tokens"] == 20
    else:
        with pytest.raises((ValueError, requests.HTTPError)):
            runner.generate(
                mixed_messages(), 3072, "openie_triples", {"type": "json_object"}
            )
        with pytest.raises(ValueError):
            runner.generate(
                mixed_messages(), 3072, "openie_triples", {"type": "json_object"}
            )
    assert session.post.call_count == posts
    if posts == 2:
        payload = session.post.call_args_list[1].kwargs["json"]
        assert (
            payload["model"] == "iairlab/gpt-oss-120b"
            and payload["reasoning_effort"] == "low"
        )
        assert "chat_template_kwargs" not in payload and payload["max_tokens"] == 3072
        assert all(
            call.kwargs["allow_redirects"] is False
            and call.kwargs["timeout"] == (30, 300)
            for call in session.post.call_args_list
        )
        starts = [
            r for r in e1.read_records(runner.journal.path) if r["event"] == "started"
        ]
        assert [r["model"] for r in starts] == ["qwen", "iairlab/gpt-oss-120b"]


def test_mixed_known_failure_reuses_gpt_without_repaying_and_claims_across_outputs(
    mixed_transport_factory, tmp_path
):
    runner, session = mixed_transport_factory()
    original = {
        **e1.target.OPTIONS,
        "model": "qwen",
        "messages": mixed_messages(),
        "max_tokens": 3072,
        "response_format": {"type": "json_object"},
    }
    primary, _ = e1.schema_probe_payload(original, compatible=True)
    pk = e1.target.digest(
        {"payload": primary, "kind": "llm", "operation": "openie_triples"}
    )
    bad = tmp_path / "old-length.json"
    dense.write_json_atomic(bad, mixed_body("length"))
    runner.mixed_failures[pk] = {
        "response_path": str(bad),
        "response_sha256": dense.sha256_file(bad),
    }
    fallback = e1.mixed_payload(primary)
    fk = e1.target.digest(
        {"payload": fallback, "kind": "llm", "operation": "openie_triples"}
    )
    good = tmp_path / "old-gpt.json"
    dense.write_json_atomic(good, mixed_body())
    item = {
        "path": good,
        "sha256": dense.sha256_file(good),
        "run_id": "producer",
        "producer_complete": True,
        "kind": "llm",
        "operation": "openie_triples",
        "provider": "target_api",
        "model": "iairlab/gpt-oss-120b",
    }
    runner.parent_cache[fk] = item
    session.post = Mock(side_effect=AssertionError("HTTP forbidden"))
    for _ in range(2):
        runner.generate(
            mixed_messages(), 3072, "openie_triples", {"type": "json_object"}
        )
    assert (
        runner.journal.summary()["attempts"] == 0
        and runner.journal.summary()["known_subtotal"]["llm_input_tokens"] == 0
    )
    assert runner.last_cache_hit and session.post.call_count == 0
    other, other_session = mixed_transport_factory("another-output")
    other.mixed_failures = runner.mixed_failures.copy()
    other.parent_cache[fk] = item
    other_session.post = Mock(side_effect=AssertionError("HTTP forbidden"))
    with pytest.raises(ValueError, match="unresolved_fallback_claim"):
        other.generate(
            mixed_messages(), 3072, "openie_triples", {"type": "json_object"}
        )
    assert other_session.post.call_count == 0


def test_mixed_primary_full_cache_has_priority(mixed_transport_factory, tmp_path):
    runner, session = mixed_transport_factory()
    payload = {
        **e1.target.OPTIONS,
        "model": "qwen",
        "messages": mixed_messages(),
        "max_tokens": 3072,
        "response_format": {"type": "json_object"},
    }
    key = e1.target.digest(
        {"payload": payload, "kind": "llm", "operation": "openie_triples"}
    )
    response = tmp_path / "full-primary.json"
    dense.write_json_atomic(response, mixed_body())
    runner.parent_cache[key] = {
        "path": response,
        "sha256": dense.sha256_file(response),
        "run_id": "qwen-producer",
        "producer_complete": False,
        "kind": "llm",
        "operation": "openie_triples",
        "provider": "target_api",
        "model": "qwen",
    }
    runner.mixed_failures[key] = {
        "response_path": "must not be read",
        "response_sha256": "bad",
    }
    session.post = Mock(side_effect=AssertionError("HTTP forbidden"))
    _, metadata = runner.generate(
        mixed_messages(), 3072, "openie_triples", {"type": "json_object"}
    )
    assert (
        metadata["extractor_model"] == "qwen"
        and runner.journal.summary()["attempts"] == 0
    )
    assert not runner.journal.summary()["historical_cache_cost_complete"]


def test_mixed_twenty_slots_and_deterministic_audit(mixed_transport_factory, tmp_path):
    runner, session = mixed_transport_factory()
    primary, _ = e1.schema_probe_payload(
        {
            **e1.target.OPTIONS,
            "model": "qwen",
            "messages": mixed_messages(),
            "max_tokens": 3072,
            "response_format": {"type": "json_object"},
        },
        compatible=True,
    )
    key = e1.target.digest(
        {"payload": primary, "kind": "llm", "operation": "openie_triples"}
    )
    bad = tmp_path / "bad.json"
    dense.write_json_atomic(bad, mixed_body("length"))
    runner.mixed_failures[key] = {
        "response_path": str(bad),
        "response_sha256": dense.sha256_file(bad),
    }
    claims = Path(runner.plan["mixed_claim_root"]) / "musique"
    claims.mkdir(parents=True)
    for i in range(20):
        (claims / f"{i}.claim.json").write_text("{}", encoding="utf-8")
    session.post = Mock(side_effect=AssertionError("HTTP forbidden"))
    with pytest.raises(ValueError, match="fallback_limit"):
        runner.generate(
            mixed_messages(), 3072, "openie_triples", {"type": "json_object"}
        )
    producers = {str(i): "qwen" if i % 2 else "gpt" for i in range(50)}
    a = e1.mixed_audit_selection("musique", producers, ["0"], ["1"])
    b = e1.mixed_audit_selection(
        "musique", dict(reversed(list(producers.items()))), ["0"], ["1"]
    )
    assert a == b and all(len(v) == 8 for v in a["strata"].values())
    assert (
        "0" in a["selected_ids"]
        and "1" not in a["selected_ids"]
        and a["accuracy_threshold"] is None
    )


@pytest.fixture
def synthetic_mixed_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    directory = tmp_path / "mixed"
    directory.mkdir()
    corpus = [
        {"id": str(i), "title": "Synthetic", "text": f"{i} is in B."} for i in range(20)
    ]
    processed = tmp_path / "data/processed/musique"
    processed.mkdir(parents=True)
    dense.write_json_atomic(processed / "corpus.json", corpus)
    source_map = {p["id"]: "chunk-" + p["id"] for p in corpus}
    routes = {}
    outcomes = {}
    for i, doc in enumerate(corpus):
        model = "qwen" if i % 2 else "iairlab/gpt-oss-120b"
        response = directory / f"response-{i}.json"
        dense.write_json_atomic(
            response,
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps({"triples": [[str(i), "in", "B"]]})
                        },
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )
        key = f"request-{i}"
        routes[key] = {
            "actual_request_sha256": key,
            "response_path": str(response),
            "response_sha256": dense.sha256_file(response),
            "model": model,
        }
        outcomes["chunk-" + str(i)] = {
            "extractor_model": model,
            "triples_request_sha256": key,
            "warning": i == 0,
        }
    dense.write_json_atomic(directory / "source-map.json", source_map)
    dense.write_json_atomic(directory / "mixed-routes.json", routes)
    dense.write_json_atomic(directory / "openie-validation.json", outcomes)
    journal = Journal(
        directory / "usage.jsonl",
        run_id="synthetic",
        method="hipporag2",
        dataset="musique",
    )
    journal.cache_hit(
        phase="index",
        operation="openie_triples",
        provider="target_api",
        model="qwen",
        kind="llm",
        object_id="request-1",
        producer_run_id="known",
        producer_usage_complete=False,
    )
    plan = {
        "data_root": str(tmp_path),
        "audit_calibration_ids": ["1"],
        "mixed_adoption": {"source_review_sha256": "old-negative-calibration-review"},
    }
    row = {
        "output": "mixed",
        "dataset": "musique",
        "corpus_fingerprint": dense.corpus_fingerprint(corpus),
    }
    dense.write_json_atomic(
        directory / "manifest.json",
        {
            "run_id": "synthetic",
            "status": "indexed_pending_audit",
            "seconds": 1,
            "plan_sha256": e1.target.digest(plan),
            "validation": {"passages": 20},
            "token_accounting": journal.reference(),
            "artifacts": {
                p.name: dense.sha256_file(p) for p in directory.iterdir() if p.is_file()
            },
        },
    )
    return plan, row, directory


@pytest.mark.parametrize(
    "change", ["none", "missing", "warning", "sha", "evidence", "response", "category"]
)
def test_mixed_audit_required_before_completion(
    synthetic_mixed_audit, tmp_path, change
):
    plan, row, directory = synthetic_mixed_audit
    old = (directory / "manifest.json").read_bytes()
    with patch(
        "requests.sessions.Session.request",
        side_effect=AssertionError("HTTP forbidden"),
    ):
        audit = e1.prepare_mixed_audit(plan, row)
        assert "0" in audit["selected_ids"] and "1" not in audit["selected_ids"]
        ap = directory / "source-audit.json"
        dense.write_json_atomic(ap, audit)
        reviews = [
            {
                "id": c["id"],
                "status": "observed_error" if c["id"] == "0" else "supported",
                "all_triples_reviewed": True,
                "comment": "Synthetic source manually checked; errors retained.",
                "categories": ["attachment"] if c["id"] == "0" else [],
                "source_evidence": "is in B.",
                "structural_warning_resolved": True,
            }
            for c in audit["cases"]
        ]
        review = {
            "audit_sha256": dense.sha256_file(ap),
            "reviewer": "assistant_synthetic_fixture",
            "reviews": reviews,
        }
        if change == "missing":
            reviews.pop()
        if change == "warning":
            next(r for r in reviews if r["id"] == "0")[
                "structural_warning_resolved"
            ] = False
        if change == "sha":
            review["audit_sha256"] = "wrong"
        if change == "evidence":
            reviews[0]["source_evidence"] = "not in source"
        if change == "category":
            next(r for r in reviews if r["id"] == "0")["categories"] = []
        if change == "response":
            (directory / "response-0.json").write_text("{}", encoding="utf-8")
        rp = tmp_path / "review.json"
        dense.write_json_atomic(rp, review)
        if change == "none":
            final = e1.finalize_mixed_audit(plan, row, rp)
            assert final["status"] == "completed"
            assert final["validation"]["source_audit"]["observed_error_sources"] == 1
            assert final["validation"]["source_audit"]["semantic_verified"] is False
            assert (directory / "index-build-manifest.json").read_bytes() == old
            assert not final["token_accounting"]["summary"][
                "historical_cache_cost_complete"
            ]
        else:
            with pytest.raises(ValueError):
                e1.finalize_mixed_audit(plan, row, rp)
            assert (directory / "manifest.json").read_bytes() == old


def test_mixed_invalid_operation_rejected_before_post(mixed_transport_factory):
    runner, session = mixed_transport_factory()
    session.post = Mock(side_effect=AssertionError("HTTP forbidden"))
    for op, cap in [("reader", 1024), ("openie_triples", 4096), ("openie_ner", 512)]:
        with pytest.raises(ValueError, match="operation_or_cap_changed"):
            runner.generate(mixed_messages(), cap, op, {"type": "json_object"})
    assert session.post.call_count == 0


def test_mixed_plan_claim_bounds_and_hotpot_gate_before_any_http(tmp_path, monkeypatch):
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    monkeypatch.setattr(e1, "git", lambda *a: "head")
    monkeypatch.setattr(e1, "code_dirty", lambda: False)
    monkeypatch.setattr(e1, "verify_mixed_approval", lambda *a: None)
    monkeypatch.setattr(e1, "verify_mixed_adoption", lambda *a: {})
    monkeypatch.setattr(e1, "mixed_history", lambda *a: ([], []))
    parent = {
        "rows": [{"method": "hipporag2", "dataset": "musique", "output": "old-mu"}]
    }
    pp = tmp_path / "parent.json"
    dense.write_json_atomic(pp, parent)
    rows = [
        {
            "method": m,
            "dataset": d,
            "run_id": m + d,
            "code_commit": "head",
            "token_limit": e1.LIMITS[m],
            "output": f"indexes/e1/batch/{m}/{d}-mixed1"
            if m == "hipporag2"
            else f"ready/{m}/{d}",
            **(
                {
                    "resume_kind": "mixed_native",
                    "history_runs": [],
                    "resume_sources": [],
                    "prior_budget_charge": 0,
                    "max_new_posts": 40000,
                    "max_llm_posts": e1.MIXED_EXTRACTOR["max_llm_posts"][d],
                }
                if m == "hipporag2"
                else {}
            ),
        }
        for m in e1.METHODS
        for d in e1.DATASETS
    ]
    root = tmp_path / "old-mu/mixed-continuation-claims"
    root.mkdir(parents=True)
    plan = {
        "kind": "E1_full_corpus_indexing",
        "parameters": e1.PARAMETERS,
        "workspace": str(tmp_path),
        "batch_id": "batch",
        "parent_plan": {"path": str(pp), "sha256": dense.sha256_file(pp)},
        "rows": rows,
        "combined_token_limit": sum(r["token_limit"] for r in rows),
        "mixed_claim_root": str(root),
        "model": "qwen",
        "endpoint": "https://example.invalid/v1",
    }
    dense.write_json_atomic(root / "plan.claim.json", e1.mixed_plan_claim(plan))
    mu = next(
        r for r in rows if (r["method"], r["dataset"]) == ("hipporag2", "musique")
    )
    hot = next(
        r for r in rows if (r["method"], r["dataset"]) == ("hipporag2", "hotpotqa")
    )
    (tmp_path / mu["output"]).mkdir(parents=True)
    dense.write_json_atomic(
        tmp_path / mu["output"] / "manifest.json", {"status": "indexed_pending_audit"}
    )
    config = {"TARGET_API_MODEL": "qwen", "TARGET_API_BASE_URL": plan["endpoint"]}
    with patch(
        "requests.sessions.Session.request",
        side_effect=AssertionError("HTTP forbidden"),
    ):
        with pytest.raises(ValueError, match="completed_musique_audit"):
            e1.verify_plan(plan, hot, config)
        mu["max_llm_posts"] += 1
        with pytest.raises(ValueError, match="history_or_request_bounds_changed"):
            e1.verify_plan(plan, mu, config)
        mu["max_llm_posts"] -= 1
        dense.write_json_atomic(
            root / "plan.claim.json",
            {"children": {}, "parent_plan_sha256": dense.sha256_file(pp)},
        )
        with pytest.raises(ValueError, match="canonical_plan_claim_changed"):
            e1.verify_plan(plan, mu, config)


def test_mixed_pending_export_has_no_journal_or_double_initial_cost(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    (tmp_path / "results/summary").mkdir(parents=True)
    plan = {
        "batch_id": "batch",
        "model": "qwen",
        "embedding_model": "bge",
        "embedding_digest": "digest",
        "parameters": {},
        "combined_token_limit": 20000000,
        "mixed_extractor": e1.MIXED_EXTRACTOR,
        "rows": [
            {
                "method": "hipporag2",
                "dataset": "musique",
                "run_id": "new",
                "output": "pending",
                "resume_kind": "mixed_native",
                "history_runs": [],
                "diagnostics_in_history": True,
            }
        ],
    }
    pp = tmp_path / "plan.json"
    dense.write_json_atomic(pp, plan)
    with patch(
        "requests.sessions.Session.request",
        side_effect=AssertionError("HTTP forbidden"),
    ):
        report = e1.export(plan, pp)
    assert report["physical_known_tokens"] == 0
    assert report["rows"][0]["llm_by_model"] == {}
    assert report["cost_complete"] is False
    assert not (tmp_path / "pending").exists()
