"""Offline tree integrity, accounting and opt-in official RAPTOR checks."""

import copy
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from scripts import run_raptor_smoke as raptor
from scripts.token_accounting import Journal


def tree_payload():
    return {
        "schema_version": 1,
        "dimension": 2,
        "implementation_commit": raptor.SOURCE_COMMIT,
        "nodes": [
            {
                "index": 0,
                "text": "alpha",
                "children": [],
                "embeddings": {"BGE": [1, 0]},
            },
            {"index": 1, "text": "beta", "children": [], "embeddings": {"BGE": [0, 1]}},
            {
                "index": 2,
                "text": "summary",
                "children": [0, 1],
                "embeddings": {"BGE": [1, 1]},
            },
            {
                "index": 3,
                "text": "overlap",
                "children": [1],
                "embeddings": {"BGE": [1, 1]},
            },
        ],
        "leaf_passage_ids": {"0": "p0", "1": "p1"},
        "layers": {"0": [0, 1], "1": [2, 3]},
        "roots": [2, 3],
        "num_layers": 1,
    }


def test_overlapping_summary_ancestry_is_union():
    ancestry = raptor.validate_tree(tree_payload())
    assert ancestry[2] == {"p0", "p1"}
    assert ancestry[3] == {"p1"}
    assert ancestry[2] | ancestry[3] == {"p0", "p1"}


@pytest.mark.parametrize(
    "defect", ["cycle", "missing", "nonfinite", "duplicate", "layers", "leaf_children"]
)
def test_tree_corruption_is_rejected(defect):
    payload = tree_payload()
    if defect == "cycle":
        payload["nodes"][2]["children"] = [3]
        payload["nodes"][3]["children"] = [2]
    elif defect == "missing":
        payload["nodes"][2]["children"] = [9]
    elif defect == "nonfinite":
        payload["nodes"][2]["embeddings"]["BGE"] = [float("nan"), 1]
    elif defect == "duplicate":
        payload["nodes"].append(copy.deepcopy(payload["nodes"][0]))
    elif defect == "layers":
        payload["layers"]["1"] = [2]
    else:
        payload["nodes"][0]["children"] = [1]
    with pytest.raises(ValueError):
        raptor.validate_tree(payload)


def test_reload_has_no_model_dependency():
    payload = tree_payload()

    def node(text, index, children, embeddings):
        return SimpleNamespace(
            text=text, index=index, children=children, embeddings=embeddings
        )

    sdk = {"node": node, "tree": lambda *args: args}
    restored = raptor.restore_tree(payload, sdk)
    assert restored[0][2].children == {0, 1}
    assert restored[0][0].embeddings == {"BGE": [1, 0]}
    assert restored[3] == 1


def test_summary_and_unknown_usage_preserve_known_cost(tmp_path, monkeypatch):
    journal = Journal(
        tmp_path / "tokens.jsonl", run_id="r", method="raptor", dataset="musique"
    )
    config = {
        "base_url": "https://example.invalid/v1",
        "ollama_url": "http://127.0.0.1:11434",
        "model": "qwen",
        "embedding_model": "bge",
        "key": "test",
    }
    transport = raptor.Transport(
        config, journal, tmp_path, requests.Session(), requests.Session()
    )
    responses = iter(
        [
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"content": "summary"}}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            },
            {"choices": [{"finish_reason": "stop", "message": {"content": "unknown"}}]},
        ]
    )

    class Response:
        status_code = 200

        def json(self):
            return next(responses)

        def raise_for_status(self):
            pass

    monkeypatch.setattr(transport.remote, "post", lambda *args, **kwargs: Response())
    assert transport.summarize("context", 512) == "summary"
    with pytest.raises(ValueError, match="missing_usage_stop"):
        transport.summarize("another", 512)
    reference = journal.reference()
    assert reference["summary"]["attempts"] == 2
    assert sum(reference["summary"]["known_subtotal"].values()) == 12
    assert not reference["summary"]["complete"]
    assert len(list(tmp_path.glob("*.response.json"))) == 2


def test_transport_retries_and_request_limit_stop_before_send(tmp_path, monkeypatch):
    journal = Journal(
        tmp_path / "tokens.jsonl", run_id="r", method="raptor", dataset="musique"
    )
    config = {"base_url": "https://example.invalid/v1", "model": "qwen", "key": "test"}
    remote = requests.Session()
    remote.mount("https://", requests.adapters.HTTPAdapter(max_retries=1))
    transport = raptor.Transport(config, journal, tmp_path, None, remote)
    with pytest.raises(ValueError, match="transport_retries"):
        transport.call({}, kind="llm", phase="index", operation="summary", object_id=0)
    assert journal.summary()["attempts"] == 0
    monkeypatch.setitem(raptor.PARAMETERS, "request_limit", 0)
    with pytest.raises(ValueError, match="request_limit_exceeded"):
        transport.call({}, kind="llm", phase="index", operation="summary", object_id=0)
    transport.summary_count = raptor.PARAMETERS["summary_limit"]
    with pytest.raises(ValueError, match="summary_limit_exceeded"):
        transport.summarize("unused", 512)
    assert journal.summary()["attempts"] == 0


@pytest.mark.skipif(
    not os.environ.get("RAPTOR_SOURCE"),
    reason="opt-in isolated official RAPTOR environment",
)
def test_official_50_leaf_tree_and_reload_without_network(tmp_path, monkeypatch):
    sdk = raptor.load_source(Path(os.environ["RAPTOR_SOURCE"]))
    import numpy as np

    rng = np.random.RandomState(42)
    calls = {"embedding": 0, "summary": 0}

    class Embedding(sdk["embedding_base"]):
        def create_embedding(self, text):
            calls["embedding"] += 1
            return rng.normal(size=1024).tolist()

    class Summary(sdk["summary_base"]):
        def summarize(self, context, max_tokens=150):
            calls["summary"] += 1
            return "A deterministic mock summary of several passages."

    np.random.seed(42)
    embedding = Embedding()
    builder = sdk["builder"](
        sdk["builder_config"](
            tokenizer=sdk["tokenizer"],
            num_layers=2,
            reduction_dimension=5,
            embedding_models={"BGE": embedding},
            cluster_embedding_model="BGE",
            summarization_model=Summary(),
            clustering_params={"max_length_in_cluster": 3000},
        )
    )
    corpus = [{"id": f"p{i}"} for i in range(50)]
    leaves = {
        i: builder.create_node(i, f"Passage {i} about a separate topic.")[1]
        for i in range(50)
    }
    nodes, layers = copy.deepcopy(leaves), {0: list(leaves.values())}
    roots = builder.construct_tree(
        nodes.copy(), nodes, layers, use_multithreading=False
    )
    tree = sdk["tree"](nodes, roots, leaves, builder.num_layers, layers)
    payload = raptor.serialize_tree(tree, corpus)
    before = calls.copy()
    restored = raptor.restore_tree(payload, sdk)
    assert calls == before
    assert calls["summary"] == len(nodes) - 50 > 0
    assert calls["embedding"] == len(nodes)
    assert set().union(*raptor.validate_tree(payload).values()) == {
        row["id"] for row in corpus
    }
    retriever = sdk["retriever"](
        sdk["retriever_config"](
            tokenizer=sdk["tokenizer"],
            context_embedding_model="BGE",
            embedding_model=embedding,
            top_k=5,
        ),
        restored,
    )
    selected, context = retriever.retrieve_information_collapse_tree(
        "test question", 5, 3000
    )
    assert len(selected) == 5 and context
    assert calls["embedding"] == before["embedding"] + 1

    # Full adapter pipeline, including three shared-reader calls, remains offline.
    # Synthetic UMAP/GMM can yield >20 summaries; expand test-only limits, while
    # the separate guard regression checks production limits before transport.
    monkeypatch.setitem(raptor.PARAMETERS, "summary_limit", 100)
    monkeypatch.setitem(raptor.PARAMETERS, "request_limit", 300)
    sent = []
    fake_rng = np.random.RandomState(7)

    class Response:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

        def raise_for_status(self):
            pass

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get_adapter(self, url):
            return SimpleNamespace(max_retries=SimpleNamespace(total=0))

        def get(self, url, **kwargs):
            return Response({"models": [{"name": "bge", "digest": "mock-digest"}]})

        def post(self, url, json, **kwargs):
            sent.append(json)
            if url.endswith("/api/embed"):
                # Five topics, without prescribing UMAP/GMM's soft cluster count.
                text = json["input"][0]
                vector = fake_rng.normal(scale=0.001, size=1024)
                topic = (
                    int(text.splitlines()[0].split()[-1]) // 10
                    if text.startswith("Topic ")
                    else 0
                )
                vector[topic] += 1
                return Response(
                    {
                        "embeddings": [vector.tolist()],
                        "prompt_eval_count": 3,
                    }
                )
            messages = json["messages"]
            content = (
                "A compact summary."
                if len(messages) == 2
                else "Thought: diagnostic\nAnswer: alpha"
            )
            return Response(
                {
                    "model": "mock-model",
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": content}}
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                }
            )

    monkeypatch.setattr(raptor.requests, "Session", Session)
    corpus = [
        {"id": f"p{i}", "title": f"Topic {i}", "text": f"A short passage number {i}."}
        for i in range(50)
    ]
    queries = [{"id": f"q{i}", "question": f"Question {i}?"} for i in range(3)]
    labels = [
        {"id": q["id"], "answer": "CANARY_GOLD_ONLY", "supporting_ids": ["p0"]}
        for q in queries
    ]
    config = {
        "base_url": "https://example.invalid/v1",
        "ollama_url": "http://127.0.0.1:11434",
        "embedding_model": "bge",
        "model": "mock-model",
        "key": "test",
    }
    manifest, directory = raptor.execute(
        {"question_ids": [q["id"] for q in queries]},
        queries,
        corpus,
        labels,
        config,
        sdk,
        tmp_path,
    )
    assert manifest["status"] == "completed", manifest
    assert manifest["completed_questions"] == 3
    assert manifest["tree"]["leaves"] == 50
    assert manifest["tree"]["reload_model_calls"] == 0
    summary = manifest["token_accounting"]["summary"]
    assert summary["complete"] and summary["attempts"] == len(sent)
    assert (
        sum(p.get("messages") is not None and len(p["messages"]) == 4 for p in sent)
        == 3
    )
    assert "CANARY_GOLD_ONLY" not in str(sent)
    assert (
        sum(p.get("messages") is not None and len(p["messages"]) == 2 for p in sent)
        == manifest["tree"]["summaries"]
    )
    assert (directory / "tree.json").is_file()


@pytest.fixture
def continuation_history(tmp_path, monkeypatch):
    root = tmp_path / "history"
    reports = root / "results/summary"
    reports.mkdir(parents=True)
    monkeypatch.setattr(raptor.target, "ROOT", root)
    plan = {k: ["sample"] for k in ("question_ids", "passage_ids")}
    plan.update(
        corpus_sha256="corpus",
        queries_sha256="queries",
        parameters=dict(raptor.PARAMETERS),
    )
    config = {
        "model": "model",
        "base_url": "https://example.invalid/v1",
        "embedding_model": "bge",
    }
    manifests = []
    for name in ("prior", "diagnostic"):
        directory = root / name
        directory.mkdir()
        journal = Journal(
            directory / "tokens.jsonl", run_id=name, method="raptor", dataset="musique"
        )
        started = journal.start(
            phase="index",
            operation="summary",
            provider="target_api",
            model="model",
            kind="llm",
        )
        if name == "prior":
            journal.finish(started, status="unknown", error_code="ReadTimeout")
        else:
            journal.finish(
                started,
                status="success",
                usage={"llm_input_tokens": 350, "llm_output_tokens": 375},
            )
        manifest = {
            "run_id": name,
            "plan": plan,
            "generation": config,
            "embedding": {"name": "bge", "digest": "mock"},
            "status": "failed" if name == "prior" else "completed",
            "token_accounting": journal.reference(),
        }
        if name == "diagnostic":
            manifest.update(
                prior_run_id="prior",
                prior_manifest_sha256=raptor.dense.sha256_file(manifests[0]),
                **config,
            )
        path = directory / "manifest.json"
        raptor.dense.write_json_atomic(path, manifest)
        manifests.append(path)
    raptor.dense.write_json_atomic(
        reports / "raptor-smoke.json",
        {"artifacts": {"manifest_sha256": raptor.dense.sha256_file(manifests[0])}},
    )
    raptor.dense.write_json_atomic(
        reports / "raptor-summary-diagnostic.json",
        {"raw_manifest_sha256": raptor.dense.sha256_file(manifests[1])},
    )
    return manifests, plan, config


def test_continuation_retains_known_cost_and_unknown(continuation_history):
    paths, plan, config = continuation_history
    _, records, sources = raptor.verify_continuation(*paths, plan, config)
    combined = raptor.summarize(records)
    assert combined["attempts"] == 2
    assert combined["known_subtotal"]["llm_input_tokens"] == 350
    assert combined["known_subtotal"]["llm_output_tokens"] == 375
    assert not combined["complete"]
    assert len(sources) == 2


@pytest.mark.parametrize("defect", ["manifest", "journal", "plan", "target"])
def test_continuation_rejects_changed_history_before_http(
    continuation_history, monkeypatch, tmp_path, defect
):
    paths, plan, config = continuation_history

    def forbidden():
        raise AssertionError("No HTTP allowed")

    monkeypatch.setattr(raptor.requests, "Session", forbidden)
    if defect == "manifest":
        paths[0].write_text("{}")
    elif defect == "journal":
        (paths[0].parent / "tokens.jsonl").write_text("{}")
    elif defect == "plan":
        plan = {**plan, "corpus_sha256": "different"}
    else:
        config = {**config, "model": "different"}
    with pytest.raises(ValueError):
        raptor.execute(
            plan, [], [], [], config, {}, tmp_path / "out", continuation=paths
        )


def test_continuation_claim_survives_failure_across_output_directories(
    continuation_history, monkeypatch, tmp_path
):
    paths, plan, config = continuation_history
    calls = []

    def offline():
        calls.append(1)
        raise RuntimeError("Simulated crash before any POST")

    monkeypatch.setattr(raptor.requests, "Session", offline)
    manifest, _ = raptor.execute(
        plan, [], [], [], config, {}, tmp_path / "out-A", continuation=paths
    )
    assert manifest["status"] == "failed"
    assert not manifest["aggregate_accounting"]["complete"]
    assert manifest["aggregate_total"] is None
    with pytest.raises(FileExistsError):
        raptor.execute(
            plan, [], [], [], config, {}, tmp_path / "out-B", continuation=paths
        )
    assert calls == [1]


def test_continuation_transport_uses_300_second_timeout(tmp_path, monkeypatch):
    journal = Journal(
        tmp_path / "tokens.jsonl", run_id="new", method="raptor", dataset="musique"
    )
    captured = []

    def post(*args, **kwargs):
        captured.append(kwargs)
        return {}

    monkeypatch.setattr(raptor.target, "checked_post", post)
    session = SimpleNamespace(
        get_adapter=lambda url: SimpleNamespace(max_retries=SimpleNamespace(total=0))
    )
    config = {"key": "test", "base_url": "https://example.invalid/v1", "model": "model"}
    transport = raptor.Transport(
        config, journal, tmp_path, session, session, continuation=True
    )
    transport.call(
        {"messages": []}, kind="llm", phase="index", operation="summary", object_id="0"
    )
    assert captured[0]["timeout"] == (5, 300)
    assert captured[0]["token_limit"] == 100_000
