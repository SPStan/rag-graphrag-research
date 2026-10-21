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
