"""No model calls: physical totals and standalone attribution are distinct."""

from copy import deepcopy

from scripts.run_e1 import attribute_costs, row_usage


def row(method, run, tokens, complete=True, historical=True):
    return {
        "method": method,
        "run_id": run,
        "seconds": 2,
        "token_accounting": {
            "summary": {
                "complete": complete,
                "historical_cache_cost_complete": historical,
                "known_subtotal": {"embedding_input_tokens": tokens},
            }
        },
    }


def test_standalone_includes_failed_producer_history_without_physical_double_count():
    producer = row("dense", "p", 100)
    producer["cumulative_accounting"] = deepcopy(row_usage(producer))
    producer["cumulative_accounting"]["known_subtotal"]["embedding_input_tokens"] = 119
    producer["cumulative_accounting"]["complete"] = False
    producer["cumulative_seconds"] = 5
    consumer = row("raptor", "c", 10)
    consumer["validation"] = {"leaf_producer_run_id": "p"}
    rows = [producer, consumer]
    before = deepcopy(rows)
    attribute_costs(rows)
    assert consumer["standalone_known_subtotal"]["embedding_input_tokens"] == 129
    assert consumer["attributed_construction_seconds"] == 7
    assert consumer["measured_run_seconds"] == 2
    assert not consumer["standalone_cost_complete"]
    assert (
        sum(row_usage(r)["known_subtotal"]["embedding_input_tokens"] for r in rows)
        == 129
    )
    assert [row_usage(r) for r in rows] == [row_usage(r) for r in before]


def test_historical_unknown_is_not_complete():
    rows = [row("hipporag2", "h", 20, historical=False)]
    attribute_costs(rows)
    assert not rows[0]["standalone_cost_complete"]


def test_missing_producer_and_unknown_time_are_explicit():
    consumer = row("raptor", "c", 10)
    attribute_costs([consumer])
    assert not consumer["standalone_cost_complete"]
    producer = row("dense", "p", 100)
    del producer["seconds"]
    consumer["validation"] = {"leaf_producer_run_id": "p"}
    attribute_costs([producer, consumer])
    assert consumer["attributed_construction_seconds"] is None
    assert consumer["standalone_cost_complete"]


def test_embedding_diagnostic_keeps_failed_cost_unknown_and_counts_once(
    tmp_path, monkeypatch
):
    from scripts import run_e1 as e1, run_dense as dense
    from scripts.token_accounting import Journal

    parent = tmp_path / "raptor/musique"
    probe = tmp_path / "raptor/musique-embedding-probe1"
    for folder, run_id, status, tokens in [
        (parent, "failed", "failed", 7),
        (probe, "probe", "completed", 5),
    ]:
        (folder / "requests").mkdir(parents=True)
        j = Journal(
            folder / "usage.jsonl", run_id=run_id, method="raptor", dataset="musique"
        )
        a = j.start(
            phase="index",
            operation="index_embedding",
            provider="local_ollama",
            model="bge",
            kind="embedding",
            object_id="known",
        )
        j.finish(a, status="success", usage={"embedding_input_tokens": tokens})
        if folder == parent:
            a = j.start(
                phase="index",
                operation="index_embedding",
                provider="local_ollama",
                model="bge",
                kind="embedding",
                object_id="bad",
            )
            j.finish(a, status="error")
            dense.write_json_atomic(
                folder / "requests/bad.json", {"reserved_tokens": 100}
            )
        manifest = {
            "status": status,
            "run_id": run_id,
            "seconds": 1,
            "token_accounting": j.reference(),
            "artifacts": {
                p.relative_to(folder).as_posix(): dense.sha256_file(p)
                for p in folder.rglob("*")
                if p.is_file()
            },
        }
        if folder == probe:
            manifest.update(
                parent_manifest_sha256=dense.sha256_file(parent / "manifest.json"),
                unknown_reserved_upper_bound=0,
                full_index_authorized=False,
                cases=[],
            )
        dense.write_json_atomic(folder / "manifest.json", manifest)
    plan = {
        "batch_id": "b",
        "model": "qwen",
        "embedding_model": "bge",
        "embedding_digest": "digest",
        "parameters": {},
        "combined_token_limit": 12000000,
        "rows": [
            {
                "method": "raptor",
                "dataset": "musique",
                "run_id": "failed",
                "output": "raptor/musique",
            }
        ],
    }
    path = tmp_path / "plan.json"
    dense.write_json_atomic(path, plan)
    (tmp_path / "results/summary").mkdir(parents=True)
    monkeypatch.setattr(e1, "ROOT", tmp_path)
    for _ in range(2):
        report = e1.export(plan, path)
        assert report["physical_known_tokens"] == 12
        assert report["budget_charge_upper_bound"] == 112
        assert not report["physical_usage_complete"]
        assert not report["cost_complete"]
        assert report["rows"][0]["embedding_probe"]["status"] == "completed"
        assert e1.row_usage(report["rows"][0])["attempts"] == 3
