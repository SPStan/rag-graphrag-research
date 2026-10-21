from unittest.mock import Mock, patch

import numpy as np
import pytest
import requests

from scripts import run_e1 as e
from scripts import run_dense as d
from scripts.token_accounting import Journal


def fixture(tmp_path):
    corpus = [
        {"id": "a", "title": "A", "text": "text"},
        {"id": "b", "title": "B", "text": "text"},
    ]
    plan = {
        "kind": "E1_full_corpus_indexing",
        "batch_id": "batch",
        "workspace": str(tmp_path),
        "data_root": str(tmp_path),
        "model": "qwen",
        "endpoint": "https://example.invalid/v1",
        "embedding_model": "bge-m3:latest",
        "embedding_digest": "digest",
        "parameters": e.PARAMETERS,
        "combined_token_limit": 68000000,
        "independent_raptor": True,
        "rows": [
            {
                "method": m,
                "dataset": ds,
                "run_id": f"{m}-{ds}",
                "output": f"indexes/e1/batch/{m}/{ds}",
                "code_commit": "old",
                "token_limit": e.LIMITS[m],
                "corpus": {},
                "corpus_fingerprint": d.corpus_fingerprint(corpus),
            }
            for m in e.METHODS
            for ds in e.DATASETS
        ],
    }
    prior = tmp_path / "prior.json"
    d.write_json_atomic(prior, plan)
    for row in plan["rows"][:2]:
        folder = tmp_path / row["output"]
        folder.mkdir(parents=True)
        j = Journal(
            folder / "usage.jsonl",
            run_id=row["run_id"],
            method="dense",
            dataset=row["dataset"],
        )
        a = j.start(
            phase="index",
            operation="index_embedding",
            provider="local_ollama",
            model=plan["embedding_model"],
            kind="embedding",
        )
        j.finish(a, status="success", usage={"embedding_input_tokens": 7})
        np.savez_compressed(
            folder / "vectors.npz",
            ids=[x["id"] for x in corpus],
            vectors=np.ones((2, 1024)),
        )
        save(folder, row["run_id"], j, "completed", plan_sha256=e.target.digest(plan))
    row = plan["rows"][4]
    folder = tmp_path / row["output"]
    folder.mkdir(parents=True)
    j = Journal(
        folder / "usage.jsonl", run_id=row["run_id"], method="raptor", dataset="musique"
    )
    j.cache_hit(
        phase="index",
        operation="index_embedding",
        provider="local_ollama",
        model=plan["embedding_model"],
        kind="embedding",
        object_id=e.target.digest("A\ntext"),
        producer_run_id=plan["rows"][0]["run_id"],
        producer_usage_complete=True,
    )
    runner = e.Transport(plan, row, {"LITELLM_API_KEY": "test-secret"}, folder, j)
    response = Mock(status_code=200)
    response.json.return_value = {
        "choices": [{"finish_reason": "stop", "message": {"content": "saved summary"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    runner.session.post = Mock(return_value=response)
    runner.generate([], 4096, "summary")
    runner.session.post.side_effect = requests.ConnectionError("failed embedding")
    with pytest.raises(requests.ConnectionError):
        runner.embed(["saved summary"])
    save(folder, row["run_id"], j, "failed")
    probe = folder.parent / "musique-embedding-probe1"
    probe.mkdir()
    pj = Journal(
        probe / "usage.jsonl", run_id="probe", method="raptor", dataset="musique"
    )
    probe_runner = e.Transport(
        plan, {**row, "embedding_options": e.RAPTOR_EMBEDDING_OPTIONS}, {}, probe, pj
    )
    response = Mock(status_code=200)
    response.json.return_value = {"embeddings": [[1.0] * 1024], "prompt_eval_count": 7}
    probe_runner.session.post = Mock(return_value=response)
    probe_runner.embed(["saved summary"])
    save(
        probe,
        "probe",
        pj,
        "completed",
        embedding_options=e.RAPTOR_EMBEDDING_OPTIONS,
        parent_manifest_sha256=d.sha256_file(folder / "manifest.json"),
        full_index_authorized=False,
        unknown_reserved_upper_bound=0,
        cases=[],
    )
    return prior, plan, corpus, folder, probe


def save(folder, run_id, journal, status, **extra):
    manifest = {
        "run_id": run_id,
        "status": status,
        "seconds": 1,
        "token_accounting": journal.reference(),
        "artifacts": {
            p.relative_to(folder).as_posix(): d.sha256_file(p)
            for p in folder.rglob("*")
            if p.is_file() and p.name != "manifest.json"
        },
        **extra,
    }
    d.write_json_atomic(folder / "manifest.json", manifest)


@pytest.mark.parametrize("broken", [None, "vectors", "active", "probe"])
def test_batch_resume_verifies_leaf_and_physical_cache_before_claim(tmp_path, broken):
    prior, original, corpus, folder, probe = fixture(tmp_path)
    original_sha = d.sha256_file(prior)
    if broken == "vectors":
        (tmp_path / original["rows"][0]["output"] / "vectors.npz").write_bytes(
            b"changed"
        )
    elif broken == "active":
        (folder / "running.lock").write_text("123", encoding="utf-8")
    elif broken == "probe":
        next((probe / "requests").glob("*.response.json")).write_text(
            "{}", encoding="utf-8"
        )
    with (
        patch.object(e, "ROOT", tmp_path),
        patch.object(e, "code_dirty", return_value=False),
        patch.object(e, "git", return_value="new"),
        patch.object(e, "load_corpus", return_value=(corpus, {})),
        patch("requests.Session.request", side_effect=AssertionError("HTTP forbidden")),
    ):
        if broken:
            with pytest.raises(ValueError):
                e.raptor_batch_plan(prior)
            assert not (folder / "embedding-resume-once.claim.json").exists()
            return
        child = e.raptor_batch_plan(prior)
        row = child["rows"][4]
        reserve = e.current_unknown_reservation(folder)
        assert row["token_limit"] == 12000000 - 15 - 7 - reserve
        assert row["prior_budget_charge"] + row["token_limit"] == 12000000
        assert row["verified_response_cache_count"] == 2
        assert child["rows"][:4] == original["rows"][:4]
        assert child["rows"][5]["token_limit"] == 12000000
        assert row["diagnostics_in_history"] is True
        assert d.sha256_file(prior) == original_sha
        with pytest.raises(FileExistsError):
            e.raptor_batch_plan(prior)
        output = tmp_path / row["output"]
        output.mkdir()
        journal = Journal(
            output / "usage.jsonl",
            run_id=row["run_id"],
            method="raptor",
            dataset="musique",
        )
        runner = e.Transport(child, row, {}, output, journal)
        runner.session.post = Mock(side_effect=AssertionError("HTTP forbidden"))
        assert runner.generate([], 4096, "summary")[0] == "saved summary"
        assert runner.embed(["saved summary"]).shape == (1, 1024)
        assert journal.summary()["attempts"] == 0
        assert not journal.summary()["historical_cache_cost_complete"]
        (tmp_path / "results/summary").mkdir(parents=True)
        before = e.export(original, prior)
        after = e.export(child, prior)
        assert before["physical_known_tokens"] == after["physical_known_tokens"] == 36
        assert (
            before["budget_charge_upper_bound"]
            == after["budget_charge_upper_bound"]
            == 36 + reserve
        )
        assert not after["cost_complete"]


def test_leaf_hit_cannot_claim_an_unverified_producer(tmp_path):
    prior, plan, corpus, folder, _ = fixture(tmp_path)
    with (
        patch.object(e, "ROOT", tmp_path),
        patch.object(e, "load_corpus", return_value=(corpus, {})),
    ):
        scope = e.verified_raptor_leaf_scope(plan, plan["rows"][4])
        scope["run_id"] = "other"
        with pytest.raises(ValueError, match="unverified_dense_leaf"):
            e.verified_checkpoints(folder / "manifest.json", leaf_producer=scope)


@pytest.mark.parametrize("count", range(5))
def test_small_raptor_groups_preserve_every_node_without_reduction_or_http(count):
    from types import SimpleNamespace
    from scripts.e1_indexers import raptor_cluster_nodes

    nodes = [SimpleNamespace(text="long " * 4000, embeddings={}) for _ in range(count)]
    reduce = Mock(side_effect=AssertionError("small groups must not use UMAP"))
    with patch(
        "requests.Session.request", side_effect=AssertionError("HTTP forbidden")
    ):
        groups = raptor_cluster_nodes(nodes, "BGE", tokenizer=Mock(), cluster_fn=reduce)
    assert len(groups) == count
    assert all(len(g) == 1 and g[0] is n for g, n in zip(groups, nodes))
    reduce.assert_not_called()


def test_raptor_recursive_small_group_terminates_and_keeps_normal_grouping():
    from types import SimpleNamespace
    from scripts.e1_indexers import raptor_cluster_nodes

    nodes = [
        SimpleNamespace(text="a b c", embeddings={"BGE": [i, 1]}) for i in range(7)
    ]
    # Two overlapping groups; the four-node group exceeds the token cap.
    memberships = (
        [np.array([0]) for _ in range(3)]
        + [np.array([0, 1])]
        + [np.array([1]) for _ in range(3)]
    )
    reduce = Mock(return_value=memberships)
    tokenizer = SimpleNamespace(encode=lambda text: text.split())
    groups = raptor_cluster_nodes(
        nodes,
        "BGE",
        10,
        tokenizer=tokenizer,
        reduction_dimension=5,
        cluster_fn=reduce,
    )
    assert [[nodes.index(n) for n in g] for g in groups] == [
        [0],
        [1],
        [2],
        [3],
        [3],
        [4],
        [5],
        [6],
    ]
    reduce.assert_called_once()
    assert reduce.call_args.kwargs == {"dim": 5, "threshold": 0.1}


def test_raptor_ordinary_groups_use_pinned_labels_unchanged():
    from types import SimpleNamespace
    from scripts.e1_indexers import raptor_cluster_nodes

    nodes = [SimpleNamespace(text="x", embeddings={"BGE": [i]}) for i in range(6)]
    memberships = [np.array([i % 2]) for i in range(6)]
    groups = raptor_cluster_nodes(
        nodes,
        "BGE",
        tokenizer=SimpleNamespace(encode=list),
        cluster_fn=Mock(return_value=memberships),
    )
    assert groups == [nodes[::2], nodes[1::2]]


@pytest.mark.parametrize("broken", [None, "active", "tampered", "unknown"])
def test_clustering_resume_preserves_budget_cache_and_canonical_claim(tmp_path, broken):
    prior, original, corpus, _, _ = fixture(tmp_path)
    with (
        patch.object(e, "ROOT", tmp_path),
        patch.object(e, "code_dirty", return_value=False),
        patch.object(e, "git", return_value="new"),
        patch.object(e, "load_corpus", return_value=(corpus, {})),
        patch("requests.Session.request", side_effect=AssertionError("HTTP forbidden")),
    ):
        batch = e.raptor_batch_plan(prior)
        batch_path = tmp_path / "batch-plan.json"
        d.write_json_atomic(batch_path, batch)
        row = batch["rows"][4]
        folder = tmp_path / row["output"]
        folder.mkdir()
        journal = Journal(
            folder / "usage.jsonl",
            run_id=row["run_id"],
            method="raptor",
            dataset="musique",
        )
        runner = e.Transport(
            batch, row, {"LITELLM_API_KEY": "test-secret"}, folder, journal
        )
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [
                {"finish_reason": "stop", "message": {"content": "next summary"}}
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        }
        runner.session.post = Mock(return_value=response)
        runner.generate([{"role": "user", "content": "new cluster"}], 4096, "summary")
        if broken == "unknown":
            runner.session.post.side_effect = requests.ConnectionError("timeout")
            with pytest.raises(requests.ConnectionError):
                runner.embed(["next summary"])
        save(folder, row["run_id"], journal, "failed", error_type="ValueError")
        if broken == "active":
            (folder / "running.lock").write_text("123", encoding="utf-8")
        if broken == "tampered":
            next((folder / "requests").glob("*.response.json")).write_text(
                "{}", encoding="utf-8"
            )
        claim = folder / "clustering-resume-once.claim.json"
        if broken:
            with pytest.raises(ValueError):
                e.raptor_clustering_plan(batch_path)
            assert not claim.exists()
            return
        child = e.raptor_clustering_plan(batch_path)
        cr = child["rows"][4]
        assert cr["token_limit"] == row["token_limit"] - 20
        assert cr["prior_budget_charge"] + cr["token_limit"] == e.LIMITS["raptor"]
        assert cr["output"].endswith("musique-cluster1")
        assert len(cr["history_runs"]) == 3
        assert cr["verified_response_cache_count"] == 3
        assert child["rows"][:4] == batch["rows"][:4]
        assert child["rows"][5]["token_limit"] == batch["rows"][5]["token_limit"]
        with pytest.raises(FileExistsError):
            e.raptor_clustering_plan(batch_path)
        output = tmp_path / cr["output"]
        output.mkdir()
        cj = Journal(
            output / "usage.jsonl",
            run_id=cr["run_id"],
            method="raptor",
            dataset="musique",
        )
        replay = e.Transport(child, cr, {}, output, cj)
        replay.session.post = Mock(side_effect=AssertionError("HTTP forbidden"))
        assert (
            replay.generate(
                [{"role": "user", "content": "new cluster"}], 4096, "summary"
            )[0]
            == "next summary"
        )
        assert cj.summary()["attempts"] == 0
        (tmp_path / "results/summary").mkdir(parents=True)
        before = e.export(batch, batch_path)
        after = e.export(child, batch_path)
        assert after["raptor_clustering_policy"] == e.RAPTOR_CLUSTERING_POLICY
        assert before["physical_known_tokens"] == after["physical_known_tokens"]
        assert before["budget_charge_upper_bound"] == after["budget_charge_upper_bound"]
        assert not after["cost_complete"]
