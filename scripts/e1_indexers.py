"""Index-only calls into the pinned HippoRAG and RAPTOR implementations."""

import copy
import random

from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts import run_raptor_smoke as raptor
from scripts.run_e1 import PARAMETERS, ROOT


def raptor_index(corpus, transport, directory, source):
    sdk = raptor.load_source(source)
    # Same dataset, exact title-newline-text inputs and model digest; no old smoke cache.
    producer = (
        ROOT
        / "indexes/e1"
        / transport.plan["batch_id"]
        / "dense"
        / transport.row["dataset"]
    )
    for row in transport.plan.get("rows", []):
        if row["method"] == "dense" and row["dataset"] == transport.row["dataset"]:
            producer = ROOT / row["output"]
    manifest = dense.read_json(producer / "manifest.json")
    from scripts.token_accounting import verified_reference

    reference = verified_reference(manifest, producer / "manifest.json")
    vectors_path = producer / "vectors.npz"
    if (
        manifest["status"] != "completed"
        or reference["status"] != "verified"
        or not reference["summary"]["complete"]
        or manifest["artifacts"]["vectors.npz"] != dense.sha256_file(vectors_path)
        or manifest["plan_sha256"]
        not in (
            target.digest(transport.plan),
            transport.plan.get("parent_plan", {}).get("digest"),
            *[p["digest"] for p in transport.plan.get("lineage", [])],
        )
    ):
        raise ValueError("dense_leaf_producer_not_verified")
    with dense.np.load(vectors_path, allow_pickle=False) as saved:
        if saved["ids"].tolist() != [row["id"] for row in corpus]:
            raise ValueError("dense_leaf_corpus_mismatch")
        vectors = dense.normalize_rows(saved["vectors"])
    leaf_vectors = {
        f"{row['title']}\n{row['text']}": vector for row, vector in zip(corpus, vectors)
    }

    class Embedding(sdk["embedding_base"]):
        def create_embedding(self, text):
            if text in leaf_vectors:
                transport.journal.cache_hit(
                    phase="index",
                    operation="index_embedding",
                    provider="local_ollama",
                    model=transport.plan["embedding_model"],
                    kind="embedding",
                    object_id=target.digest(text),
                    producer_run_id=manifest["run_id"],
                    producer_usage_complete=True,
                )
                return leaf_vectors[text].tolist()
            return transport.embed([text])[0].tolist()

    class Summary(sdk["summary_base"]):
        def summarize(self, context, max_tokens=150):
            if max_tokens != PARAMETERS["summary_max_tokens"]:
                raise ValueError("summary_cap_mismatch")
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {
                    "role": "user",
                    "content": f"Write a summary of the following, including as many key details as possible: {context}:",
                },
            ]
            return transport.generate(messages, max_tokens, "summary")[0]

    random.seed(42)
    dense.np.random.seed(42)
    builder = sdk["builder"](
        sdk["builder_config"](
            tokenizer=sdk["tokenizer"],
            max_tokens=3000,
            num_layers=2,
            summarization_length=4096,
            summarization_model=Summary(),
            embedding_models={"BGE": Embedding()},
            cluster_embedding_model="BGE",
            reduction_dimension=5,
            clustering_params={
                "max_length_in_cluster": 3000,
                "threshold": 0.1,
                "tokenizer": sdk["tokenizer"],
            },
        )
    )
    leaves = {
        i: builder.create_node(i, f"{row['title']}\n{row['text']}")[1]
        for i, row in enumerate(corpus)
    }
    nodes, layers = copy.deepcopy(leaves), {0: list(leaves.values())}
    roots = builder.construct_tree(
        nodes.copy(), nodes, layers, use_multithreading=False
    )
    tree = sdk["tree"](nodes, roots, leaves, builder.num_layers, layers)
    payload = raptor.serialize_tree(tree, corpus)
    path = directory / "tree.json"
    dense.write_json_atomic(path, payload)
    before = transport.journal.summary()
    loaded = raptor.restore_tree(dense.read_json(path), sdk)
    if (
        raptor.serialize_tree(loaded, corpus) != payload
        or before != transport.journal.summary()
    ):
        raise ValueError("raptor_reload_mismatch")
    if set(payload["leaf_passage_ids"].values()) != {r["id"] for r in corpus}:
        raise ValueError("raptor_source_coverage_mismatch")
    return {
        "passages": len(corpus),
        "nodes": len(nodes),
        "summaries": len(nodes) - len(leaves),
        "layers": {str(k): len(v) for k, v in layers.items()},
        "reload_model_calls": 0,
        "leaf_producer_manifest_sha256": dense.sha256_file(producer / "manifest.json"),
        "leaf_producer_run_id": manifest["run_id"],
        "leaf_cost_attribution": "Physical embedding cost counted once in the Dense row; exact input vectors reused here.",
    }


def hipporag_index(corpus, transport, directory, source):
    from scripts.preflight_hipporag_repair_prompts import (
        verify_target_prompt_installation,
    )

    verify_target_prompt_installation(source)
    from hipporag import HippoRAG
    from hipporag.utils.config_utils import BaseConfig
    from scripts.hipporag_repair_executor import make_pinned_openie_parser

    parse = make_pinned_openie_parser()
    config = BaseConfig(
        save_dir=str(directory / "index"),
        llm_name="qwen3.8-27b-target",
        llm_base_url=transport.plan["endpoint"],
        embedding_model_name="bge-m3-target",
        embedding_batch_size=32,
        seed=42,
        temperature=0,
        max_retry_attempts=0,
        openie_max_workers=1,
        openie_ner_max_tokens=1024,
        openie_triple_max_tokens=3072,
        response_format={"type": "json_object"},
        force_index_from_scratch=True,
    )

    class LLM:
        global_config = config

        def infer(self, messages, max_new_tokens=1024, response_format=None, **kwargs):
            operation = "openie_ner" if max_new_tokens == 1024 else "openie_triples"
            text, metadata = transport.generate(
                messages, max_new_tokens, operation, response_format
            )
            # Strict original response; SDK partial-JSON recovery cannot make it valid.
            parse(operation, text, recover_partial=False)
            return text, metadata, metadata.get("cache_hit", False)

    class Embedding:
        embedding_dim = 1024

        def batch_encode(self, texts):
            return transport.embed([text.replace("\n", " ") for text in texts])

    identity = target.digest({"plan": transport.plan, "row": transport.row})

    def create():
        return HippoRAG(
            global_config=config,
            extraction_llm=LLM(),
            qa_llm=LLM(),
            embedding_model=Embedding(),
            index_identity=identity,
        )

    rag = create()
    original = rag.openie
    outcomes = {}

    def batch_openie(chunks):
        ner, triples = {}, {}
        for chunk_id, row in chunks.items():
            n = original.ner(chunk_id, row["content"])
            if n.metadata.get("error") or n.metadata.get("finish_reason") != "stop":
                raise ValueError("unresolved_ner_stop")
            n.unique_entities = parse("openie_ner", n.response, recover_partial=False)
            t = original.triple_extraction(chunk_id, row["content"], n.unique_entities)
            if t.metadata.get("error") or t.metadata.get("finish_reason") != "stop":
                raise ValueError("unresolved_triples_stop")
            t.triples = parse("openie_triples", t.response, recover_partial=False)
            ner[chunk_id], triples[chunk_id] = n, t
            outcomes[chunk_id] = {
                "ner": "valid_nonempty" if n.unique_entities else "valid_empty",
                "triples": "valid_nonempty" if t.triples else "valid_empty",
            }
            dense.write_json_atomic(directory / "openie-validation.json", outcomes)
        return ner, triples

    rag.openie.batch_openie = batch_openie
    # IDs are mapped explicitly to the exact SDK chunk content; labels never enter indexing.
    docs = [f"{r['title']}\n{r['text']}" for r in corpus]
    try:
        if transport.row.get("cycle_probe_source_id"):
            source_row = next(
                r for r in corpus if r["id"] == transport.row["cycle_probe_source_id"]
            )
            text = f"{source_row['title']}\n{source_row['text']}"
            transport.require_cache = True
            try:
                n = original.ner("cycle-probe", text)
            finally:
                transport.require_cache = False
            if n.metadata.get("error"):
                raise ValueError("cycle_probe_NER_not_cached")
            n.unique_entities = parse("openie_ner", n.response, recover_partial=False)
            transport.require_repair_key = True
            try:
                t = original.triple_extraction("cycle-probe", text, n.unique_entities)
            finally:
                transport.require_repair_key = False
            if (
                t.metadata.get("error")
                or t.metadata.get("finish_reason") != "stop"
                or not t.triples
            ):
                raise ValueError("cycle_probe_not_completed")
            dense.write_json_atomic(
                directory / "cycle-probe.json",
                {
                    "source_id": source_row["id"],
                    "status": "passed",
                    "triples": len(t.triples),
                    "finish_reason": t.metadata["finish_reason"],
                    "prompt_tokens": t.metadata.get("prompt_tokens"),
                    "completion_tokens": t.metadata.get("completion_tokens"),
                },
            )
        rag.index(docs)
        if set(rag.chunk_embedding_store.get_all_texts()) != set(docs) or len(
            rag.chunk_embedding_store.get_all_ids()
        ) != len(corpus):
            raise ValueError("hipporag_chunk_coverage_mismatch")
        info, _ = rag.load_existing_openie([])
        if {r["idx"] for r in info} != set(rag.chunk_embedding_store.get_all_ids()):
            raise ValueError("hipporag_openie_coverage_mismatch")
        dense.write_json_atomic(
            directory / "source-map.json",
            {
                row["id"]: rag.chunk_embedding_store.get_hash_id(text)
                for row, text in zip(corpus, docs)
            },
        )
        counts = {
            "passages": len(corpus),
            "entities": len(rag.entity_embedding_store.get_all_ids()),
            "facts": len(rag.fact_embedding_store.get_all_ids()),
            "graph_nodes": rag.graph.vcount(),
            "graph_edges": rag.graph.ecount(),
            "reload_model_calls": 0,
        }
    finally:
        rag.close()
    before = transport.journal.summary()
    config.force_index_from_scratch = False
    reloaded = create()
    try:
        if (
            len(reloaded.chunk_embedding_store.get_all_ids()) != len(corpus)
            or reloaded.graph.vcount() != counts["graph_nodes"]
            or reloaded.graph.ecount() != counts["graph_edges"]
            or before != transport.journal.summary()
        ):
            raise ValueError("hipporag_reload_mismatch")
    finally:
        reloaded.close()
    return counts
