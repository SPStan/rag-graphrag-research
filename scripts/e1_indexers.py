"""Index-only calls into the pinned HippoRAG and RAPTOR implementations."""

import copy
import json
import logging
import random

from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts import run_raptor_smoke as raptor
from scripts.run_e1 import PARAMETERS, RAPTOR_CLUSTERING_POLICY, ROOT


def verified_dense_leaves(corpus, plan, dataset, workspace):
    # Same dataset, exact title-newline-text inputs and model digest; no old smoke cache.
    producer = workspace / "indexes/e1" / plan["batch_id"] / "dense" / dataset
    for row in plan.get("rows", []):
        if row["method"] == "dense" and row["dataset"] == dataset:
            producer = workspace / row["output"]
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
            target.digest(plan),
            plan.get("parent_plan", {}).get("digest"),
            *[p["digest"] for p in plan.get("lineage", [])],
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
    return producer, manifest, leaf_vectors


def raptor_cluster_nodes(
    nodes,
    embedding_model_name,
    max_length_in_cluster=3500,
    *,
    tokenizer,
    reduction_dimension=10,
    threshold=0.1,
    verbose=False,
    cluster_fn,
):
    """Pinned node grouping, with singleton terminals where UMAP is undefined.

    Upstream computes floor(sqrt(n-1)) neighbors: n=2..4 gives 1,
    rejected by UMAP. Singletons preserve all texts without another reduction.
    The normal path and recursive defaults follow pinned cluster_utils.py.
    """
    if len(nodes) <= 4:
        logging.info("RAPTOR singleton terminal: %d nodes", len(nodes))
        return [[node] for node in nodes]
    embeddings = dense.np.array([n.embeddings[embedding_model_name] for n in nodes])
    labels = cluster_fn(embeddings, dim=reduction_dimension, threshold=threshold)
    groups = []
    for label in dense.np.unique(dense.np.concatenate(labels)):
        group = [n for n, memberships in zip(nodes, labels) if label in memberships]
        if len(group) == 1:
            groups.append(group)
        elif sum(len(tokenizer.encode(n.text)) for n in group) > max_length_in_cluster:
            # Upstream recursion resets dimension/threshold to 10/0.1.
            groups.extend(
                raptor_cluster_nodes(
                    group,
                    embedding_model_name,
                    max_length_in_cluster,
                    tokenizer=tokenizer,
                    cluster_fn=cluster_fn,
                )
            )
        else:
            groups.append(group)
    return groups


def raptor_index(corpus, transport, directory, source):
    sdk = raptor.load_source(source)
    from raptor.cluster_utils import ClusteringAlgorithm, perform_clustering

    class SmallGroupClustering(ClusteringAlgorithm):
        @staticmethod
        def perform_clustering(nodes, embedding_model_name, **kwargs):
            return raptor_cluster_nodes(
                nodes, embedding_model_name, cluster_fn=perform_clustering, **kwargs
            )

    producer, manifest, leaf_vectors = verified_dense_leaves(
        corpus, transport.plan, transport.row["dataset"], ROOT
    )

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
            clustering_algorithm=SmallGroupClustering,
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
        "clustering_policy": RAPTOR_CLUSTERING_POLICY,
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
            try:
                text, metadata = transport.generate(
                    messages, max_new_tokens, operation, response_format
                )
            except Exception as exc:
                # The pinned SDK returns metadata on inference errors. Preserve
                # the original IO/transport exception across that wrapper.
                transport.extraction_error = exc
                raise
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
                if getattr(transport, "extraction_error", None) is not None:
                    raise transport.extraction_error
                raise ValueError(f"unresolved_ner_stop: {n.metadata.get('error')}")
            n.unique_entities = parse("openie_ner", n.response, recover_partial=False)
            t = original.triple_extraction(chunk_id, row["content"], n.unique_entities)
            if t.metadata.get("error") or t.metadata.get("finish_reason") != "stop":
                if getattr(transport, "extraction_error", None) is not None:
                    raise transport.extraction_error
                raise ValueError(f"unresolved_triples_stop: {t.metadata.get('error')}")
            t.triples = parse("openie_triples", t.response, recover_partial=False)
            ner[chunk_id], triples[chunk_id] = n, t
            outcomes[chunk_id] = {
                "ner": "valid_nonempty" if n.unique_entities else "valid_empty",
                "triples": "valid_nonempty" if t.triples else "valid_empty",
            }
            if transport.row.get("resume_kind") == "mixed_native":
                repeated = 0
                longest = 0
                previous = None
                raw_values = json.loads(t.response)["triples"]
                for triple in raw_values:
                    repeated = repeated + 1 if triple == previous else 1
                    previous = triple
                    longest = max(longest, repeated)
                outcomes[chunk_id].update(
                    extractor_model=t.metadata["extractor_model"],
                    triples_request_sha256=t.metadata["triples_request_sha256"],
                    warning=not n.unique_entities
                    or not t.triples
                    or longest >= 12
                    or (
                        len(raw_values) >= 12
                        and len(set(map(tuple, raw_values))) * 4 <= len(raw_values)
                    ),
                    raw_triples=len(raw_values),
                    unique_triples=len(set(map(tuple, raw_values))),
                )
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


def load_ready_e1(plan, row, corpus, workspace=ROOT):
    """Read-only artifact gate for offline E2 preparation; never opens a model client."""
    from scripts.token_accounting import verified_reference

    path = workspace / row["output"] / "manifest.json"
    manifest = dense.read_json(path)
    if (
        manifest["status"] != "completed"
        or verified_reference(manifest, path)["status"] != "verified"
    ):
        raise ValueError("E2_index_not_completed_or_verified")
    identities = [
        target.digest(plan),
        plan.get("parent_plan", {}).get("digest"),
        *[p["digest"] for p in plan.get("lineage", [])],
    ]
    if (
        manifest["plan_sha256"] not in identities
        or dense.corpus_fingerprint(corpus) != row["corpus_fingerprint"]
    ):
        raise ValueError("E2_index_plan_or_corpus_changed")
    for name, sha in manifest["artifacts"].items():
        if dense.sha256_file(path.parent / name) != sha:
            raise ValueError("E2_index_artifact_changed")
    ids = [p["id"] for p in corpus]
    if len(set(ids)) != len(ids):
        raise ValueError("E2_duplicate_source_ids")
    common = {
        "corpus": corpus,
        "manifest_sha256": dense.sha256_file(path),
        "embedding_digest": plan["embedding_digest"],
        "directory": path.parent,
    }
    if row["method"] == "dense":
        with dense.np.load(path.parent / "vectors.npz", allow_pickle=False) as saved:
            if saved["ids"].tolist() != ids:
                raise ValueError("E2_dense_source_order_changed")
            matrix = dense.normalize_rows(saved["vectors"])
        if matrix.shape != (len(ids), 1024):
            raise ValueError("E2_embedding_dimension_changed")
        return {**common, "kind": "dense", "vectors": matrix}
    if row["method"] == "raptor":
        tree = dense.read_json(path.parent / "tree.json")
        if (
            tree["dimension"] != 1024
            or tree["implementation_commit"] != raptor.SOURCE_COMMIT
        ):
            raise ValueError("E2_raptor_contract_changed")
        ancestry = raptor.validate_tree(tree)
        if [
            tree["leaf_passage_ids"].get(str(i)) for i in range(len(ids))
        ] != ids or len(tree["leaf_passage_ids"]) != len(ids):
            raise ValueError("E2_raptor_source_mapping_changed")
        nodes_by_id = {n["index"]: n for n in tree["nodes"]}
        for i, doc in enumerate(corpus):
            node = nodes_by_id[i]
            if node["text"] != f"{doc['title']}\n{doc['text']}":
                raise ValueError("E2_raptor_leaf_text_changed")
        return {**common, "kind": "raptor", "tree": tree, "ancestry": ancestry}
    if row["method"] == "hipporag2":
        mapping = dense.read_json(path.parent / "source-map.json")
        if set(mapping) != set(ids) or len(set(mapping.values())) != len(ids):
            raise ValueError("E2_hippo_source_mapping_changed")
        return {**common, "kind": "hipporag2", "source_map": mapping}
    raise ValueError("E2_unknown_method")


def retrieve_ready_e1(loaded, question, query_vector, *, embedding_digest, sdk=None):
    """Use an explicitly supplied cached/synthetic vector; no embedding fallback."""
    if embedding_digest != loaded["embedding_digest"]:
        raise ValueError("E2_query_embedding_model_changed")
    vector = dense.normalize_rows([query_vector])[0]
    if vector.shape != (1024,):
        raise ValueError("E2_query_vector_dimension_changed")
    if loaded["kind"] == "dense":
        ranked = dense.top_k(vector, loaded["vectors"], 5)
        passages = [loaded["corpus"][i] for i, _ in ranked]
        return {
            "kind": "passages",
            "passages": passages,
            "source_ids": [p["id"] for p in passages],
            "scores": [float(score) for _, score in ranked],
            "new_embedding_calls": 0,
        }
    if sdk is None:
        raise ValueError("E2_pinned_raptor_sdk_required")

    class CachedEmbedding(sdk["embedding_base"]):
        def create_embedding(self, text):
            if text != question:
                raise ValueError("E2_unplanned_embedding_input")
            return vector.tolist()

    tree = raptor.restore_tree(loaded["tree"], sdk)
    retriever = sdk["retriever"](
        sdk["retriever_config"](
            tokenizer=sdk["tokenizer"],
            top_k=5,
            selection_mode="top_k",
            context_embedding_model="BGE",
            embedding_model=CachedEmbedding(),
        ),
        tree,
    )
    selected, _ = retriever.retrieve_information_collapse_tree(question, 5, 2**63 - 1)
    if not selected:
        raise ValueError("E2_empty_cached_retrieval")
    covered = sorted(set().union(*(loaded["ancestry"][n.index] for n in selected)))
    return {
        "kind": "raptor_nodes",
        "passages": [
            {"title": f"RAPTOR node {n.index}", "text": n.text} for n in selected
        ],
        "node_ids": [n.index for n in selected],
        "nodes": [
            {
                "id": n.index,
                "level": next(
                    int(level)
                    for level, indices in loaded["tree"]["layers"].items()
                    if n.index in indices
                ),
                "source_ids": sorted(loaded["ancestry"][n.index]),
            }
            for n in selected
        ],
        "scores": [
            float(dense.np.dot(vector, dense.normalize_rows([n.embeddings["BGE"]])[0]))
            for n in selected
        ],
        "source_ids": covered,
        "new_embedding_calls": 0,
    }


def replay_cached_reader(query, retrieval, responses, label):
    """Common prompt/parser/evaluator on synthetic/cache inputs only; never HTTP."""
    from scripts import evaluate_dense as evaluator
    from scripts.token_accounting import extract_usage

    messages = dense.build_reader_messages(query["question"], retrieval["passages"])
    payload = {**target.OPTIONS, "model": "iairlab/qwen3.8-27b", "messages": messages}
    if len(json.dumps(messages, ensure_ascii=False).encode()) > target.INPUT_BYTE_LIMIT:
        raise ValueError("E2_reader_input_byte_limit_no_truncation")
    key = target.digest({"payload": payload, "kind": "llm", "operation": "reader"})
    if key not in responses:
        raise ValueError("E2_reader_cache_miss_no_http_fallback")
    saved = responses[key]
    body = saved["response"]
    if target.digest(body) != saved["response_sha256"]:
        raise ValueError("E2_reader_cached_response_changed")
    usage = extract_usage(body, "llm", "target_api")
    if usage["llm_input_tokens"] is None or usage["llm_output_tokens"] is None:
        raise ValueError("E2_reader_unknown_usage")
    choice = body["choices"][0]
    answer, status = dense.extract_target_reader_answer(choice["message"]["content"])
    if choice["finish_reason"] != "stop" or status != "ok":
        raise ValueError("E2_reader_not_complete")
    if query["id"] != label["id"] or not label["supporting_ids"]:
        raise ValueError("E2_synthetic_label_mismatch")
    scores = evaluator.answer_scores(
        answer, [label["answer"], *label.get("answer_aliases", [])]
    )
    scores["passage_recall_at_5"] = (
        evaluator.recall_at_k(retrieval["source_ids"], label["supporting_ids"], 5)
        if retrieval["kind"] == "passages"
        else None
    )
    scores["supporting_provenance_coverage"] = len(
        set(retrieval["source_ids"]) & set(label["supporting_ids"])
    ) / len(set(label["supporting_ids"]))
    return {
        "mode": "offline_preparation_only",
        "answer": answer,
        "metrics": scores,
        "metric_version": evaluator.METRIC_VERSION,
        "reader_prompt_version": dense.READER_PROMPT_VERSION,
        "request_sha256": key,
        "cached_usage": usage,
        "historical_cost_complete": None,
        "new_model_calls": 0,
    }


def load_hippo_query_only(loaded, source, infer):
    """Use pinned retrieval methods on verified persisted stores; no SDK constructors.

    The SDK constructor opens mutable stores/locks and OpenIE. Bypass only that
    lifecycle. Its prepare_retrieval_objects rebuilds IN-MEMORY lookup maps from
    saved triples; add_fact_edges does not alter an existing complete graph.
    """
    from scripts.preflight_hipporag_repair_prompts import (
        verify_target_prompt_installation,
    )

    verify_target_prompt_installation(source)
    import ast
    import igraph
    from hipporag import HippoRAG
    from hipporag.embedding_store import EmbeddingStore
    from hipporag.rerank import DSPyFilter
    from hipporag.utils.config_utils import BaseConfig

    def forbidden(*args, **kwargs):
        raise ValueError("E2_indexing_or_uncached_embedding_forbidden")

    class QueryOnly(HippoRAG):
        index = delete = save_igraph = save_openie_results = forbidden

    class LLM:
        error = None

        def infer(self, messages, max_new_tokens=512, **kwargs):
            try:
                if max_new_tokens != 512 or kwargs:
                    raise ValueError("E2_unplanned_filter_options")
                return self.handler(messages), {}, False
            except Exception as exc:
                self.error = exc
                raise

    class Filter(DSPyFilter):
        def parse_filter(self, response):
            # SDK swallows parse/transport errors into legitimate empty-fact DPR.
            # Preserve native matching, but make malformed responses fatal later.
            try:
                marker = "[[ ## fact_after_filter ## ]]"
                end = "[[ ## completed ## ]]"
                if response.count(marker) != 1 or response.count(end) != 1:
                    raise ValueError("E2_filter_markers_invalid")
                value = response.split(marker)[1].split(end)[0].strip()
                parsed = ast.literal_eval(value)
                facts = parsed["fact"]
                if (
                    set(parsed) != {"fact"}
                    or not isinstance(facts, list)
                    or any(
                        not isinstance(f, list)
                        or len(f) != 3
                        or any(not isinstance(v, str) or not v.strip() for v in f)
                        for f in facts
                    )
                ):
                    raise ValueError("E2_filter_shape_invalid")
                return super().parse_filter(response)
            except Exception as exc:
                rag.extraction_llm.error = exc
                raise

    base = loaded["directory"] / "index"
    directory = base / "qwen3.8-27b-target_bge-m3-target"
    rag = QueryOnly.__new__(QueryOnly)
    rag.global_config = BaseConfig(
        linking_top_k=5, retrieval_top_k=5, passage_node_weight=0.05, damping=0.5
    )
    rag.graph = igraph.Graph.Read_Pickle(str(directory / "graph.pickle"))
    rag._graph_state_available = True
    rag.chunk_metadata = dense.read_json(directory / "chunk_metadata.json")
    rag._openie_info = dense.read_json(
        base / "openie_results_ner_qwen3.8-27b-target.json"
    )["docs"]
    for name in ("chunk", "entity", "fact"):
        store = EmbeddingStore.__new__(EmbeddingStore)
        store.namespace = name
        store.filename = str(directory / f"{name}_embeddings/vdb_{name}.parquet")
        if not dense.Path(store.filename).is_file():
            raise ValueError("E2_store_missing")
        store._load_data()  # Pinned read-only loader, no constructor/locks/upsert.
        if dense.np.asarray(store.embeddings).shape != (len(store.hash_ids), 1024):
            raise ValueError("E2_invalid_store_vectors")
        store.insert_strings = store.delete = store._save_data = forbidden
        setattr(rag, f"{name}_embedding_store", store)
    docs = {p["id"]: f"{p['title']}\n{p['text']}" for p in loaded["corpus"]}
    for source_id, key in loaded["source_map"].items():
        if rag.chunk_embedding_store.get_row(key)["content"] != docs[source_id]:
            raise ValueError("E2_hippo_source_text_changed")
    rag.ready_to_retrieve = False
    rag.ent_node_to_chunk_ids = None
    rag.ppr_time = rag.rerank_time = rag.all_retrieval_time = 0
    rag.extraction_llm = LLM()
    rag.extraction_llm.handler = infer
    rag.embedding_model = type(
        "NoEmbedding", (), {"batch_encode": staticmethod(forbidden)}
    )()
    rag.rerank_filter = Filter(rag)
    native_rerank = rag.rerank_facts

    def checked_rerank(*args):
        indices, facts, log = native_rerank(*args)
        if log.get("error"):
            raise ValueError("E2_native_rerank_failed: " + log["error"])
        return indices, facts, log

    rag.rerank_facts = checked_rerank
    rag.prepare_retrieval_objects()
    return rag


def retrieve_hippo_query_only(loaded, rag, question, query_vector, embedding_digest):
    if loaded["embedding_digest"] != embedding_digest:
        raise ValueError("E2_query_embedding_model_changed")
    vector = dense.normalize_rows([query_vector])[0]
    if vector.shape != (1024,) or not dense.np.isfinite(vector).all():
        raise ValueError("E2_query_vector_dimension_changed")
    for kind in ("triple", "passage"):
        rag.query_to_embedding[kind][question] = vector
    rag.extraction_llm.error = None
    result = rag.retrieve([question], num_to_retrieve=5)[0]
    if rag.extraction_llm.error is not None:
        raise rag.extraction_llm.error
    by_text = {f"{p['title']}\n{p['text']}": p for p in loaded["corpus"]}
    passages = [by_text[text] for text in result.docs]
    return {
        "kind": "passages",
        "passages": passages,
        "source_ids": [p["id"] for p in passages],
        "scores": [float(s) for s in result.doc_scores],
        "graph_seeds": result.graph_seeds,
        "dense_fallback": not bool(result.graph_seeds),
        "new_embedding_calls": 0,
    }
