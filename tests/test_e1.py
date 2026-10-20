"""Offline spending guards and actual pinned SDK index/save/reload checks."""

import os
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


@pytest.mark.skipif(
    not os.environ.get("E1_HIPPO_SOURCE"),
    reason="isolated pinned HippoRAG SDK required",
)
def test_real_hipporag_sdk_index_and_reload_without_http(tmp_path):
    class Fake:
        plan = {"endpoint": "https://example.invalid", "model": "qwen"}
        row = {"dataset": "musique"}
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
    runner.plan = {**plan, "parent_plan": {"digest": e1.target.digest(plan)}}
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
