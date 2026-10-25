"""Existing shared runner on60 synthetic cases; no actual HTTP/model clients."""

import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import e2_evaluation as e2, run_dense as dense, run_dense_target as runner


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    vector = np.zeros(1024)
    vector[0] = 1
    corpus = [
        {"id": f"p{i}", "title": f"Paris{i}", "text": "A city."} for i in range(5)
    ]
    datasets = {}
    for dataset in runner.DATASETS:
        raw = tmp_path / f"data/processed/{dataset}"
        raw.mkdir(parents=True)
        queries = [{"id": f"q{i}", "question": f"Which city {i}?"} for i in range(10)]
        dense.write_json_atomic(raw / "corpus.json", corpus)
        dense.write_json_atomic(raw / "queries.json", queries)
        dense.write_json_atomic(
            raw / "labels.json",
            [
                {"id": q["id"], "answer": "Paris", "supporting_ids": ["p0"]}
                for q in queries
            ],
        )
        datasets[dataset] = {
            "question_ids": [q["id"] for q in queries],
            "labels_sha256_evaluator_only": dense.sha256_file(raw / "labels.json"),
            "indexes": [
                {
                    "method": m,
                    "manifest_sha256": f"{dataset}-{m}",
                    "e1_row": {"method": m, "dataset": dataset},
                }
                for m in e2.METHODS
            ],
        }
    source = tmp_path / "e1.json"
    dense.write_json_atomic(source, {"data_root": str(tmp_path)})
    (tmp_path / ".cache").mkdir()
    base = {
        "version": e2.VERSION,
        "mode": "smoke10_pending_approval",
        "datasets": datasets,
        "e1_plan": str(source),
        "e1_plan_sha256": dense.sha256_file(source),
        "e1_workspace": str(tmp_path),
        "reader_options": runner.OPTIONS,
        "reader_model": e2.MODEL,
        "embedding_model": "bge-m3:latest",
        "embedding_digest": "bge",
        "max_posts": 140,
        "max_llm_posts": 80,
        "max_embedding_posts": 60,
        "max_combined_tokens": e2.LIMIT,
        "reader_calls": 60,
        "filter_calls": 20,
        "tokenizer_cache": {"directory": str(tmp_path), "sha256": {"cached": "sha"}},
    }

    def fresh(*args):
        return {
            **copy.deepcopy(base),
            "code_sha256": {p: dense.sha256_file(e2.ROOT / p) for p in e2.CODE_FILES},
        }

    monkeypatch.setattr(e2, "prepare", fresh)
    monkeypatch.setattr(e2, "verify_parent_code", lambda p: None)
    from scripts import preflight_hipporag_repair_prompts

    monkeypatch.setattr(
        preflight_hipporag_repair_prompts,
        "verify_target_prompt_installation",
        lambda p: None,
    )

    def load(plan, row, corpus, workspace):
        return {
            "kind": "dense",
            "manifest_sha256": f"{row['dataset']}-{row['method']}",
            "embedding_digest": "bge",
            "vectors": np.asarray([vector] * len(corpus)),
            "corpus": corpus,
        }

    monkeypatch.setattr(e2.indexes, "load_ready_e1", load)
    monkeypatch.setattr(
        e2.indexes,
        "load_hippo_query_only",
        lambda loaded, source, infer: SimpleNamespace(
            extraction_llm=SimpleNamespace(handler=infer)
        ),
    )

    def hippo(loaded, rag, question, query_vector, embedding_digest):
        rag.extraction_llm.handler([{"role": "user", "content": "filter-marker"}])
        return e2.indexes.retrieve_ready_e1(
            loaded, question, query_vector, embedding_digest=embedding_digest
        )

    monkeypatch.setattr(e2.indexes, "retrieve_hippo_query_only", hippo)
    monkeypatch.setattr(e2.indexes.raptor, "load_source", lambda p: {})
    monkeypatch.setattr(e2.time, "sleep", lambda seconds: None)
    state = {
        "posts": [],
        "reader_outcomes": ["stop", "stop", "length"],
        "filter_failure": False,
        "fault": None,
    }

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"models": [{"name": "bge-m3:latest", "digest": "bge"}]},
            )

        def post(self, url, *, json, **kwargs):
            assert kwargs["allow_redirects"] is False and kwargs["timeout"] == (30, 300)
            operation = (
                "embedding"
                if url.endswith("/api/embed")
                else "filter"
                if json["messages"][-1]["content"] == "filter-marker"
                else "reader"
            )
            state["posts"].append((operation, copy.deepcopy(json)))
            if state["fault"] == "transport":
                raise runner.requests.ConnectionError("synthetic IO failure")
            if operation == "embedding":
                body = {"embeddings": [vector.tolist()], "prompt_eval_count": 1}
            else:
                finish = (
                    state["reader_outcomes"].pop(0)
                    if operation == "reader" and state["reader_outcomes"]
                    else "stop"
                )
                if operation == "filter" and state["filter_failure"]:
                    finish = "length"
                text = "Answer: Paris" if finish != "empty" else ""
                if finish == "malformed":
                    text = "unparseable"
                body = {
                    "choices": [
                        {
                            "finish_reason": "stop"
                            if finish in ("empty", "malformed")
                            else finish,
                            "message": {"content": text},
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                }
                if state["fault"] == "model":
                    body["model"] = "different-model"
                if state["fault"] == "unknown":
                    body["usage"].pop("completion_tokens")
                if state["fault"] == "budget":
                    body["usage"]["prompt_tokens"] = e2.LIMIT
            return SimpleNamespace(
                status_code=200, json=lambda: body, raise_for_status=lambda: None
            )

    monkeypatch.setattr(runner.requests, "Session", Session)
    config = {
        "model": e2.MODEL,
        "base_url": "https://api.duckduck.cloud/v1",
        "embedding_model": "bge-m3:latest",
        "ollama_url": "http://127.0.0.1:11434",
        "key": "synthetic",
    }
    for name, value in {
        "TARGET_API_MODEL": e2.MODEL,
        "TARGET_API_BASE_URL": config["base_url"],
        "LITELLM_API_KEY": "synthetic",
        "OLLAMA_EMBED_MODEL": "bge-m3:latest",
    }.items():
        monkeypatch.setenv(name, value)
    original = tmp_path / "original-plan.json"
    dense.write_json_atomic(original, fresh())
    parent = tmp_path / "parent"
    with monkeypatch.context() as setup:
        setup.setattr(e2, "verify", lambda p: True)
        result = e2.execute(
            original,
            parent,
            "dense",
            approved_sha=dense.sha256_file(original),
            config=config,
        )
    assert (
        result["status"] == "failed"
        and len(result["results"]) == 3
        and len(state["posts"]) == 6
    )
    parent_bytes = {p.name: p.read_bytes() for p in parent.iterdir() if p.is_file()}
    child_plan = tmp_path / "child-plan.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_dense_target",
            "--shared-plan",
            str(child_plan),
            "--continue-shared-plan",
            str(original),
            "--parent-output-dir",
            str(parent),
        ],
    )
    runner.main()
    return SimpleNamespace(
        root=tmp_path,
        parent=parent,
        parent_bytes=parent_bytes,
        parent_plan=original,
        child_plan=child_plan,
        output=tmp_path / "child",
        state=state,
        config=config,
    )


def run_method(s, method, monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_dense_target",
            "--shared-plan",
            str(s.child_plan),
            "--execute",
            "--shared-method",
            method,
            "--output-dir",
            str(s.output),
            "--approved-plan-sha256",
            dense.sha256_file(s.child_plan),
        ],
    )
    runner.main()


def test_runner_continuation_60_unique_cases_and_reader_failure_resume(
    scenario, monkeypatch
):
    s = scenario
    plan = dense.read_json(s.child_plan)
    assert len(plan["remaining_cases"]) == 57
    assert (
        plan["max_posts"] == 134
        and plan["max_llm_posts"] == 77
        and plan["max_embedding_posts"] == 57
    )
    assert plan["max_combined_tokens"] <= plan["original_remaining_tokens"]
    # More known reader outcome failures must not stop subsequent questions.
    s.state["reader_outcomes"] = ["length", "empty", "malformed"]
    for method in e2.METHODS:
        run_method(s, method, monkeypatch)
    report = e2.summary(plan, s.output)
    assert report["comparison_complete"]
    assert len(report["question_results"]) == 60
    identities = {
        (r["dataset"], r["method"], r["question_id"])
        for r in report["question_results"]
    }
    assert len(identities) == 60
    assert (
        sum(r["status"] == "attempted_failed" for r in report["question_results"]) == 4
    )
    assert len(s.state["posts"]) == 140
    assert report["physical_query_accounting"]["summary"]["attempts"] == 140
    known = report["physical_query_accounting"]["summary"]["known_subtotal"]
    assert known == {
        "llm_input_tokens": 800,
        "llm_output_tokens": 320,
        "embedding_input_tokens": 60,
    }
    failed = next(
        r
        for r in report["question_results"]
        if r.get("failure_scope") == "reader_response"
    )
    assert failed["operations"][-1]["logical_usage"]["llm_output_tokens"] == 4
    assert failed["wall_seconds"] >= 0 and failed["stage_seconds"]["reader"] >= 0
    before = s.output.joinpath("usage.jsonl").read_bytes()
    for method in e2.METHODS:
        run_method(s, method, monkeypatch)
    assert (
        len(s.state["posts"]) == 140
        and (s.output / "usage.jsonl").read_bytes() == before
    )
    assert s.parent_bytes == {
        p.name: p.read_bytes() for p in s.parent.iterdir() if p.is_file()
    }
    assert dense.read_json(s.parent / "manifest.json")["status"] == "failed"
    safe = e2.write_report(s.child_plan, s.output, s.root / "report")
    assert safe["model_posts"] == 140 and safe["new_model_posts"] == 134
    assert safe["remaining_original_posts"] == 0
    assert safe["remaining_original_tokens"] == plan["original_remaining_tokens"] - 1135
    assert any(
        f.get("finish_reason") == "length" and f["question_id"] == "q2"
        for f in safe["failures"]
    )
    assert safe["e1_historical_cost"]["cost_complete"] is False
    assert (
        safe["comparative_metrics"] and safe["outcome_counts"]["attempted_failed"] == 4
    )
    assert (
        next(r for r in safe["comparative_metrics"] if r["method"] == "raptor")[
            "passage_recall_at_5"
        ]
        is None
    )

    # Even if all60 have a result file, a terminal infrastructure stop is not
    # a completed comparison. Do not publish its metrics as a complete smoke.
    terminal = dense.read_json(s.output / "manifest.json")
    terminal["status"] = "failed"
    terminal["error"] = {"type": "OSError", "reason": "synthetic finalization failure"}
    dense.write_json_atomic(s.output / "manifest.json", terminal)
    assert e2.summary(plan, s.output)["comparison_complete"] is False


@pytest.mark.parametrize("fault", ["unknown", "budget", "transport", "model"])
def test_runner_fatal_stops_no_retry(scenario, monkeypatch, fault):
    s = scenario
    s.state["fault"] = fault
    run_method(s, "dense", monkeypatch)
    manifest = dense.read_json(s.output / "manifest.json")
    assert manifest["status"] == "failed"
    count = len(s.state["posts"])
    assert count <= 8
    with pytest.raises(ValueError, match="failed_or_changed"):
        run_method(s, "dense", monkeypatch)
    assert len(s.state["posts"]) == count
    report = e2.summary(dense.read_json(s.child_plan), s.output)
    assert report["comparison_complete"] is False
    safe = e2.write_report(s.child_plan, s.output, s.root / "interrupted")
    assert safe["comparative_metrics"] is None
    if fault == "unknown":
        assert (
            safe["remaining_original_tokens"] is None
            and safe["query_cost_complete"] is False
        )
    assert any(
        r["status"] == "not_attempted" and r["metrics"]["f1"] is None
        for r in report["question_results"]
    )


@pytest.mark.parametrize(
    "change", ["reader_options", "index", "parent_pin", "code_pin"]
)
def test_runner_rejects_incompatible_before_client(scenario, monkeypatch, change):
    s = scenario
    plan = dense.read_json(s.child_plan)
    if change == "reader_options":
        plan["reader_options"] = {**runner.OPTIONS, "max_tokens": 1024}
    if change == "index":
        plan["datasets"]["musique"]["indexes"][0]["manifest_sha256"] = "changed"
    if change == "parent_pin":
        path = next(p for p in s.parent.glob("question-*.json"))
        path.write_text("tampered", encoding="utf-8")
    if change == "code_pin":
        plan["code_sha256"]["scripts/run_dense.py"] = "changed"
    dense.write_json_atomic(s.child_plan, plan)
    with pytest.raises((ValueError, json.JSONDecodeError)):
        run_method(s, "dense", monkeypatch)
    assert len(s.state["posts"]) == 6


def test_runner_filter_length_still_fatal(scenario, monkeypatch):
    s = scenario
    s.state["filter_failure"] = True
    run_method(s, "hipporag2", monkeypatch)
    m = dense.read_json(s.output / "manifest.json")
    assert m["status"] == "failed"
    r = dense.read_json(next(s.output.glob("question-*.json")))
    assert r["fatal"] is True and r["failure_scope"] == "execution"
    assert len(s.state["posts"]) == 8
