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


def test_transport_retries_and_request_limit_stop_before_send(tmp_path):
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


@pytest.mark.skipif(
    not os.environ.get("RAPTOR_SOURCE"),
    reason="opt-in isolated official RAPTOR environment",
)
def test_official_50_leaf_tree_and_reload_without_network(tmp_path):
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
