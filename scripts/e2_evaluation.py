"""Shared evaluation glue for existing E1 indexes; invoked by run_dense_target.

No indexing entry point. Labels are only accepted by score_result after inference.
"""

import json
import time
from pathlib import Path

from scripts import e1_indexers as indexes
from scripts import evaluate_dense as evaluator
from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts.evaluation_view import ordered_ids_sha256, select_in_view
from scripts.token_accounting import Journal, extract_usage

ROOT = Path(__file__).resolve().parents[1]
VERSION = "e2-shared-e1-v1"
MODEL = "iairlab/qwen3.8-27b"
MESSAGE_BYTES = 32000
QUERY_BYTES = 4096
LIMIT = 3276800  # 80*(32000+1024+2048+512) + 60*(4096+1024+2048).
METHODS = ("dense", "hipporag2", "raptor")
CODE_FILES = (
    "scripts/e2_evaluation.py",
    "scripts/e1_indexers.py",
    "scripts/run_dense.py",
    "scripts/run_dense_target.py",
    "scripts/run_e1.py",
    "scripts/evaluate_dense.py",
    "scripts/answer_parser.py",
    "scripts/token_accounting.py",
    "scripts/run_raptor_smoke.py",
    "scripts/vendor/hipporag2_musique_template.py",
    "scripts/preflight_hipporag_repair_prompts.py",
    "scripts/track_dense.py",
    "scripts/evaluation_view.py",
)


def reader_payload(question, retrieval):
    # Explicit projection: caller labels/additional metadata cannot enter messages.
    passages = [{"title": p["title"], "text": p["text"]} for p in retrieval["passages"]]
    messages = dense.build_reader_messages(question, passages)
    if len(json.dumps(messages, ensure_ascii=False).encode()) > MESSAGE_BYTES:
        raise ValueError("E2_context_overflow_no_truncation")
    return {"model": MODEL, "messages": messages, **target.OPTIONS}


def prepare(e1_plan_path, workspace):
    workspace = Path(workspace).resolve()
    e1_plan_path = Path(e1_plan_path).resolve()
    source = dense.read_json(e1_plan_path)
    datasets = {}
    for dataset in target.DATASETS:
        split = ROOT / f"data/ids/{dataset}_comparison_split.json"
        ids_path = ROOT / f"data/ids/{dataset}_s500.json"
        ids = dense.read_json(ids_path)["question_ids"][:10]
        views = dense.read_json(split)
        if (
            views["source_sha256"] != dense.sha256_file(ids_path)
            or ids != views["signal_tuning_ids"][:10]
            or set(ids)
            & set(views["signal_check_ids"] + views["legacy_holdout_reserved_ids"])
        ):
            raise ValueError("E2_smoke_split_changed")
        directory = Path(source["data_root"]) / f"data/processed/{dataset}"
        # No labels read at preparation or inference. Evaluator opens only selected IDs later.
        corpus = dense.read_json(directory / "corpus.json")
        queries = select_in_view(
            dense.read_json(directory / "queries.json"), ids, "query"
        )
        rows = []
        for method in METHODS:
            row = next(
                r
                for r in source["rows"]
                if (r["dataset"], r["method"]) == (dataset, method)
            )
            loaded = indexes.load_ready_e1(source, row, corpus, workspace)
            manifest = dense.read_json(loaded["directory"] / "manifest.json")
            rows.append(
                {
                    "method": method,
                    "e1_row": {
                        k: row[k]
                        for k in ("method", "dataset", "output", "corpus_fingerprint")
                    },
                    "manifest_sha256": loaded["manifest_sha256"],
                    "artifacts_sha256": target.digest(manifest["artifacts"]),
                    "run_id": manifest["run_id"],
                }
            )
        datasets[dataset] = {
            "question_ids": ids,
            "ordered_ids_sha256": ordered_ids_sha256(ids),
            "queries_sha256": target.digest(queries),
            "corpus_sha256": dense.sha256_file(directory / "corpus.json"),
            "labels_sha256_evaluator_only": dense.sha256_file(
                directory / "labels.json"
            ),
            "split_sha256": dense.sha256_file(split),
            "indexes": rows,
        }
    return {
        "version": VERSION,
        "mode": "smoke10_pending_approval",
        "e1_workspace": str(workspace),
        "e1_plan": str(e1_plan_path),
        "e1_plan_sha256": dense.sha256_file(e1_plan_path),
        "datasets": datasets,
        "code_sha256": {name: dense.sha256_file(ROOT / name) for name in CODE_FILES},
        "hippo_commit": "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff",
        "raptor_commit": indexes.raptor.SOURCE_COMMIT,
        "embedding_digest": source["embedding_digest"],
        "embedding_model": source["embedding_model"],
        "reader_model": MODEL,
        "endpoint": "https://api.duckduck.cloud/v1",
        "embedding_endpoint": "local Ollama /api/embed",
        "reader_options": target.OPTIONS,
        "reader_templates": {
            d: dense.reader_template_sha256() for d in target.DATASETS
        },
        "reader_template_policy": "existing MuSiQue one-shot unchanged for both datasets; not Hotpot-optimized",
        "parser": dense.TARGET_ANSWER_PARSER_VERSION,
        "evaluator": evaluator.METRIC_VERSION,
        "top_k": 5,
        "context_order": "native descending retrieval order; no reranking by gold",
        "message_utf8_bytes_limit": MESSAGE_BYTES,
        "overflow": "stop_without_truncation",
        "query_utf8_bytes_limit": QUERY_BYTES,
        "hippo": {
            "linking_top_k": 5,
            "passage_node_weight": 0.05,
            "damping": 0.5,
            "filter_cap": 512,
            "filter": "pinned DSPyFilter; malformed/transport failure fatal; valid empty -> DPR",
            "query_instruction_mode": "ignored; one normalized BGE vector for fact and passage",
        },
        "max_posts": 140,
        "max_llm_posts": 80,
        "max_embedding_posts": 60,
        "max_combined_tokens": LIMIT,
        "reader_calls": 60,
        "filter_calls": 20,
        "reserve_rule": "UTF8 serialized payload bytes + 2048 + max_tokens; 1024 bytes envelope allowance; conservative reservation, not measured tokenizer counts",
        "attempts_per_request": 1,
        "retry": 0,
        "redirects": 0,
        "timeout": [30, 300],
        "failures": "first transport/unknown/length/empty/malformed/overflow/budget/pin mismatch stops; failed and remaining planned IDs stay in denominator",
        "cache": "same config+method+question+payload; successful terminal body SHA and journal usage required; started/error/unknown never retried",
        "cost": "new physical query usage separate from logical replay and E1 known32601955/unknown61588; no tariffs",
        "tokenizer_cache": {
            "directory": str(workspace / ".cache/tiktoken"),
            "sha256": {
                p.name: dense.sha256_file(p)
                for p in sorted((workspace / ".cache/tiktoken").glob("*"))
                if p.is_file()
            },
        },
        "http_authorized": False,
    }


def verify(plan):
    if plan["version"] != VERSION:
        raise ValueError("E2_plan_version_changed")
    for name, sha in plan["code_sha256"].items():
        if dense.sha256_file(ROOT / name) != sha:
            raise ValueError("E2_code_changed")
    if dense.sha256_file(Path(plan["e1_plan"])) != plan["e1_plan_sha256"]:
        raise ValueError("E2_E1_plan_changed")
    # Rebuild immutable metadata offline, including journal/artifact/corpus checks.
    if prepare(plan["e1_plan"], plan["e1_workspace"]) != plan:
        raise ValueError("E2_plan_or_index_changed")
    return True


class Calls:
    """Existing checked_post/Journal with durable per-payload once claims.

    A crash before a completed checkpoint is deliberately not auto-recoverable.
    Successful checkpoints bind a single finished journal attempt, not just usage.
    """

    def __init__(self, directory, plan, *, run_id, resume=False):
        self.directory, self.plan = Path(directory), plan
        self.directory.mkdir(parents=True, exist_ok=True)
        self.plan_sha = target.digest(plan)
        self.journal = Journal(
            self.directory / "usage.jsonl",
            run_id=run_id,
            method="shared_e2",
            dataset="both",
            resume=resume,
        )

    def call(
        self,
        payload,
        *,
        method,
        dataset,
        qid,
        operation,
        session=None,
        url=None,
        headers=None,
    ):
        kind = "embedding" if operation == "query_embedding" else "llm"
        provider = "local_ollama" if kind == "embedding" else "target_api"
        key = target.digest(
            {
                "plan": self.plan_sha,
                "method": method,
                "dataset": dataset,
                "qid": qid,
                "operation": operation,
                "payload": payload,
            }
        )
        path = self.directory / f"{key}.json"
        from scripts.token_accounting import read_records

        records = read_records(self.journal.path)
        if records.corrupt_tail:
            raise ValueError("E2_corrupt_journal_no_retry")
        if path.exists():
            saved = dense.read_json(path)
            finished = [
                r
                for r in records
                if r.get("object_id") == key and r["event"] == "finished"
            ]
            if (
                saved.get("status") != "completed"
                or saved.get("key") != key
                or saved.get("response_sha256") != target.digest(saved.get("response"))
                or len(finished) != 1
                or finished[0]["status"] != "success"
                or finished[0]["usage_status"] != "complete"
                or extract_usage(saved["response"], kind, provider)
                != {
                    k: finished[0][k]
                    for k in (
                        "llm_input_tokens",
                        "llm_output_tokens",
                        "embedding_input_tokens",
                    )
                }
            ):
                raise ValueError("E2_uncertain_or_changed_checkpoint_no_retry")
            return saved["response"], True
        summary = self.journal.summary()
        if not summary["complete"]:
            raise ValueError("E2_unknown_journal_no_retry")
        physical = [r for r in records if r["event"] == "started"]
        cap = self.plan[
            "max_embedding_posts" if kind == "embedding" else "max_llm_posts"
        ]
        if (
            len(physical) >= self.plan["max_posts"]
            or sum(r["kind"] == kind for r in physical) >= cap
        ):
            raise ValueError("E2_POST_cap_exceeded")
        if kind == "llm" and (
            payload.get("model") != MODEL
            or any(payload.get(k) != v for k, v in target.OPTIONS.items())
            or len(json.dumps(payload["messages"], ensure_ascii=False).encode())
            > MESSAGE_BYTES
        ):
            raise ValueError("E2_LLM_payload_contract")
        if kind == "embedding" and (
            len(payload["input"].encode()) > QUERY_BYTES
            or payload != embedding_payload(self.plan, payload["input"])
        ):
            raise ValueError("E2_embedding_payload_contract")
        if (
            len(json.dumps(payload, ensure_ascii=False).encode())
            > (QUERY_BYTES if kind == "embedding" else MESSAGE_BYTES) + 1024
        ):
            raise ValueError("E2_payload_envelope_overflow")
        operation_cap = {"reader": 60, "filter": 20, "query_embedding": 60}[operation]
        if sum(r["operation"] == operation for r in physical) >= operation_cap:
            raise ValueError("E2_operation_cap_exceeded")
        if session is None:
            raise ValueError("E2_cache_miss_HTTP_forbidden")
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"status": "started", "key": key}, stream)
            stream.flush()
            import os

            os.fsync(stream.fileno())
        body = target.checked_post(
            session,
            url,
            payload,
            self.journal,
            phase="reader" if operation == "reader" else "retrieval",
            operation=operation,
            provider=provider,
            model=payload["model"],
            kind=kind,
            object_id=key,
            headers=headers,
            response_path=self.directory / f"{key}.response.json",
            token_limit=self.plan["max_combined_tokens"],
            timeout=(30, 300),
        )
        # A stopped-but-invalid answer keeps its measured usage; it cannot be
        # replayed as a successful completed response.
        try:
            if kind == "llm":
                completed_text(body)
            elif len(body["embeddings"]) != 1 or len(body["embeddings"][0]) != 1024:
                raise ValueError("E2_embedding_shape_invalid")
        except Exception:
            dense.write_json_atomic(
                path,
                {
                    "status": "failed",
                    "key": key,
                    "response": body,
                    "response_sha256": target.digest(body),
                },
            )
            raise
        # Persist usage before semantic/parser checks; failed raw remains accessible.
        dense.write_json_atomic(
            path,
            {
                "status": "completed",
                "key": key,
                "response": body,
                "response_sha256": target.digest(body),
            },
        )
        return body, False


def embedding_payload(plan, question):
    return {
        "model": plan["embedding_model"],
        "input": question,
        "truncate": False,
        "options": {"num_ctx": 4096, "num_batch": 4096},
    }


def completed_text(body):
    choice = body["choices"][0]
    text = choice["message"]["content"]
    usage = extract_usage(body, "llm", "target_api")
    if (
        choice.get("finish_reason") != "stop"
        or not isinstance(text, str)
        or not text.strip()
        or any(usage[k] is None for k in ("llm_input_tokens", "llm_output_tokens"))
    ):
        raise ValueError("E2_incomplete_or_unknown_response")
    return text


def question_result(
    plan, loaded, query, calls, *, dataset, method, send=None, hippo=None, sdk=None
):
    """One common measured retrieval/reader path, synthetic/cache or approved transport."""
    began = time.perf_counter()
    stages, cache, operations = {}, {}, []
    result = {
        "question_id": query["id"],
        "question": query["question"],
        "dataset": dataset,
        "method": method,
        "config_sha256": target.digest(plan),
        "index_manifest_sha256": loaded["manifest_sha256"],
        "status": "failed",
        "answer": "",
        "raw_answer": None,
    }

    def call(payload, operation):
        options = send(operation) if send else {}
        t = time.perf_counter()
        attempt = {
            "operation": operation,
            "request_payload_sha256": target.digest(payload),
            "journal_object_id": target.digest(
                {
                    "plan": calls.plan_sha,
                    "method": method,
                    "dataset": dataset,
                    "qid": query["id"],
                    "operation": operation,
                    "payload": payload,
                }
            ),
            "model": payload["model"],
            "status": "failed",
        }
        try:
            body, hit = calls.call(
                payload,
                method=method,
                dataset=dataset,
                qid=query["id"],
                operation=operation,
                **options,
            )
            cache[operation] = hit
            attempt.update(
                status="completed",
                cache_hit=hit,
                logical_usage=extract_usage(
                    body,
                    "embedding" if operation == "query_embedding" else "llm",
                    "local_ollama" if operation == "query_embedding" else "target_api",
                ),
                response_sha256=target.digest(body),
                returned_model=body.get("model"),
            )
            return body
        finally:
            from scripts.token_accounting import read_records

            finished = [
                r
                for r in read_records(calls.journal.path)
                if r.get("object_id") == attempt["journal_object_id"]
                and r["event"] == "finished"
            ]
            attempt["physical_attempted"] = bool(finished)
            if finished and "logical_usage" not in attempt:
                attempt["logical_usage"] = {
                    k: finished[-1][k]
                    for k in (
                        "llm_input_tokens",
                        "llm_output_tokens",
                        "embedding_input_tokens",
                    )
                }
                attempt["physical_status"] = finished[-1]["status"]
            attempt["client_seconds"] = time.perf_counter() - t
            operations.append(attempt)

    stage_name = "query_embedding"
    t = time.perf_counter()
    try:
        response = call(embedding_payload(plan, query["question"]), "query_embedding")
        vectors = response["embeddings"]
        if len(vectors) != 1:
            raise ValueError("E2_query_embedding_shape")
        stages["query_embedding"] = time.perf_counter() - t

        def infer(messages):
            return completed_text(
                call({"model": MODEL, "messages": messages, **target.OPTIONS}, "filter")
            )

        stage_name = "retrieval"
        t = time.perf_counter()
        if method == "hipporag2":
            rag = hippo(infer)
            retrieval = indexes.retrieve_hippo_query_only(
                loaded, rag, query["question"], vectors[0], plan["embedding_digest"]
            )
        else:
            retrieval = indexes.retrieve_ready_e1(
                loaded,
                query["question"],
                vectors[0],
                embedding_digest=plan["embedding_digest"],
                sdk=sdk,
            )
        stages["retrieval"] = time.perf_counter() - t
        result["retrieval"] = retrieval
        payload = reader_payload(query["question"], retrieval)
        result["reader_request_sha256"] = target.digest(payload)
        result["reader_message_utf8_bytes"] = len(
            json.dumps(payload["messages"], ensure_ascii=False).encode()
        )
        stage_name = "reader"
        t = time.perf_counter()
        response = call(payload, "reader")
        stages["reader"] = time.perf_counter() - t
        raw = completed_text(response)
        result["raw_answer"] = raw
        answer, status = dense.extract_target_reader_answer(raw)
        if status != "ok":
            raise ValueError("E2_reader_parser_failed")
        result.update(status="completed", answer=answer)
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "reason": str(exc)}
    finally:
        if stage_name not in stages:
            stages[stage_name] = time.perf_counter() - t
        result.update(
            stage_seconds=stages,
            wall_seconds=time.perf_counter() - began,
            cache_hits=cache,
            operations=operations,
            token_accounting=calls.journal.reference(),
        )
    return result


def score_result(result, label):
    if result["question_id"] != label["id"]:
        raise ValueError("E2_evaluator_ID_mismatch")
    scores = (
        evaluator.answer_scores(
            result["answer"], [label["answer"], *label.get("answer_aliases", [])]
        )
        if result["status"] == "completed"
        else {"em": 0.0, "f1": 0.0}
    )
    retrieval = result.get("retrieval", {})
    ids = retrieval.get("source_ids", [])
    scores["passage_recall_at_5"] = (
        evaluator.recall_at_k(ids, label["supporting_ids"], 5)
        if result["method"] != "raptor"
        else None
    )
    scores["supporting_provenance_coverage"] = len(
        set(ids) & set(label["supporting_ids"])
    ) / len(set(label["supporting_ids"]))
    return scores


def execute(
    plan_path,
    directory,
    method,
    *,
    approved_sha=None,
    config=None,
    hippo_source=None,
    raptor_source=None,
):
    """Sequential existing-runner extension. No HTTP unless exact plan approved.

    Invoke once per method in its pinned SDK environment, same directory/plan.
    A durable common claim prevents another directory evading the aggregate caps.
    """
    import os
    import uuid
    from scripts import run_e1 as e1

    plan_path, directory = Path(plan_path).resolve(), Path(directory).resolve()
    plan = dense.read_json(plan_path)
    verify(plan)
    if approved_sha != dense.sha256_file(plan_path) or config is None:
        raise ValueError("E2_exact_plan_approval_required_before_HTTP")
    if (
        config["model"] != MODEL
        or config["base_url"] != "https://api.duckduck.cloud/v1"
        or config["embedding_model"] != plan["embedding_model"]
    ):
        raise ValueError("E2_endpoint_or_model_changed")
    # SDK and artifact gates happen before sessions/first HTTP.
    if not plan["tokenizer_cache"]["sha256"]:
        raise ValueError("E2_offline_tokenizer_cache_required")
    os.environ["TIKTOKEN_CACHE_DIR"] = plan["tokenizer_cache"]["directory"]
    sdk = indexes.raptor.load_source(raptor_source) if method == "raptor" else None
    if method == "hipporag2":
        from scripts.preflight_hipporag_repair_prompts import (
            verify_target_prompt_installation,
        )

        verify_target_prompt_installation(hippo_source)
    claim = (
        Path(plan["e1_workspace"]) / ".cache" / f"e2-{target.digest(plan)}.claim.json"
    )
    if claim.exists():
        if dense.read_json(claim)["directory"] != str(directory):
            raise ValueError("E2_plan_already_claimed_in_other_directory")
    else:
        with claim.open("x", encoding="utf-8") as stream:
            json.dump({"directory": str(directory)}, stream)
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "running.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
    started_work = False
    try:
        mp = directory / "manifest.json"
        if mp.exists():
            manifest = dense.read_json(mp)
            if (
                manifest["plan_sha256"] != target.digest(plan)
                or manifest["status"] == "failed"
            ):
                raise ValueError("E2_failed_or_changed_run_no_automatic_resume")
            if e1.journal_snapshot(directory / "usage.jsonl")[1]:
                raise ValueError("E2_incomplete_journal_no_retry")
            calls = Calls(directory, plan, run_id=manifest["run_id"], resume=True)
        else:
            manifest = {
                "run_id": str(uuid.uuid4()),
                "plan_sha256": target.digest(plan),
                "status": "running",
                "results": {},
            }
            calls = Calls(directory, plan, run_id=manifest["run_id"])
            dense.write_json_atomic(mp, manifest)
        started_work = True
        source = dense.read_json(Path(plan["e1_plan"]))
        # Fully load BOTH dataset indexes before first HTTP, including graph/store
        # compatibility and native lookup preparation (no model calls).
        preloaded = {}
        for dataset, data in plan["datasets"].items():
            raw = Path(source["data_root"]) / f"data/processed/{dataset}"
            corpus = dense.read_json(raw / "corpus.json")
            pinned = next(r for r in data["indexes"] if r["method"] == method)
            loaded = indexes.load_ready_e1(
                source, pinned["e1_row"], corpus, Path(plan["e1_workspace"])
            )
            if loaded["manifest_sha256"] != pinned["manifest_sha256"]:
                raise ValueError("E2_manifest_changed")

            def no_inference(messages):
                raise ValueError("E2_loading_must_not_infer")

            rag = (
                indexes.load_hippo_query_only(loaded, hippo_source, no_inference)
                if method == "hipporag2"
                else None
            )
            preloaded[dataset] = (loaded, rag)
        # Restore no indexes; all artifacts are immutable and already verified.
        with target.requests.Session() as local, target.requests.Session() as remote:
            tags = local.get(
                config["ollama_url"] + "/api/tags",
                timeout=(30, 300),
                allow_redirects=False,
            )
            tags.raise_for_status()
            if not any(
                r.get("name") == plan["embedding_model"]
                and r.get("digest") == plan["embedding_digest"]
                for r in tags.json().get("models", [])
            ):
                raise ValueError("E2_live_embedding_digest_changed")

            def send(operation):
                if operation == "query_embedding":
                    return {
                        "session": local,
                        "url": config["ollama_url"] + "/api/embed",
                    }
                return {
                    "session": remote,
                    "url": config["base_url"] + "/chat/completions",
                    "headers": {"Authorization": "Bearer " + config["key"]},
                }

            for dataset, data in plan["datasets"].items():
                raw = Path(source["data_root"]) / f"data/processed/{dataset}"
                loaded, rag = preloaded[dataset]

                def hippo(infer):
                    nonlocal rag
                    if rag is None:
                        rag = indexes.load_hippo_query_only(loaded, hippo_source, infer)
                    else:
                        rag.extraction_llm.handler = infer
                    return rag

                queries = select_in_view(
                    dense.read_json(raw / "queries.json"), data["question_ids"], "query"
                )
                for query in queries:
                    key = target.digest([dataset, method, query["id"]])
                    result_path = directory / f"question-{key}.json"
                    if key in manifest["results"]:
                        if dense.sha256_file(result_path) != manifest["results"][key]:
                            raise ValueError("E2_saved_result_changed")
                        # Validate every underlying completed request on replay;
                        # no transport is supplied, so a missing checkpoint is fatal.
                        replay = question_result(
                            plan,
                            loaded,
                            query,
                            calls,
                            dataset=dataset,
                            method=method,
                            hippo=hippo,
                            sdk=sdk,
                        )
                        if (
                            replay["status"] != "completed"
                            or replay["answer"]
                            != dense.read_json(result_path)["answer"]
                        ):
                            raise ValueError("E2_result_replay_not_compatible")
                        continue
                    result = question_result(
                        plan,
                        loaded,
                        query,
                        calls,
                        dataset=dataset,
                        method=method,
                        send=send,
                        hippo=hippo,
                        sdk=sdk,
                    )
                    result["run_id"] = manifest["run_id"]
                    dense.write_json_atomic(result_path, result)
                    manifest["results"][key] = dense.sha256_file(result_path)
                    manifest["token_accounting"] = calls.journal.reference()
                    if result["status"] != "completed":
                        manifest["status"] = "failed"
                    dense.write_json_atomic(mp, manifest)
                    if result["status"] != "completed":
                        return manifest
                    time.sleep(4)
        manifest["status"] = (
            "completed"
            if len(manifest["results"]) == 60
            else "partial_completed_methods"
        )
        manifest["token_accounting"] = calls.journal.reference()
        dense.write_json_atomic(mp, manifest)
        return manifest
    except Exception as exc:
        if started_work:
            manifest["status"] = "failed"
            manifest["error"] = {"type": type(exc).__name__, "reason": str(exc)}
            manifest["token_accounting"] = calls.journal.reference()
            dense.write_json_atomic(mp, manifest)
        raise
    finally:
        lock.unlink()


def summary(plan, directory):
    """Score only frozen development IDs. Denominator includes every planned ID.

    Returns six aggregate rows plus private per-question scores/tracking payloads;
    no labels are returned to generation. This does not export to services.
    """
    from scripts.token_accounting import verified_reference

    directory = Path(directory)
    manifest = dense.read_json(directory / "manifest.json")
    if manifest["plan_sha256"] != target.digest(plan):
        raise ValueError("E2_summary_config_changed")
    reference = verified_reference(manifest, directory / "manifest.json")
    if reference["status"] != "verified":
        raise ValueError("E2_summary_journal_changed")
    # verified_reference keeps a Path for local consumers; reports are JSON artifacts.
    reference = {**reference, "path": str(reference["path"])}
    source = dense.read_json(Path(plan["e1_plan"]))
    table, details = [], []
    for dataset, data in plan["datasets"].items():
        label_path = Path(source["data_root"]) / f"data/processed/{dataset}/labels.json"
        if dense.sha256_file(label_path) != data["labels_sha256_evaluator_only"]:
            raise ValueError("E2_labels_changed")
        labels = {
            r["id"]: r
            for r in select_in_view(
                dense.read_json(label_path), data["question_ids"], "label"
            )
        }
        for method in METHODS:
            scored = []
            for qid in data["question_ids"]:
                key = target.digest([dataset, method, qid])
                path = directory / f"question-{key}.json"
                if key in manifest["results"]:
                    if dense.sha256_file(path) != manifest["results"][key]:
                        raise ValueError("E2_result_changed")
                    result = dense.read_json(path)
                else:
                    result = {
                        "question_id": qid,
                        "method": method,
                        "dataset": dataset,
                        "status": "not_attempted_after_stop",
                        "answer": "",
                    }
                scores = score_result(result, labels[qid])
                scored.append({**result, "metrics": scores})
            details.extend(scored)
            complete = [r for r in scored if r["status"] == "completed"]
            operations = [op for r in scored for op in r.get("operations", [])]
            usage = {}
            for op in operations:
                bucket = usage.setdefault(
                    op["model"],
                    {
                        "known_subtotal": {
                            "llm_input_tokens": 0,
                            "llm_output_tokens": 0,
                            "embedding_input_tokens": 0,
                        },
                        "unknown_operations": 0,
                        "complete": True,
                    },
                )
                applicable = (
                    ("embedding_input_tokens",)
                    if op["operation"] == "query_embedding"
                    else ("llm_input_tokens", "llm_output_tokens")
                )
                values = op.get("logical_usage", {})
                if op.get("physical_attempted") and any(
                    values.get(k) is None for k in applicable
                ):
                    bucket["unknown_operations"] += 1
                    bucket["complete"] = False
                for k, v in values.items():
                    if v is not None:
                        bucket["known_subtotal"][k] += v
            table.append(
                {
                    "dataset": dataset,
                    "method": method,
                    "planned": len(scored),
                    "completed": len(complete),
                    "completion_rate": len(complete) / len(scored),
                    "em": sum(r["metrics"]["em"] for r in scored) / len(scored),
                    "f1": sum(r["metrics"]["f1"] for r in scored) / len(scored),
                    "passage_recall_at_5": sum(
                        r["metrics"]["passage_recall_at_5"] for r in scored
                    )
                    / len(scored)
                    if method != "raptor"
                    else None,
                    "provenance_coverage": sum(
                        r["metrics"]["supporting_provenance_coverage"] for r in scored
                    )
                    / len(scored),
                    "mean_completed_seconds": sum(r["wall_seconds"] for r in complete)
                    / len(complete)
                    if complete
                    else None,
                    "logical_usage_by_model": usage,
                    "limitations": "smoke10 development, not independent quality evidence; failed operation usage in global physical journal",
                }
            )
    return {
        "run_id": manifest["run_id"],
        "rows": table,
        "question_results": details,
        "physical_query_accounting": reference,
        "historical_E1_excluded": True,
    }


def tracking_payload(plan, directory, dataset, method):
    """Adapt shared records to the existing MLflow/Langfuse exporters, offline.

    Common journal belongs to this whole smoke run, not six extra costs; partition
    its records by exact question request identities for each exported config.
    """
    from scripts.token_accounting import read_records, summarize

    report = summary(plan, directory)
    rows = [
        r
        for r in report["question_results"]
        if r["dataset"] == dataset and r["method"] == method
    ]
    # Tracking preparation includes failed IDs; post-hoc export does not perform QA.
    questions = []
    keys = set()
    for row in rows:
        operations = row.get("operations", [])
        for op in operations:
            keys.add(op.get("journal_object_id"))
        reader = next((o for o in operations if o["operation"] == "reader"), {})
        embedding = next(
            (o for o in operations if o["operation"] == "query_embedding"), {}
        )
        row.update(
            top_k=5,
            generation_model={"name": MODEL},
            embedding_model={
                "name": plan["embedding_model"],
                "digest": plan["embedding_digest"],
            },
            reader_prompt_version=dense.READER_PROMPT_VERSION,
            prompt_tokens=reader.get("logical_usage", {}).get("llm_input_tokens"),
            completion_tokens=reader.get("logical_usage", {}).get("llm_output_tokens"),
            query_embedding_prompt_tokens=embedding.get("logical_usage", {}).get(
                "embedding_input_tokens"
            ),
            query_embedding_client_seconds=embedding.get("client_seconds"),
            generation_wall_seconds=reader.get("client_seconds"),
        )
        row.setdefault("question", "not attempted after stop")
        questions.append(
            {
                "row": row,
                "retrieved_passages": row.get("retrieval", {}).get("passages", []),
            }
        )
    phases = summarize(
        [
            r
            for r in read_records(Path(directory) / "usage.jsonl")
            if r.get("object_id") in keys
        ]
    )
    aggregate = next(
        r for r in report["rows"] if r["dataset"] == dataset and r["method"] == method
    )
    manifest = {
        "mode": "e2-smoke10",
        "generation": {
            "model": {"name": MODEL, "digest": None},
            "reader_prompt_version": dense.READER_PROMPT_VERSION,
        },
        "embedding": {
            "model": {
                "name": plan["embedding_model"],
                "digest": plan["embedding_digest"],
            }
        },
        "token_accounting": dense.read_json(Path(directory) / "manifest.json")[
            "token_accounting"
        ],
    }
    return {
        "system": method,
        "trace_name": "e2-shared-query-run",
        "dataset": dataset,
        "run_id": report["run_id"] + "-" + dataset + "-" + method,
        "rows": rows,
        "questions": questions,
        "manifest": manifest,
        "metrics": {
            "questions_evaluated": len(rows),
            "top_k": 5,
            "em": aggregate["em"],
            "token_f1": aggregate["f1"],
            "recall_at_k": aggregate["passage_recall_at_5"],
        },
        "token_accounting": {
            "status": "verified",
            "summary": phases,
            "scope": "partition of common query journal; E1 excluded",
        },
    }


def write_report(plan_path, directory, public_prefix):
    """Generate private evaluation and a safe public table from immutable results.

    A failed smoke publishes technical coverage, not a fabricated six-way score.
    Does not check current execution code pins or enable resume: it reports the
    original pinned runtime and preserves its failed manifest/claims verbatim.
    """
    from collections import Counter
    from scripts.token_accounting import read_records

    plan_path, directory, prefix = map(Path, (plan_path, directory, public_prefix))
    plan = dense.read_json(plan_path)
    manifest_path = directory / "manifest.json"
    manifest_sha = dense.sha256_file(manifest_path)
    manifest = dense.read_json(manifest_path)
    report = summary(plan, directory)
    dense.write_json_atomic(directory / "evaluation.json", report)
    records = read_records(directory / "usage.jsonl")
    started = [r for r in records if r["event"] == "started"]
    finished = [r for r in records if r["event"] == "finished"]
    rows = []
    for dataset, data in plan["datasets"].items():
        for method in METHODS:
            selected = [
                r
                for r in report["question_results"]
                if r["dataset"] == dataset and r["method"] == method
            ]
            counts = Counter(r["status"] for r in selected)
            rows.append(
                {
                    "dataset": dataset,
                    "method": method,
                    "planned": len(data["question_ids"]),
                    "completed": counts["completed"],
                    "failed": counts["failed"],
                    "not_attempted_after_stop": counts["not_attempted_after_stop"],
                }
            )
    failures = []
    for result in report["question_results"]:
        if result["status"] != "failed":
            continue
        failure = {
            "dataset": result["dataset"],
            "method": result["method"],
            "question_id": result["question_id"],
            "error": result.get("error"),
            "partial_response_accepted": False,
        }
        for op in result.get("operations", []):
            response = directory / f"{op['journal_object_id']}.response.json"
            if op["status"] != "failed" or not response.exists():
                continue
            body = dense.read_json(response)
            failure.update(
                operation=op["operation"],
                response_sha256=dense.sha256_file(response),
                finish_reason=body.get("choices", [{}])[0].get("finish_reason"),
                reported_usage=body.get("usage"),
            )
        failures.append(failure)
    known = report["physical_query_accounting"]["summary"]["known_subtotal"]
    outcome_counts = Counter(r["status"] for r in report["question_results"])
    safe = {
        "schema_version": 1,
        "kind": "e2_smoke10",
        "status": manifest["status"],
        "run_id": manifest["run_id"],
        "plan_sha256": dense.sha256_file(plan_path),
        "execution_code_pins": plan.get("code_sha256", {}),
        "manifest_sha256": manifest_sha,
        "journal_sha256": dense.sha256_file(directory / "usage.jsonl"),
        "raw_directory": str(directory),
        "rows": rows,
        "outcome_counts": dict(outcome_counts),
        "model_posts": len(started),
        "llm_posts": sum(r["kind"] == "llm" for r in started),
        "embedding_posts": sum(r["kind"] == "embedding" for r in started),
        "known_query_tokens": known,
        "known_combined_query_tokens": sum(known.values()),
        "query_cost_complete": report["physical_query_accounting"]["summary"][
            "complete"
        ],
        "new_unknown_attempts": sum(r["usage_status"] != "complete" for r in finished),
        "unfinished_attempts": len(started) - len(finished),
        "remaining_original_tokens": plan["max_combined_tokens"] - sum(known.values()),
        "remaining_original_posts": plan["max_posts"] - len(started),
        "failures": failures,
        "comparative_metrics": report["rows"]
        if manifest["status"] == "completed"
        else None,
        "tracking": dense.read_json(directory / "tracking/receipt.json")
        if (directory / "tracking/receipt.json").exists()
        else None,
        "continuation_authorized": False,
        "e1_historical_cost_excluded": True,
        "limitations": "development smoke only; failed run is not a completed comparison; E1 unknown61588 remains separate",
    }
    dense.write_json_atomic(prefix.with_suffix(".json"), safe)
    lines = [
        "# E2 smoke10: " + manifest["status"],
        "",
        f"Run `{manifest['run_id']}`; plan `{safe['plan_sha256']}`.",
        "",
        "| Датасет | Метод | План | Completed | Failed | Не запускались |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['dataset']} | {r['method']} | {r['planned']} | {r['completed']} | {r['failed']} | {r['not_attempted_after_stop']} |"
        )
    lines.extend(
        [
            "",
            f"Модельных POST: {safe['model_posts']} ({safe['llm_posts']}LLM/{safe['embedding_posts']}local BGE).",
            f"Known LLM input={known['llm_input_tokens']}, output={known['llm_output_tokens']}, local embedding={known['embedding_input_tokens']}; всего {sum(known.values())}.",
            f"Query cost_complete={safe['query_cost_complete']}; unknown={safe['new_unknown_attempts']}; unfinished={safe['unfinished_attempts']}.",
            "",
            f"Остаток исходных caps: {safe['remaining_original_tokens']}tokens/{safe['remaining_original_posts']}POST. Это не допуск к новому run после остановки.",
        ]
    )
    for f in failures:
        lines.extend(
            [
                "",
                f"Первый stop: {f['method']}/{f['dataset']}/{f['question_id']}; {f.get('operation')} finish_reason={f.get('finish_reason')}. Partial response не принят.",
            ]
        )
    lines.extend(
        [
            "",
            "При failed сравнительные F1/EM не публикуются: это техническая остановка, не полный E2. Полная declared-denominator оценка выбранных tuning IDs сохранена только в private evaluation.json.",
            "E1 known32601955/unknown reserve61588 и все6индексов сохранены отдельно. В Git нет gold/сырого ответа/корпуса. Refs #14; без pilot200/QA holdout/merge.",
            "",
            f"Данные: [{prefix.name}.json]({prefix.name}.json). Private raw: `{directory}`.",
        ]
    )
    prefix.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert dense.sha256_file(manifest_path) == manifest_sha
    return safe
