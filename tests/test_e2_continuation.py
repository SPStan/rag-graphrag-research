"""Existing shared runner on60 synthetic cases; no actual HTTP/model clients."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
        queries = [{"id": f"q{i}", "question": f"Which city {i}?"} for i in range(13)]
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
            "question_ids": [q["id"] for q in queries[:10]],
            "labels_sha256_evaluator_only": dense.sha256_file(raw / "labels.json"),
            "queries_sha256": runner.digest(queries[:10]),
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

    # Derived tracking keeps the parent length and all statuses, without turning
    # a raw partial into a completed answer or double-counting filter usage.
    payload = e2.tracking_payload(plan, s.output, "musique", "dense")
    assert len(payload["rows"]) == 10
    source_failure = next(r for r in payload["rows"] if r["question_id"] == "q2")
    assert source_failure["status"] == "attempted_failed"
    assert source_failure["done_reason"] == "length"
    assert not source_failure["answer"]
    assert source_failure["raw_answer"] is not None
    assert s.parent_bytes == {
        p.name: p.read_bytes() for p in s.parent.iterdir() if p.is_file()
    }
    for aggregate in report["rows"]:
        operations = aggregate["usage_by_operation"]
        assert operations["reader"]["calls"] == 10
        assert operations["query_embedding"]["calls"] == 10
        if aggregate["method"] == "hipporag2":
            assert operations["filter"]["calls"] == 10
        for field in known:
            assert sum(
                op["known_subtotal"].get(field, 0) for op in operations.values()
            ) == sum(
                model["known_subtotal"].get(field, 0)
                for model in aggregate["logical_usage_by_model"].values()
            )
    assert (s.root / "report.md").read_text(encoding="utf-8").count("| musique |") == 3

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


@pytest.mark.parametrize(
    "fault", [None, "length", "unknown", "transport", "malformed", "cycle"]
)
def test_answer_only_diagnostic_existing_runner(scenario, monkeypatch, fault):
    s = scenario
    for method in e2.METHODS:
        run_method(s, method, monkeypatch)
    # Neither labels nor scoring/retrieval may participate in the new diagnostic.
    original_read = dense.read_json

    def no_labels(path):
        assert str(path).split("/")[-1] != "labels.json"
        assert not str(path).endswith("labels.json")
        return original_read(path)

    monkeypatch.setattr(dense, "read_json", no_labels)
    monkeypatch.setattr(e2, "summary", lambda *a: pytest.fail("no gold evaluator"))
    probe_path = s.root / "reader-probe.json"
    with patch(
        "sys.argv",
        [
            "run_dense_target",
            "--shared-plan",
            str(probe_path),
            "--reader-probe-from",
            str(s.child_plan),
            "--parent-output-dir",
            str(s.output),
        ],
    ):
        runner.main()
    probe = dense.read_json(probe_path)
    assert probe["max_posts"] == probe["max_llm_posts"] == 12
    assert probe["max_embedding_posts"] == probe["filter_calls"] == 0
    assert (
        len({(c["dataset"], c["method"], c["question_id"]) for c in probe["cases"]})
        == 12
    )
    for c in probe["cases"]:
        assert c["payload"]["max_tokens"] == 512
        assert not any("Thought:" in m["content"] for m in c["payload"]["messages"])
        assert c["payload"]["messages"][2]["content"] == "Answer: 1862."
    blocked_calls = e2.Calls(s.root / "blocked-probe-calls", probe, run_id="blocked")
    for forbidden in ("query_embedding", "filter"):
        case = probe["cases"][0]
        with pytest.raises(ValueError, match="only_frozen_reader"):
            blocked_calls.call(
                case["payload"],
                method=case["method"],
                dataset=case["dataset"],
                qid=case["question_id"],
                operation=forbidden,
            )
    with pytest.raises(ValueError, match="approval_required"):
        e2.execute_reader_probe(
            probe_path, s.root / "not-approved", approved_sha="wrong", config=s.config
        )
    assert not (s.root / "not-approved").exists()
    for key, value in (("max_posts", 13), ("max_combined_tokens", 1)):
        changed = {**probe, key: value}
        with pytest.raises(ValueError, match="contract_changed"):
            e2.verify_reader_probe(changed)
    posts = len(s.state["posts"])
    s.state["reader_outcomes"] = [fault] if fault in ("length", "malformed") else []
    s.state["fault"] = fault if fault in ("unknown", "transport") else None
    if fault == "cycle":
        session_class = runner.requests.Session
        original_post = session_class.post

        def cycle_post(self, *args, **kwargs):
            response = original_post(self, *args, **kwargs)
            body = response.json()
            body["choices"][0]["message"]["content"] = "Answer: " + "Paris " * 32
            response.json = lambda: body
            return response

        monkeypatch.setattr(session_class, "post", cycle_post)
    monkeypatch.setattr(runner.api, "settings", lambda env: s.config)
    output = s.root / "reader-diagnostic"
    with patch(
        "sys.argv",
        [
            "run_dense_target",
            "--shared-plan",
            str(probe_path),
            "--execute",
            "--output-dir",
            str(output),
            "--approved-plan-sha256",
            dense.sha256_file(probe_path),
        ],
    ):
        runner.main()
    result = dense.read_json(output / "manifest.json")
    assert result["status"] == (
        "responses_pending_source_audit" if fault is None else "failed"
    )
    delta = s.state["posts"][posts:]
    assert len(delta) == (12 if fault is None else 1)
    assert all(operation == "reader" for operation, _ in delta)
    assert result["token_accounting"]["summary"]["attempts"] == len(delta)
    with pytest.raises((FileExistsError, ValueError)):
        e2.execute_reader_probe(
            probe_path,
            s.root / "other-output",
            approved_sha=dense.sha256_file(probe_path),
            config=s.config,
        )
    assert len(s.state["posts"]) == posts + len(delta)
    altered = copy.deepcopy(probe)
    altered["cases"][0]["payload"]["max_tokens"] = 1024
    with pytest.raises(ValueError, match="contract_changed"):
        e2.verify_reader_probe(altered)


@pytest.fixture
def pilot_scenario(scenario, monkeypatch):
    from scripts import e2_pilot as pilot

    s = scenario
    for method in e2.METHODS:
        run_method(s, method, monkeypatch)
    diagnostic_plan = s.root / "diagnostic-plan.json"
    runner.dense.write_json_atomic(
        diagnostic_plan, e2.prepare_reader_probe(s.child_plan, s.output)
    )
    diagnostic = s.root / "diagnostic"
    e2.execute_reader_probe(
        diagnostic_plan,
        diagnostic,
        approved_sha=dense.sha256_file(diagnostic_plan),
        config=s.config,
    )
    # Same immutable synthetic corpus/labels, now include an unseen query q10.
    # Real production prepare separately enforces200published tuning IDs.
    base = e2.prepare(None, None)
    for data in base["datasets"].values():
        data["question_ids"] = [f"q{i}" for i in range(11)]
    monkeypatch.setattr(e2, "prepare", lambda *a, **kw: copy.deepcopy(base))
    frozen = pilot.complete_plan(
        base, s.child_plan, s.output, diagnostic_plan, diagnostic
    )
    s.pilot_plan = s.root / "pilot-plan.json"
    dense.write_json_atomic(s.pilot_plan, frozen)
    s.pilot_output = s.root / "pilot"
    s.plan = frozen
    s.source_bytes = {
        Path(name): Path(name).read_bytes() for name in frozen["pilot_reuse"]["files"]
    }
    return s


def test_pilot_existing_runner_reuse_common_reader_cost_and_latency(
    pilot_scenario, monkeypatch
):
    from scripts import e2_pilot as pilot

    s = pilot_scenario
    assert (
        s.plan["reader_calls"] == 54
        and s.plan["filter_calls"] == 2
        and s.plan["max_embedding_posts"] == 6
        and s.plan["max_posts"] == 62
    )
    assert (
        len(s.plan["pilot_reuse"]["contexts"]) == 60
        and len(s.plan["pilot_reuse"]["readers"]) == 12
    )
    before = len(s.state["posts"])
    for field, value in (
        ("max_posts", 63),
        ("max_combined_tokens", 1),
        ("reader_options", {**runner.OPTIONS, "max_tokens": 1024}),
    ):
        altered = {**s.plan, field: value}
        with pytest.raises(ValueError, match="plan_or_reuse_changed"):
            pilot.verify(altered)
    query_file = s.root / "data/processed/musique/queries.json"
    original_queries = query_file.read_bytes()
    changed_queries = dense.read_json(query_file)
    changed_queries[0]["question"] = "Different question same ID"
    dense.write_json_atomic(query_file, changed_queries)
    with pytest.raises(ValueError, match="question_text_changed"):
        pilot.verify(s.plan)
    query_file.write_bytes(original_queries)
    assert len(s.state["posts"]) == before
    payload = e2.configured_reader_payload(
        s.plan,
        "Where?",
        {
            "passages": [{"title": "T", "text": "Source", "gold": "SECRET"}],
            "supporting_ids": ["SECRET"],
        },
    )
    assert "SECRET" not in json.dumps(payload)
    assert payload["messages"][0]["content"] == e2.ANSWER_ONLY_SYSTEM
    assert payload["max_tokens"] == 512
    blocked = e2.Calls(s.root / "blocked-pilot", s.plan, run_id="blocked")
    frozen_case = next(iter(s.plan["pilot_reuse"]["readers"]))
    context = dense.read_json(
        Path(s.plan["pilot_reuse"]["contexts"][frozen_case]["path"])
    )
    for operation in ("reader", "filter", "query_embedding"):
        with pytest.raises(ValueError, match="must_not_POST"):
            blocked.call(
                payload,
                method=context["method"],
                dataset=context["dataset"],
                qid=context["question_id"],
                operation=operation,
            )
    with pytest.raises(ValueError, match="outside_frozen_IDs"):
        blocked.call(
            payload,
            method="dense",
            dataset="musique",
            qid="holdout-forbidden",
            operation="reader",
        )
    old_payload = e2.reader_payload("Which city 10?", {"passages": []})
    with pytest.raises(ValueError, match="actual_reader_template_changed"):
        blocked.call(
            old_payload,
            method="dense",
            dataset="musique",
            qid="q10",
            operation="reader",
        )
    assert len(s.state["posts"]) == before
    # One known length is measured as0, but does not stop the next case.
    s.state["reader_outcomes"] = ["length"]
    original = runner.requests.Session.post

    def observed_post(self, url, *, json, **kwargs):
        response = original(self, url, json=json, **kwargs)
        if (
            not url.endswith("/api/embed")
            and json["messages"][-1]["content"] != "filter-marker"
        ):
            assert json["messages"][0]["content"] == e2.ANSWER_ONLY_SYSTEM
            assert json["messages"][2]["content"] == "Answer: 1862."
            assert all("Thought:" not in m["content"] for m in json["messages"])
            assert all(json[k] == v for k, v in runner.OPTIONS.items())
            # Technically valid but semantically wrong must not stop execution.
            if json["messages"][-1]["content"].endswith("Question: Which city 10?"):
                body = response.json()
                body["choices"][0]["message"]["content"] = "Answer: London"
                response.json = lambda: body
        return response

    monkeypatch.setattr(runner.requests.Session, "post", observed_post)

    def execute(method):
        with patch(
            "sys.argv",
            [
                "run_dense_target",
                "--shared-plan",
                str(s.pilot_plan),
                "--execute",
                "--shared-method",
                method,
                "--output-dir",
                str(s.pilot_output),
                "--approved-plan-sha256",
                dense.sha256_file(s.pilot_plan),
            ],
        ):
            runner.main()

    execute("dense")
    partial = e2.summary(s.plan, s.pilot_output)
    assert not partial["comparison_complete"] and partial["paired_comparisons"] == []
    assert any(
        r["status"] == "not_attempted" and r["metrics"]["em"] is None
        for r in partial["question_results"]
    )
    execute("hipporag2")
    execute("raptor")
    manifest = dense.read_json(s.pilot_output / "manifest.json")
    assert manifest["status"] == "completed" and len(manifest["results"]) == 66
    assert len(s.state["posts"]) - before == 62
    report = e2.summary(s.plan, s.pilot_output)
    assert report["comparison_complete"]
    assert (
        sum(r["status"] == "attempted_failed" for r in report["question_results"]) == 1
    )
    assert (
        sum(
            r.get("latency_mode") == "fresh_end_to_end"
            for r in report["question_results"]
        )
        == 6
    )
    assert (
        sum(
            r.get("latency_mode") == "cached_context_cached_reader"
            for r in report["question_results"]
        )
        == 12
    )
    assert sum(r["fresh_e2e_cases"] for r in report["rows"]) == 6
    assert sum(r["fresh_reader_cases"] for r in report["rows"]) == 54
    assert all(r["mean_attempted_seconds"] is None for r in report["rows"])
    assert len(report["paired_comparisons"]) == 12
    assert report["pilot_accounting"]["new_physical"]["attempts"] == 62
    assert report["pilot_accounting"]["development_physical"]["known_subtotal"] == {
        "llm_input_tokens": 920,
        "llm_output_tokens": 368,
        "embedding_input_tokens": 60,
    }
    assert report["pilot_accounting"]["reused_source_known"] == {
        "llm_input_tokens": 320,
        "llm_output_tokens": 128,
        "embedding_input_tokens": 60,
    }
    # All compatible diagnostic answers, regardless of any external review, reused.
    reader_ops = [
        o
        for r in report["question_results"]
        for o in r.get("operations", [])
        if o["operation"] == "reader" and o.get("reused")
    ]
    assert len(reader_ops) == 12
    count = len(s.state["posts"])
    journal = (s.pilot_output / "usage.jsonl").read_bytes()
    for method in e2.METHODS:
        execute(method)
    assert (
        len(s.state["posts"]) == count
        and (s.pilot_output / "usage.jsonl").read_bytes() == journal
    )
    assert all(path.read_bytes() == data for path, data in s.source_bytes.items())
    with pytest.raises(ValueError, match="other_directory"):
        e2.execute(
            s.pilot_plan,
            s.root / "other-pilot",
            "dense",
            approved_sha=dense.sha256_file(s.pilot_plan),
            config=s.config,
        )
    safe = e2.write_report(s.pilot_plan, s.pilot_output, s.root / "pilot-report")
    assert safe["kind"] == "e2_pilot200" and safe["model_posts"] == 62
    assert (
        safe["pilot_accounting"]["reused_source_known"]["embedding_input_tokens"] == 60
    )
    # Pure report regeneration never calls the model transport.
    with patch.object(
        runner.requests.Session, "post", side_effect=AssertionError("HTTP forbidden")
    ):
        with patch(
            "sys.argv",
            [
                "run_dense_target",
                "--shared-plan",
                str(s.pilot_plan),
                "--output-dir",
                str(s.pilot_output),
                "--summarize-shared",
                str(s.root / "pilot-report"),
            ],
        ):
            runner.main()


def test_pilot_unknown_and_pin_mismatch_stop_before_reuse_or_retry(
    pilot_scenario, monkeypatch
):
    from scripts import e2_pilot as pilot

    s = pilot_scenario
    before = len(s.state["posts"])
    path = next(iter(s.source_bytes))
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="pin_changed"):
        pilot.verify(s.plan)
    assert len(s.state["posts"]) == before
    path.write_bytes(original)
    s.state["fault"] = "unknown"
    result = e2.execute(
        s.pilot_plan,
        s.pilot_output,
        "dense",
        approved_sha=dense.sha256_file(s.pilot_plan),
        config=s.config,
    )
    assert result["status"] == "failed" and len(s.state["posts"]) == before + 1
    accounting = result["token_accounting"]["summary"]
    assert not accounting["complete"]
    with pytest.raises(ValueError, match="failed_or_changed"):
        e2.execute(
            s.pilot_plan,
            s.pilot_output,
            "dense",
            approved_sha=dense.sha256_file(s.pilot_plan),
            config=s.config,
        )
    assert len(s.state["posts"]) == before + 1
    report = e2.summary(s.plan, s.pilot_output)
    assert not report["comparison_complete"] and report["paired_comparisons"] == []
    assert report["pilot_accounting"]["used_source_operations"] < 92
    assert sum(report["pilot_accounting"]["reused_source_known"].values()) < sum(
        report["pilot_accounting"]["available_source_reuse_known"].values()
    )


@pytest.mark.parametrize("dataset", runner.DATASETS)
def test_pilot_published_200_order_unique_and_tuning_only(dataset):
    s500 = dense.read_json(e2.ROOT / f"data/ids/{dataset}_s500.json")
    split = dense.read_json(e2.ROOT / f"data/ids/{dataset}_comparison_split.json")
    ids = s500["views"]["pilot200"]
    assert len(ids) == len(set(ids)) == 200
    assert ids == s500["question_ids"][:200] == split["pilot200_ids"]
    assert set(ids) <= set(split["signal_tuning_ids"])
    assert not set(ids) & set(
        split["signal_check_ids"] + split["legacy_holdout_reserved_ids"]
    )


@pytest.fixture
def bounded_pilot_child(pilot_scenario, monkeypatch):
    from scripts import e2_pilot as pilot

    s = pilot_scenario
    # Tiny synthetic source contexts have less reservation headroom than the
    # real1200-case pilot. Fund this fixture BEFORE its first physical attempt.
    original_verify = pilot.verify
    s.plan["max_combined_tokens"] += 1_000_000
    dense.write_json_atomic(s.pilot_plan, s.plan)

    def funded_synthetic_verify(plan):
        base = copy.deepcopy(plan)
        base["max_combined_tokens"] -= 1_000_000
        return original_verify(base)

    monkeypatch.setattr(pilot, "verify", funded_synthetic_verify)
    native = e2.indexes.retrieve_ready_e1

    def long_context(loaded, question, vector, **kw):
        r = native(loaded, question, vector, **kw)
        if (
            loaded["manifest_sha256"] == "musique-raptor"
            and question == "Which city 10?"
        ):
            r["passages"][0]["text"] = "long original text " * 2100
        return r

    monkeypatch.setattr(e2.indexes, "retrieve_ready_e1", long_context)
    s.child_plan, s.output = s.pilot_plan, s.pilot_output
    for method in e2.METHODS:
        run_method(s, method, monkeypatch)
    m = dense.read_json(s.output / "manifest.json")
    assert m["status"] == "failed"
    assert len(m["results"]) == 55
    s.terminal_bytes = {p: p.read_bytes() for p in s.output.iterdir() if p.is_file()}
    monkeypatch.setattr(pilot, "validate_original_pilot", pilot.verify)
    bounds = {"synthetic": {"synthetic_top5_message_bytes": 50000}}
    monkeypatch.setattr(pilot, "input_size_bounds", lambda p: bounds)
    proof = s.root / "bound-proof.json"
    dense.write_json_atomic(
        proof,
        {
            "message_utf8_bytes_limit": 65536,
            "size_bounds": bounds,
            "conservative_input_plus_output_bound": 68096,
            "reported_context_window": 262144,
            "tokenizer_files": {},
        },
    )
    s.continuation_plan = s.root / "pilot-child-plan.json"
    with patch(
        "sys.argv",
        [
            "run_dense_target",
            "--shared-plan",
            str(s.continuation_plan),
            "--continue-pilot-plan",
            str(s.pilot_plan),
            "--parent-output-dir",
            str(s.pilot_output),
            "--pilot-bound-proof",
            str(proof),
        ],
    ):
        runner.main()
    s.continuation = dense.read_json(s.continuation_plan)
    s.continuation_output = s.root / "pilot-child"
    return s


def test_bounded_pilot_child_existing_cli_reuses_only_missing_stages(
    bounded_pilot_child, monkeypatch
):
    from scripts import e2_pilot as pilot

    s = bounded_pilot_child
    plan = s.continuation
    assert len(plan["parent_run"]["cases"]) == 54
    assert len(plan["remaining_cases"]) == 12
    assert plan["reader_calls"] == 10
    assert plan["max_embedding_posts"] == 1 and plan["filter_calls"] == 0
    assert plan["max_posts"] == 11
    assert plan["max_combined_tokens"] <= plan["original_remaining_tokens"]
    before = len(s.state["posts"])
    s.child_plan, s.output = s.continuation_plan, s.continuation_output
    run_method(s, "raptor", monkeypatch)
    new = s.state["posts"][before:]
    assert len(new) == 11
    assert sum(op == "reader" for op, _ in new) == 10
    assert sum(op == "embedding" for op, _ in new) == 1
    assert any(
        "long original text " * 2100 in p["messages"][-1]["content"]
        for op, p in new
        if op == "reader"
    )
    assert dense.read_json(s.output / "manifest.json")["status"] == "completed"
    report = e2.summary(plan, s.output)
    assert report["comparison_complete"]
    cases = report["question_results"]
    assert (
        len(cases) == 66
        and len({(c["method"], c["dataset"], c["question_id"]) for c in cases}) == 66
    )
    assert all(c["status"] == "completed" for c in cases)
    assert report["physical_query_accounting"]["summary"]["attempts"] == 62
    assert (
        report["pilot_accounting"]["lineage_stage_reuse_known"][
            "embedding_input_tokens"
        ]
        == 1
    )
    assert (
        report["pilot_accounting"]["reused_source_known"]
        == s.plan["pilot_reuse"]["reused_source_known"]
    )
    for path, content in s.terminal_bytes.items():
        assert path.read_bytes() == content
    for path, content in s.source_bytes.items():
        assert path.read_bytes() == content
    paid = len(s.state["posts"])
    run_method(s, "raptor", monkeypatch)
    assert len(s.state["posts"]) == paid
    for key, value in (
        ("message_utf8_bytes_limit", 70000),
        ("max_posts", 12),
        ("reader_options", {"max_tokens": 1024}),
    ):
        altered = {**plan, key: value}
        with pytest.raises(ValueError, match="continuation_plan_changed"):
            pilot.verify_continuation(altered)
    changed = copy.deepcopy(plan)
    changed["code_sha256"]["scripts/e2_pilot.py"] = "bad"
    with pytest.raises(ValueError, match="continuation_plan_changed"):
        pilot.verify_continuation(changed)


def test_new_byte_gate_keeps_full_payload_and_rejects_before_reader(pilot_scenario):
    s = pilot_scenario
    retrieval = {"passages": [{"title": "T", "text": "unchanged content " * 2100}]}
    with pytest.raises(ValueError, match="context_overflow"):
        e2.configured_reader_payload(s.plan, "Which?", retrieval)
    child = {**s.plan, "message_utf8_bytes_limit": 65536}
    payload = e2.configured_reader_payload(child, "Which?", retrieval)
    assert retrieval["passages"][0]["text"] in payload["messages"][-1]["content"]
    assert len(json.dumps(payload["messages"]).encode()) > 32000
    assert payload == e2.answer_only_payload("Which?", retrieval, message_limit=65536)
    with pytest.raises(ValueError, match="context_overflow"):
        e2.configured_reader_payload(
            child, "Which?", {"passages": [{"title": "T", "text": "z" * 66000}]}
        )


def test_pilot_child_transport_completed_filter_and_budget_gates(bounded_pilot_child):
    s = bounded_pilot_child
    plan = copy.deepcopy(s.continuation)
    calls = e2.Calls(s.root / "transport-gates", plan, run_id="gate-only")
    inherited = next(iter(plan["parent_run"]["cases"].values()))
    payload = e2.answer_only_payload("Which?", {"passages": []})
    with pytest.raises(ValueError, match="no_new_completed_case_or_filter"):
        calls.call(
            payload,
            method=inherited["method"],
            dataset=inherited["dataset"],
            qid=inherited["question_id"],
            operation="reader",
        )
    with pytest.raises(ValueError, match="no_new_completed_case_or_filter"):
        calls.call(
            payload, method="raptor", dataset="hotpotqa", qid="q10", operation="filter"
        )
    plan["max_combined_tokens"] = 1
    # Real checked_post path rejects reservation before synthetic session.post.
    before = len(s.state["posts"])
    with pytest.raises(ValueError, match="budget"):
        calls.call(
            payload,
            method="raptor",
            dataset="hotpotqa",
            qid="q10",
            operation="reader",
            session=runner.requests.Session(),
            url=s.config["base_url"] + "/chat/completions",
        )
    assert len(s.state["posts"]) == before


def test_pilot_continuation_rejects_active_parent_and_changed_pin(bounded_pilot_child):
    from scripts import e2_pilot as pilot

    s = bounded_pilot_child
    lock = s.pilot_output / "running.lock"
    lock.write_text("live", encoding="utf-8")
    with pytest.raises(ValueError, match="parent_not_terminal_known"):
        pilot.verify_continuation(s.continuation)
    lock.unlink()
    claim = next(
        p
        for p in s.continuation["parent_run"]["files"]
        if p.endswith("claim.json")
        and dense.read_json(Path(p)).get("directory") == str(s.pilot_output)
    )
    original = Path(claim).read_bytes()
    dense.write_json_atomic(Path(claim), {"directory": "other-output"})
    with pytest.raises(ValueError, match="parent_claim_changed"):
        pilot.verify_continuation(s.continuation)
    Path(claim).write_bytes(original)


@pytest.fixture
def sealed_transport_scenario(pilot_scenario, monkeypatch):
    from scripts import e2_pilot as pilot

    s = pilot_scenario
    previous = s.plan["pilot_reuse"]
    base = e2.prepare(None, None)
    for data in base["datasets"].values():
        data["question_ids"] = [f"q{i}" for i in range(13)]
    monkeypatch.setattr(e2, "prepare", lambda *a, **kw: copy.deepcopy(base))
    s.plan = pilot.complete_plan(
        base,
        previous["source_plan"],
        previous["source_directory"],
        previous["diagnostic_plan"],
        previous["diagnostic_directory"],
    )
    original_verify = pilot.verify
    s.plan["max_combined_tokens"] += 1_000_000
    dense.write_json_atomic(s.pilot_plan, s.plan)

    def verify_funded(p):
        value = copy.deepcopy(p)
        value["max_combined_tokens"] -= 1_000_000
        return original_verify(value)

    monkeypatch.setattr(pilot, "verify", verify_funded)
    native = e2.indexes.retrieve_ready_e1

    def long_context(loaded, question, vector, **kwargs):
        result = native(loaded, question, vector, **kwargs)
        if (
            loaded["manifest_sha256"] == "musique-raptor"
            and question == "Which city 10?"
        ):
            result["passages"][0]["text"] = "full source " * 3000
        return result

    monkeypatch.setattr(e2.indexes, "retrieve_ready_e1", long_context)
    s.child_plan, s.output = s.pilot_plan, s.pilot_output
    for method in e2.METHODS:
        run_method(s, method, monkeypatch)
    assert dense.read_json(s.pilot_output / "manifest.json")["status"] == "failed"
    monkeypatch.setattr(pilot, "validate_original_pilot", pilot.verify)
    bounds = {"synthetic": {"synthetic_top5_message_bytes": 50000}}
    monkeypatch.setattr(pilot, "input_size_bounds", lambda p: bounds)
    proof = s.root / "sealed-bound.json"
    dense.write_json_atomic(
        proof,
        {
            "message_utf8_bytes_limit": 65536,
            "size_bounds": bounds,
            "conservative_input_plus_output_bound": 68096,
            "reported_context_window": 262144,
            "tokenizer_files": {},
        },
    )
    issued = s.root / "issued-plan.json"
    dense.write_json_atomic(
        issued, pilot.prepare_input_continuation(s.pilot_plan, s.pilot_output, proof)
    )
    issued_output = s.root / "issued-run"
    original_post = runner.requests.Session.post
    fault = {"sent": False}

    def remote_disconnect(self, url, *, json, **kwargs):
        if (
            not fault["sent"]
            and not url.endswith("/api/embed")
            and json["messages"][-1]["content"].endswith("Question: Which city 11?")
        ):
            fault["sent"] = True
            s.state["posts"].append(("reader", copy.deepcopy(json)))
            raise runner.requests.ConnectionError(
                "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
            )
        return original_post(self, url, json=json, **kwargs)

    monkeypatch.setattr(runner.requests.Session, "post", remote_disconnect)
    s.child_plan, s.output = issued, issued_output
    run_method(s, "raptor", monkeypatch)
    manifest = dense.read_json(issued_output / "manifest.json")
    assert manifest["status"] == "failed" and fault["sent"]
    # Synthetic source has no real historical Git3914d70; snapshot and payload
    # validation remain real, only that deployment-runtime check is substituted.
    monkeypatch.setattr(pilot, "validate_transport_parent", lambda p: None)
    s.issued, s.issued_output = issued, issued_output
    s.proof = proof
    s.sealed_plan_path = s.root / "sealed-plan.json"
    with patch(
        "sys.argv",
        [
            "run_dense_target",
            "--shared-plan",
            str(s.sealed_plan_path),
            "--continue-pilot-plan",
            str(issued),
            "--parent-output-dir",
            str(issued_output),
            "--pilot-bound-proof",
            str(proof),
        ],
    ):
        runner.main()
    s.sealed = dense.read_json(s.sealed_plan_path)
    s.sealed_output = s.root / "sealed-run"
    s.frozen_inputs = {
        p: p.read_bytes()
        for directory in (s.pilot_output, issued_output)
        for p in directory.iterdir()
        if p.is_file()
    }
    return s


def test_unattempted_cli_seals_unknown_never_retries_and_merges_three_runs(
    sealed_transport_scenario, monkeypatch
):
    from scripts import e2_pilot as pilot

    s = sealed_transport_scenario
    plan = s.sealed
    assert len(plan["parent_run"]["cases"]) == 64
    assert len(plan["remaining_cases"]) == 14
    assert plan["reader_calls"] == 12 and plan["max_embedding_posts"] == 4
    assert plan["max_posts"] == 16
    reserve = plan["sealed_unknown"][0]["reservation_tokens"]
    source = dense.read_json(s.issued)
    known = sum(plan["parent_run"]["summary"]["known_subtotal"].values())
    assert (
        plan["original_remaining_tokens"]
        == source["max_combined_tokens"] - known - reserve
    )
    assert plan["max_combined_tokens"] <= plan["original_remaining_tokens"]
    before = len(s.state["posts"])
    s.child_plan, s.output = s.sealed_plan_path, s.sealed_output
    run_method(s, "raptor", monkeypatch)
    assert len(s.state["posts"]) - before == 16
    assert not any(
        op == "reader"
        and payload["messages"][-1]["content"].endswith("Question: Which city 11?")
        and "full source" in payload["messages"][-1]["content"]
        for op, payload in s.state["posts"][before:]
    )
    report = e2.summary(plan, s.output)
    assert report["comparison_complete"] and len(report["question_results"]) == 78
    assert (
        len(
            {
                (r["dataset"], r["method"], r["question_id"])
                for r in report["question_results"]
            }
        )
        == 78
    )
    assert (
        sum(r["status"] == "attempted_failed" for r in report["question_results"]) == 1
    )
    assert (
        sum(
            not p["summary"]["complete"]
            for p in report["physical_query_accounting"]["lineage"]
        )
        == 1
    )
    assert not report["physical_query_accounting"]["summary"]["complete"]
    assert (
        report["physical_query_accounting"]["summary"]["attempts"]
        == s.plan["max_posts"]
    )
    unknown_case = next(
        r
        for r in report["question_results"]
        if e2.case_key(r["dataset"], r["method"], r["question_id"])
        == plan["sealed_unknown"][0]["case_key"]
    )
    assert unknown_case["metrics"]["em"] == 0 and unknown_case["metrics"]["f1"] == 0
    for path, content in s.frozen_inputs.items():
        assert path.read_bytes() == content
    safe = e2.write_report(s.sealed_plan_path, s.output, s.root / "sealed-report")
    assert safe["new_unknown_attempts"] == 0 and safe["lineage_unknown_attempts"] == 1
    assert not safe["query_cost_complete"] and safe["comparison_complete"]
    views = e2.tracking_payload(plan, s.output, "musique", "raptor")
    failed = next(r for r in views["rows"] if r["status"] == "attempted_failed")
    assert failed["prompt_tokens"] is None and failed["completion_tokens"] is None
    for key in ("max_combined_tokens", "max_posts"):
        bad = {**plan, key: plan[key] + 1}
        with pytest.raises(ValueError, match="continuation_plan_changed"):
            pilot.verify_continuation(bad)
    bad = copy.deepcopy(plan)
    bad["sealed_unknown"][0]["reservation_tokens"] = 0
    with pytest.raises(ValueError, match="continuation_plan_changed"):
        pilot.verify_continuation(bad)


def test_sealed_unknown_transport_gate_and_changed_checkpoint(
    sealed_transport_scenario,
):
    from scripts import e2_pilot as pilot

    s = sealed_transport_scenario
    plan = s.sealed
    key = plan["sealed_unknown"][0]["case_key"]
    case = dense.read_json(Path(plan["parent_run"]["cases"][key]["path"]))
    calls = e2.Calls(s.root / "sealed-transport", plan, run_id="no-retry")
    payload = e2.configured_reader_payload(plan, case["question"], case["retrieval"])
    before = len(s.state["posts"])
    with pytest.raises(ValueError, match="no_new_completed_case_or_filter"):
        calls.call(
            payload,
            method=case["method"],
            dataset=case["dataset"],
            qid=case["question_id"],
            operation="reader",
            session=runner.requests.Session(),
            url=s.config["base_url"] + "/chat/completions",
        )
    assert len(s.state["posts"]) == before
    cp = s.issued_output / (plan["sealed_unknown"][0]["object_id"] + ".json")
    original = cp.read_bytes()
    dense.write_json_atomic(
        cp, {"status": "completed", "key": plan["sealed_unknown"][0]["object_id"]}
    )
    with pytest.raises(ValueError, match="unknown_reader_identity"):
        pilot.prepare_unattempted(s.issued, s.issued_output, s.proof)
    cp.write_bytes(original)


def test_tracking_preserves_unknown_and_verifies_all_known_usage():
    from scripts.track_dense import verify_langfuse_trace

    payload = {
        "run_id": "mixed",
        "rows": [
            {"prompt_tokens": 10, "completion_tokens": 3},
            {"prompt_tokens": None, "completion_tokens": None},
        ],
        "questions": [{"retrieved_passages": [{"text": "saved"}]}] * 2,
    }
    observations = [
        SimpleNamespace(
            name="dense-rag-run", metadata={"run_id": "mixed"}, input={}, output={}
        )
    ]
    for usage in ({"input": 10, "output": 3}, {}):
        observations.extend(
            [
                SimpleNamespace(name="question"),
                SimpleNamespace(name="query-embedding"),
                SimpleNamespace(
                    name="retrieval", output={"documents": [{"text": "saved"}]}
                ),
                SimpleNamespace(
                    name="generation", input={}, output={}, usage_details=usage
                ),
            ]
        )
    result = verify_langfuse_trace(observations, payload)
    assert result["generation_usage"] == {"input": 10, "output": 3}
    assert result["generation_usage_unknown"] == 1
    observations[-1].usage_details = {"input": 0, "output": 0}
    with pytest.raises(RuntimeError, match="converted to zero"):
        verify_langfuse_trace(observations, payload)
    observations[-1].usage_details = {}
    observations[4].usage_details["input"] = 11
    with pytest.raises(RuntimeError, match="does not match"):
        verify_langfuse_trace(observations, payload)
