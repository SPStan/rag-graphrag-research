"""Bounded official RAPTOR tree, with journalled callbacks and the shared reader."""

import argparse
import copy
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import uuid

from dotenv import load_dotenv
import requests

from scripts import check_target_api as api
from scripts import evaluate_dense as evaluator
from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts.token_accounting import (
    Journal,
    read_records,
    summarize,
    verified_reference,
)

SOURCE_COMMIT = "7da1d48a7e1d7dec61a63c9d9aae84e2dfaa5767"
PARAMETERS = {
    "seed": 42,
    "num_layers": 2,
    "reduction_dimension": 5,
    "max_length_in_cluster": 3000,
    "threshold": 0.1,
    "summary_max_tokens": 512,
    "summary_limit": 20,
    "request_limit": 100,
    "token_limit": 100_000,
    "input_byte_limit": 16_000,
    "retrieval_max_cl100k_tokens": 3000,
    "top_k": 5,
    "structural_tokenizer": "cl100k_base",
    "embedding_alias": "BGE",
}


REPAIR_PARAMETERS = {
    **PARAMETERS,
    "summary_max_tokens": 4096,
    "summary_limit": 100,
    "request_limit": 200,
}


def cache_key(payload, kind, phase, operation):
    normalized = dict(payload)
    if kind == "llm" and operation == "summary":
        normalized.pop("max_tokens", None)
    return target.digest([kind, phase, operation, normalized])


def load_source(source):
    """Check every imported Python file against the pinned Git blob."""
    source = Path(source).resolve()

    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={source.as_posix()}",
                "-C",
                str(source),
                *args,
            ]
        )

    if git("rev-parse", "HEAD").decode().strip() != SOURCE_COMMIT:
        raise ValueError("raptor_source_revision_mismatch")
    paths = git("ls-tree", "-r", "--name-only", "HEAD", "raptor").decode().splitlines()
    expected = {name for name in paths if name.endswith(".py")}
    actual = {
        p.relative_to(source).as_posix() for p in (source / "raptor").rglob("*.py")
    }
    if actual != expected:
        raise ValueError("raptor_source_file_set_mismatch")
    for name in expected:
        if (source / name).read_bytes().replace(b"\r\n", b"\n") != git(
            "show", f"HEAD:{name}"
        ):
            raise ValueError("raptor_source_content_mismatch")
    if "raptor" in sys.modules:
        raise ValueError("raptor_already_imported")
    sys.path.insert(0, str(source))
    from raptor.cluster_tree_builder import ClusterTreeBuilder, ClusterTreeConfig
    from raptor.EmbeddingModels import BaseEmbeddingModel
    from raptor.SummarizationModels import BaseSummarizationModel
    from raptor.tree_retriever import TreeRetriever, TreeRetrieverConfig
    from raptor.tree_structures import Node, Tree
    import tiktoken

    return {
        "builder": ClusterTreeBuilder,
        "builder_config": ClusterTreeConfig,
        "embedding_base": BaseEmbeddingModel,
        "summary_base": BaseSummarizationModel,
        "retriever": TreeRetriever,
        "retriever_config": TreeRetrieverConfig,
        "node": Node,
        "tree": Tree,
        "tokenizer": tiktoken.get_encoding("cl100k_base"),
    }


def prepare(data_root):
    plan, queries, _, labels = target.prepare("musique", data_root)
    queries, labels = queries[:3], labels[:3]
    corpus = dense.read_json(Path(data_root) / "data/processed/musique/corpus.json")
    support = {pid for row in labels for pid in row["supporting_ids"]}
    others = [row["id"] for row in corpus if row["id"] not in support]
    ids = support | set(others[: 50 - len(support)])
    selected = [row for row in corpus if row["id"] in ids]
    if len(selected) != 50 or len(support) > 50:
        raise ValueError("expected_50_unique_passages")
    plan.update(
        kind="raptor_small_corpus_functionality",
        question_ids=[row["id"] for row in queries],
        passage_ids=[row["id"] for row in selected],
        corpus_sha256=target.digest(selected),
        queries_sha256=target.digest(queries),
        selection="first 3 development S500 IDs; supporting union + first other corpus IDs to 50",
        parameters=PARAMETERS,
        implementation={
            "repository": "https://github.com/parthsarthi03/raptor",
            "commit": SOURCE_COMMIT,
        },
    )
    # Replace Dense-specific values rather than inheriting a contradictory plan.
    for key in (
        "ordered_question_ids_sha256",
        "token_limit_per_dataset",
        "reader_input_byte_limit",
    ):
        plan.pop(key, None)
    plan["limitations"] = (
        "Support-preserving development smoke, not effectiveness evidence. "
        "Summary provenance is leaf ancestry, not proof that a fact survives compression. "
        "Target contract supplied by operator; deployment HF revision unverified. Byte reservations are accounting guards."
    )
    return plan, queries, selected, labels


def validate_tree(payload):
    """Resolve all ancestry, rejecting corrupt topology before constructing objects."""
    nodes = {row["index"]: row for row in payload["nodes"]}
    leaves = {int(key): value for key, value in payload["leaf_passage_ids"].items()}
    if len(nodes) != len(payload["nodes"]) or len(set(leaves.values())) != len(leaves):
        raise ValueError("duplicate_tree_ids")
    memo, active = {}, set()

    def visit(index):
        if index in active or index not in nodes:
            raise ValueError("cycle_or_missing_child")
        if index in memo:
            return memo[index]
        active.add(index)
        node = nodes[index]
        vector = node["embeddings"]["BGE"]
        if len(vector) != payload["dimension"]:
            raise ValueError("tree_embedding_dimension_mismatch")
        dense.normalize_rows([vector])
        if not isinstance(node["text"], str) or not node["text"].strip():
            raise ValueError("empty_tree_node")
        children = node["children"]
        if index in leaves:
            if children:
                raise ValueError("leaf_has_children")
            ancestry = {leaves[index]}
        else:
            if not children:
                raise ValueError("summary_without_children")
            ancestry = set().union(*(visit(child) for child in children))
        memo[index] = ancestry
        active.remove(index)
        return ancestry

    if not leaves.keys() <= nodes.keys():
        raise ValueError("missing_leaf")
    for index in nodes:
        visit(index)
    layers = {int(k): v for k, v in payload["layers"].items()}
    flat = [index for level in layers.values() for index in level]
    if set(flat) != nodes.keys() or len(flat) != len(nodes):
        raise ValueError("invalid_tree_layers")
    if (
        set(layers[0]) != leaves.keys()
        or payload["roots"] != layers[payload["num_layers"]]
    ):
        raise ValueError("invalid_tree_roots")
    levels = {index: level for level, members in layers.items() for index in members}
    if any(
        levels[child] >= levels[index]
        for index, row in nodes.items()
        for child in row["children"]
    ):
        raise ValueError("invalid_child_layer")
    return memo


def serialize_tree(tree, corpus):
    payload = {
        "schema_version": 1,
        "dimension": 1024,
        "implementation_commit": SOURCE_COMMIT,
        "nodes": [
            {
                "index": n.index,
                "text": n.text,
                "children": sorted(n.children),
                "embeddings": n.embeddings,
            }
            for n in tree.all_nodes.values()
        ],
        "leaf_passage_ids": {str(i): row["id"] for i, row in enumerate(corpus)},
        "layers": {
            str(k): [n.index for n in v] for k, v in tree.layer_to_nodes.items()
        },
        "roots": [n.index for n in tree.root_nodes.values()],
        "num_layers": tree.num_layers,
    }
    validate_tree(payload)
    return payload


def restore_tree(payload, sdk):
    if (
        payload["schema_version"] != 1
        or payload["implementation_commit"] != SOURCE_COMMIT
    ):
        raise ValueError("tree_contract_mismatch")
    validate_tree(payload)
    nodes = {
        n["index"]: sdk["node"](
            n["text"], n["index"], set(n["children"]), n["embeddings"]
        )
        for n in payload["nodes"]
    }
    layers = {int(k): [nodes[i] for i in v] for k, v in payload["layers"].items()}
    return sdk["tree"](
        nodes,
        {i: nodes[i] for i in payload["roots"]},
        {int(i): nodes[int(i)] for i in payload["leaf_passage_ids"]},
        payload["num_layers"],
        layers,
    )


class Transport:
    def __init__(
        self,
        config,
        journal,
        directory,
        local,
        remote,
        *,
        continuation=False,
        parameters=None,
        cache=None,
    ):
        self.config, self.journal, self.directory = config, journal, directory
        self.parameters = PARAMETERS if parameters is None else parameters
        self.cache = cache or {}
        self.cache_provenance = []
        self.local, self.remote = local, remote
        self.embedding_count, self.summary_count = 0, 0
        self.phase, self.object_id = "index", None
        self.timeout = (5, 300) if continuation else (5, 120)

    def call(self, payload, *, kind, phase, operation, object_id):
        if self.journal.summary()["attempts"] >= self.parameters["request_limit"]:
            raise ValueError("request_limit_exceeded")
        config = self.config
        is_llm = kind == "llm"
        session = self.remote if is_llm else self.local
        base = config["base_url"] if is_llm else config["ollama_url"]
        if session.get_adapter(base).max_retries.total != 0:
            raise ValueError("transport_retries_must_be_zero")
        cached = self.cache.get(cache_key(payload, kind, phase, operation))
        if cached is not None:
            self.journal.cache_hit(
                phase=phase,
                operation=operation,
                provider="target_api" if is_llm else "local_ollama",
                model=config["model"] if is_llm else config["embedding_model"],
                kind=kind,
                object_id=str(object_id),
                producer_run_id=cached["producer_run_id"],
                producer_usage_complete=True,
            )
            self.cache_provenance.append(
                {k: v for k, v in cached.items() if k != "body"}
            )
            dense.write_json_atomic(
                self.directory / "cache-provenance.json", self.cache_provenance
            )
            return copy.deepcopy(cached["body"])
        request_id = f"{phase}-{operation}-{self.journal.summary()['attempts']}"
        headers = {"Authorization": f"Bearer {config['key']}"} if is_llm else None
        target.save_private_json(
            self.directory / f"{request_id}.request.json", payload, headers
        )
        return target.checked_post(
            session,
            base + ("/chat/completions" if is_llm else "/api/embed"),
            payload,
            self.journal,
            phase=phase,
            operation=operation,
            provider="target_api" if is_llm else "local_ollama",
            model=config["model"] if is_llm else config["embedding_model"],
            kind=kind,
            object_id=str(object_id),
            headers=headers,
            response_path=self.directory / f"{request_id}.response.json",
            token_limit=self.parameters["token_limit"],
            timeout=self.timeout,
        )

    def embed(self, text):
        object_id = self.embedding_count if self.phase == "index" else self.object_id
        body = self.call(
            {
                "model": self.config["embedding_model"],
                "input": [text],
                "truncate": False,
            },
            kind="embedding",
            phase=self.phase,
            operation="embedding",
            object_id=object_id,
        )
        vectors = body.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != 1:
            raise ValueError("embedding_count_mismatch")
        vector = dense.normalize_rows(vectors)
        if vector.shape[1] != 1024:
            raise ValueError("embedding_dimension_mismatch")
        self.embedding_count += 1
        return vector[0].tolist()

    def generate(self, messages, phase, operation, object_id):
        if (
            len(json.dumps(messages, ensure_ascii=False).encode())
            > self.parameters["input_byte_limit"]
        ):
            raise ValueError("generation_input_byte_limit_exceeded")
        options = dict(target.OPTIONS)
        if operation == "summary":
            options["max_tokens"] = self.parameters["summary_max_tokens"]
        body = self.call(
            {"model": self.config["model"], "messages": messages, **options},
            kind="llm",
            phase=phase,
            operation=operation,
            object_id=object_id,
        )
        choice = body.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content")
        if (
            choice.get("finish_reason") != "stop"
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError("generation_format_or_finish_reason_invalid")
        return content, body

    def summarize(self, context, max_tokens):
        if (
            max_tokens != self.parameters["summary_max_tokens"]
            or self.summary_count >= self.parameters["summary_limit"]
        ):
            raise ValueError("summary_limit_exceeded")
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": f"Write a summary of the following, including as many key details as possible: {context}:",
            },
        ]
        content, _ = self.generate(messages, "index", "summary", self.embedding_count)
        self.summary_count += 1
        return content


def verify_continuation(prior_path, diagnostic_path, plan, config):
    """Verify immutable historical runs; their unknown usage remains unknown."""
    prior_path, diagnostic_path = (
        Path(prior_path).resolve(),
        Path(diagnostic_path).resolve(),
    )
    baseline = dense.read_json(target.ROOT / "results/summary/raptor-smoke.json")
    diagnostic_report = dense.read_json(
        target.ROOT / "results/summary/raptor-summary-diagnostic.json"
    )
    expected = [
        baseline["artifacts"]["manifest_sha256"],
        diagnostic_report["raw_manifest_sha256"],
    ]
    records, sources = [], []
    for path, sha in zip((prior_path, diagnostic_path), expected):
        if dense.sha256_file(path) != sha:
            raise ValueError("continuation_manifest_hash_mismatch")
        manifest = dense.read_json(path)
        reference = verified_reference(manifest, path)
        if reference["status"] != "verified":
            raise ValueError("continuation_journal_not_intact")
        records.extend(read_records(reference["path"]))
        sources.append(
            {
                "run_id": manifest["run_id"],
                "manifest_sha256": sha,
                "accounting": manifest["token_accounting"],
            }
        )
    prior, diagnostic = dense.read_json(prior_path), dense.read_json(diagnostic_path)
    for key in (
        "question_ids",
        "passage_ids",
        "corpus_sha256",
        "queries_sha256",
        "parameters",
    ):
        if prior["plan"][key] != plan[key]:
            raise ValueError("continuation_plan_mismatch")
    if (
        diagnostic["prior_run_id"] != prior["run_id"]
        or diagnostic["prior_manifest_sha256"] != expected[0]
        or diagnostic["status"] != "completed"
        or not diagnostic["token_accounting"]["summary"]["complete"]
    ):
        raise ValueError("continuation_diagnostic_mismatch")
    if (
        config["model"] != prior["generation"]["model"]
        or config["base_url"] != prior["generation"]["base_url"]
        or diagnostic["model"] != config["model"]
        or diagnostic["base_url"] != config["base_url"]
    ):
        raise ValueError("continuation_target_mismatch")
    if config["embedding_model"] != prior["embedding"]["name"]:
        raise ValueError("continuation_embedding_model_mismatch")
    if summarize(records)["complete"]:
        raise ValueError("continuation_expected_historical_unknown")
    return prior_path, records, sources


def verify_repair(path, plan, config):
    """Reuse only intact, complete, successful outputs; never reuse truncated text."""
    path = Path(path).resolve()
    report = dense.read_json(target.ROOT / "results/summary/raptor-continuation.json")
    if dense.sha256_file(path) != report["artifacts"]["manifest.json"]:
        raise ValueError("repair_manifest_hash_mismatch")
    manifest = dense.read_json(path)
    ref = verified_reference(manifest, path)
    if ref["status"] != "verified" or not ref["summary"]["complete"]:
        raise ValueError("repair_producer_usage_not_complete")
    if (
        manifest["status"] != "failed"
        or manifest["error_code"] != "generation_format_or_finish_reason_invalid"
        or manifest["generation"]["model"] != config["model"]
        or manifest["generation"]["base_url"] != config["base_url"]
    ):
        raise ValueError("repair_source_contract_mismatch")
    for key in ("question_ids", "passage_ids", "corpus_sha256", "queries_sha256"):
        if manifest["plan"][key] != plan[key]:
            raise ValueError("repair_plan_mismatch")
    if manifest["plan"]["parameters"] != PARAMETERS:
        raise ValueError("repair_original_parameters_mismatch")
    for name, sha in report["artifacts"].items():
        if Path(name).name != name or dense.sha256_file(path.parent / name) != sha:
            raise ValueError("repair_artifact_hash_mismatch")
    records = read_records(ref["path"])
    finished = {r["attempt_id"]: r for r in records if r["event"] == "finished"}
    cache, truncated = {}, 0
    started = [r for r in records if r["event"] == "started"]
    for index, row in enumerate(started):
        last = finished.get(row["attempt_id"], {})
        if last.get("status") != "success" or last.get("usage_status") != "complete":
            raise ValueError("repair_incomplete_physical_attempt")
        stem = f"{row['phase']}-{row['operation']}-{index}"
        request_path, response_path = (
            path.parent / (stem + ".request.json"),
            path.parent / (stem + ".response.json"),
        )
        # Every reused request/response must be independently anchored in the public report.
        for artifact in (request_path, response_path):
            if report["artifacts"].get(artifact.name) != dense.sha256_file(artifact):
                raise ValueError("repair_unanchored_response")
        payload, body = dense.read_json(request_path), dense.read_json(response_path)
        if row["kind"] == "llm":
            choice = body.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content")
            if choice.get("finish_reason") == "length":
                truncated += 1
                continue
            if (
                choice.get("finish_reason") != "stop"
                or not isinstance(content, str)
                or not content.strip()
            ):
                raise ValueError("repair_invalid_summary")
        else:
            vectors = dense.normalize_rows(body.get("embeddings"))
            if vectors.shape != (1, 1024):
                raise ValueError("repair_invalid_embedding")
        key = cache_key(payload, row["kind"], row["phase"], row["operation"])
        cache.setdefault(
            key,
            {
                "body": body,
                "producer_run_id": manifest["run_id"],
                "request_sha256": dense.sha256_file(request_path),
                "response_sha256": dense.sha256_file(response_path),
                "request_file": request_path.name,
                "response_file": response_path.name,
                "producer_output_cap": payload.get("max_tokens"),
                "kind": row["kind"],
                "operation": row["operation"],
            },
        )
    if truncated != 1:
        raise ValueError("repair_expected_one_truncated_summary")
    spent = sum(ref["summary"]["known_subtotal"].values())
    if spent >= PARAMETERS["token_limit"]:
        raise ValueError("repair_budget_exhausted")
    source = {
        "run_id": manifest["run_id"],
        "manifest_sha256": dense.sha256_file(path),
        "accounting": manifest["token_accounting"],
    }
    return records, source, cache, PARAMETERS["token_limit"] - spent


def execute(
    plan,
    queries,
    corpus,
    labels,
    config,
    sdk,
    output_dir,
    *,
    continuation=None,
    repair_from=None,
):
    history, sources, cache = [], [], {}
    parameters = PARAMETERS
    if repair_from is not None and continuation is None:
        raise ValueError("repair_requires_historical_continuation")
    if continuation is not None:
        original_plan = (
            {**plan, "parameters": PARAMETERS} if repair_from is not None else plan
        )
        prior_path, history, sources = verify_continuation(
            *continuation, original_plan, config
        )
    if repair_from is not None:
        extra, source, cache, remaining = verify_repair(repair_from, plan, config)
        if source["run_id"] in {s["run_id"] for s in sources}:
            raise ValueError("repair_duplicate_source_run")
        history.extend(extra)
        sources.append(source)
        parameters = {**REPAIR_PARAMETERS, "token_limit": remaining}
        if plan["parameters"] != parameters:
            raise ValueError("repair_parameters_mismatch")
    run_id = str(uuid.uuid4())
    if continuation is not None:
        claim = prior_path.parent / (
            "smoke-summary-cap4096-once.claim.json"
            if repair_from is not None
            else "smoke-continuation-once.claim.json"
        )
        with claim.open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "run_id": run_id,
                    "prior_run_id": sources[0]["run_id"],
                    "parameters": parameters,
                    "authorization": "Teacher approval relayed by user in this chat 2026-10-20: Ну, я точно не против",
                },
                stream,
            )
            stream.flush()
            os.fsync(stream.fileno())
    directory = Path(output_dir) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    journal = Journal(
        directory / "tokens.jsonl", run_id=run_id, method="raptor", dataset="musique"
    )
    manifest = {
        "run_id": run_id,
        "status": "starting",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "plan": plan,
        "plan_sha256": target.digest(plan),
        "code": dense.git_snapshot(),
        "adapter_sha256": dense.sha256_file(Path(__file__)),
        "runtime": {
            d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
        },
        "generation": {
            "model": config["model"],
            "base_url": config["base_url"],
            "options": target.OPTIONS,
            "backend_revision": "unknown",
        },
    }
    if continuation is not None:
        manifest["continuation"] = {
            "authorization": "Teacher approval relayed by user in this chat 2026-10-20: Ну, я точно не против",
            "authorization_scope": "One bounded continuation retaining historical unknown usage; no full corpus or automatic retry",
            "source_link": None,
            "source_link_note": "User supplied quotation in chat; no external message URL provided",
            "prior_runs": sources,
            "new_token_limit": parameters["token_limit"],
            "timeout_seconds": {"connect": 5, "read": 300},
            "rebuild": "Fresh run; historical embeddings/diagnostic summary are not reused or charged as free cache",
        }
    if repair_from is not None:
        manifest["repair"] = {
            "authorization": "User instructed: Сделай все что нужно, 2026-10-20; teacher acceptance of historical unknown retained",
            "policy": "One cap4096 remediation; reuse only complete stop responses/embeddings with SHA provenance; no transport retry",
            "source_run_id": sources[-1]["run_id"],
            "cache_entries": len(cache),
            "combined_continuation_budget": PARAMETERS["token_limit"],
            "new_budget_remaining": parameters["token_limit"],
            "generation_options": {
                **target.OPTIONS,
                "max_tokens": parameters["summary_max_tokens"],
            },
            "reader_options": target.OPTIONS,
        }
    rows = []
    try:
        with requests.Session() as local, requests.Session() as remote:
            tags = local.get(config["ollama_url"] + "/api/tags", timeout=(5, 15))
            tags.raise_for_status()
            model = next(
                m
                for m in tags.json()["models"]
                if m["name"] == config["embedding_model"]
            )
            if not model.get("digest"):
                raise ValueError("embedding_digest_missing")
            if continuation is not None:
                original = dense.read_json(prior_path)
                if model["digest"] != original["embedding"]["digest"]:
                    raise ValueError("continuation_embedding_digest_mismatch")
            manifest["embedding"] = model
            dense.write_json_atomic(directory / "manifest.json", manifest)
            transport = Transport(
                config,
                journal,
                directory,
                local,
                remote,
                continuation=continuation is not None,
                parameters=parameters,
                cache=cache,
            )

            class Embedding(sdk["embedding_base"]):
                def create_embedding(self, text):
                    return transport.embed(text)

            class Summary(sdk["summary_base"]):
                def summarize(self, context, max_tokens=150):
                    return transport.summarize(context, max_tokens)

            random.seed(42)
            dense.np.random.seed(42)
            embedding = Embedding()
            builder = sdk["builder"](
                sdk["builder_config"](
                    tokenizer=sdk["tokenizer"],
                    max_tokens=3000,
                    num_layers=PARAMETERS["num_layers"],
                    summarization_length=parameters["summary_max_tokens"],
                    summarization_model=Summary(),
                    embedding_models={"BGE": embedding},
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
            payload = serialize_tree(tree, corpus)
            dense.write_json_atomic(directory / "tree.json", payload)
            before = journal.summary()
            reloaded = dense.read_json(directory / "tree.json")
            tree = restore_tree(reloaded, sdk)
            if (
                target.digest(reloaded) != target.digest(payload)
                or before != journal.summary()
            ):
                raise ValueError("reload_changed_tree_or_accounting")
            manifest["tree"] = {
                "sha256": dense.sha256_file(directory / "tree.json"),
                "nodes": len(nodes),
                "leaves": len(leaves),
                "summaries": len(nodes) - len(leaves),
                "layers": {k: len(v) for k, v in layers.items()},
                "reload_model_calls": 0,
            }
            ancestry = validate_tree(reloaded)
            node_levels = {
                n: int(level)
                for level, members in reloaded["layers"].items()
                for n in members
            }
            retriever = sdk["retriever"](
                sdk["retriever_config"](
                    tokenizer=sdk["tokenizer"],
                    top_k=5,
                    selection_mode="top_k",
                    context_embedding_model="BGE",
                    embedding_model=embedding,
                ),
                tree,
            )
            by_label = {row["id"]: row for row in labels}
            for query in queries:
                transport.phase, transport.object_id = "retrieval", query["id"]
                selected, _ = retriever.retrieve_information_collapse_tree(
                    query["question"], 5, 3000
                )
                if not selected:
                    raise ValueError("empty_retrieval")
                passages = [
                    {"title": f"RAPTOR node {n.index}", "text": n.text}
                    for n in selected
                ]
                messages = dense.build_reader_messages(query["question"], passages)
                raw, body = transport.generate(
                    messages, "reader", "reader", query["id"]
                )
                answer, status = dense.extract_target_reader_answer(raw)
                if status != "ok":
                    raise ValueError("reader_answer_extraction_failed")
                label = by_label[query["id"]]
                covered = set().union(*(ancestry[n.index] for n in selected))
                row = {
                    "question_id": query["id"],
                    "node_ids": [n.index for n in selected],
                    "selected_nodes": [
                        {
                            "index": n.index,
                            "level": node_levels[n.index],
                            "kind": "summary" if n.children else "leaf",
                            "utf8_bytes": len(n.text.encode()),
                            "structural_tokens": len(sdk["tokenizer"].encode(n.text)),
                            "leaf_passage_ids": sorted(ancestry[n.index]),
                        }
                        for n in selected
                    ],
                    "passage_recall_at_5": "not comparable",
                    "reader_prompt_version": dense.READER_PROMPT_VERSION,
                    "answer_parser_version": dense.TARGET_ANSWER_PARSER_VERSION,
                    "reader_messages_sha256": target.digest(messages),
                    "model_returned": body.get("model"),
                    "leaf_passage_ids": sorted(covered),
                    "provenance_leaf_count": len(covered),
                    "supporting_provenance_coverage": len(
                        covered & set(label["supporting_ids"])
                    )
                    / len(set(label["supporting_ids"])),
                    "answer": answer,
                    "raw_answer": raw,
                    "usage": body["usage"],
                    "scores": evaluator.answer_scores(
                        answer, [label["answer"], *label.get("answer_aliases", [])]
                    ),
                }
                rows.append(row)
                dense.write_json_atomic(directory / "answers.json", rows)
            manifest["status"] = "completed"
    except Exception as exc:
        manifest["status"] = "failed"
        # Exception strings may contain server diagnostics; preserve those only in private raw.
        manifest["error_type"] = type(exc).__name__
        manifest["error_code"] = (
            str(exc)
            if isinstance(exc, ValueError) and str(exc).replace("_", "").isalnum()
            else "see_private_responses"
        )
    finally:
        manifest["completed_questions"] = len(rows)
        manifest["token_accounting"] = journal.reference()
        if continuation is not None:
            aggregate = summarize([*history, *read_records(journal.path)])
            manifest["aggregate_accounting"] = aggregate
            manifest["aggregate_total"] = None
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        dense.write_json_atomic(directory / "manifest.json", manifest)
    return manifest, directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path, default=target.ROOT / "results/raw/raptor-smoke"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--continuation-prior", type=Path)
    parser.add_argument("--continuation-diagnostic", type=Path)
    parser.add_argument("--repair-from", type=Path)
    args = parser.parse_args()
    if bool(args.continuation_prior) != bool(args.continuation_diagnostic):
        parser.error("Both continuation manifests are required")
    continuation = (
        (args.continuation_prior, args.continuation_diagnostic)
        if args.continuation_prior
        else None
    )
    plan, queries, corpus, labels = prepare(args.data_root)
    if args.repair_from:
        if continuation is None:
            parser.error("Repair requires both historical manifests")
        report = dense.read_json(
            target.ROOT / "results/summary/raptor-continuation.json"
        )
        used = sum(report["new_token_accounting"]["summary"]["known_subtotal"].values())
        plan["parameters"] = {
            **REPAIR_PARAMETERS,
            "token_limit": PARAMETERS["token_limit"] - used,
        }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=True, indent=2))
        return
    for name in ("NUMBA_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    load_dotenv(args.env_file, override=True)
    sdk = load_source(args.source)
    manifest, directory = execute(
        plan,
        queries,
        corpus,
        labels,
        api.settings(os.environ),
        sdk,
        args.output_dir,
        continuation=continuation,
        repair_from=args.repair_from,
    )
    print(
        json.dumps(
            {
                "run_id": manifest["run_id"],
                "status": manifest["status"],
                "directory": str(directory),
                "error_code": manifest.get("error_code"),
            }
        )
    )
    if manifest["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
