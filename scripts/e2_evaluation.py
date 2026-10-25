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
    "scripts/e2_pilot.py",
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


def configured_reader_payload(plan, question, retrieval):
    return (
        answer_only_payload(question, retrieval)
        if plan.get("reader_version") == "shared-answer-only-v1"
        else reader_payload(question, retrieval)
    )


def parse_reader(plan, raw):
    answer, status = dense.extract_target_reader_answer(raw)
    if plan.get("reader_version") == "shared-answer-only-v1":
        if status != "ok" or raw.strip() != "Answer: " + answer:
            raise ReaderCaseFailure("reader_not_single_answer_line")
        words = answer.split()
        if any(
            words[i : i + 8] == words[i + 8 : i + 16] == words[i + 16 : i + 24]
            for i in range(len(words) - 23)
        ):
            raise ReaderCaseFailure("reader_repeated_8word_block_three_times")
    return answer, status


def prepare(e1_plan_path, workspace, *, pilot=False):
    workspace = Path(workspace).resolve()
    e1_plan_path = Path(e1_plan_path).resolve()
    source = dense.read_json(e1_plan_path)
    datasets = {}
    for dataset in target.DATASETS:
        split = ROOT / f"data/ids/{dataset}_comparison_split.json"
        ids_path = ROOT / f"data/ids/{dataset}_s500.json"
        s500 = dense.read_json(ids_path)
        ids = s500["views"]["pilot200"] if pilot else s500["question_ids"][:10]
        views = dense.read_json(split)
        if (
            views["source_sha256"] != dense.sha256_file(ids_path)
            or ids != views["signal_tuning_ids"][: len(ids)]
            or (
                pilot
                and (
                    len(ids) != 200
                    or len(set(ids)) != 200
                    or ids != views["pilot200_ids"]
                    or ids != s500["question_ids"][:200]
                )
            )
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


CONTINUATION_VERSION = "e2-shared-e1-v2"
OUTCOME_POLICY = "reader_known_response_failure_continue_v2"
PARENT_RUNTIME = "5dea658aec9e8f5c4a7dd1bc441bb690608a1294"


def case_key(dataset, method, qid):
    return target.digest([dataset, method, qid])


def verify_parent_code(parent):
    """Execution policy/report code may evolve; generation functions may not."""
    import ast
    import subprocess

    changed = {
        "scripts/e2_evaluation.py",
        "scripts/run_dense_target.py",
        "scripts/track_dense.py",
    }
    for name, sha in parent["code_sha256"].items():
        if name not in changed and dense.sha256_file(ROOT / name) != sha:
            raise ValueError("E2_incompatible_parent_component: " + name)
    original = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "-C",
            str(ROOT),
            "show",
            PARENT_RUNTIME + ":scripts/e2_evaluation.py",
        ]
    )
    old_tree = ast.parse(original.decode("utf-8"))
    current_tree = ast.parse(
        (ROOT / "scripts/e2_evaluation.py").read_text(encoding="utf-8")
    )
    for name in ("reader_payload", "embedding_payload"):

        def function(tree):
            return ast.dump(
                next(
                    n
                    for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == name
                )
            )

        if function(old_tree) != function(current_tree):
            raise ValueError("E2_incompatible_parent_generation_function")


def verify_saved_case(plan, directory, result, records):
    """Bind result to exact inputs, response/checkpoint SHA and physical usage."""
    directory = Path(directory)
    dataset, method, qid = (result[k] for k in ("dataset", "method", "question_id"))
    if (
        result["config_sha256"] != target.digest(plan)
        or qid not in plan["datasets"][dataset]["question_ids"]
    ):
        raise ValueError("E2_incompatible_result_identity")
    pin = next(r for r in plan["datasets"][dataset]["indexes"] if r["method"] == method)
    if result["index_manifest_sha256"] != pin["manifest_sha256"]:
        raise ValueError("E2_result_index_changed")
    if plan.get("version") == "e2-pilot200-v1":
        from scripts import e2_pilot

        e2_pilot.verify_reuse_result(plan, result)
    for op in result["operations"]:
        if op.get("reused"):
            continue  # Bound to the frozen source journal/body by verify_reuse_result.
        key = op["journal_object_id"]
        saved = dense.read_json(directory / f"{key}.json")
        response = dense.read_json(directory / f"{key}.response.json")
        if (
            saved.get("key") != key
            or saved.get("response_sha256") != target.digest(response)
            or saved.get("response") != response
        ):
            raise ValueError("E2_result_checkpoint_changed")
        terminal = [
            r for r in records if r["event"] == "finished" and r.get("object_id") == key
        ]
        if (
            len(terminal) != 1
            or terminal[0]["status"] != "success"
            or terminal[0]["usage_status"] != "complete"
        ):
            raise ValueError("E2_uncertain_result_no_resume")
        kind = "embedding" if op["operation"] == "query_embedding" else "llm"
        usage = extract_usage(
            response, kind, "local_ollama" if kind == "embedding" else "target_api"
        )
        if usage != {k: terminal[0][k] for k in usage} or usage != op["logical_usage"]:
            raise ValueError("E2_result_usage_changed")
        payload = (
            embedding_payload(plan, result["question"])
            if kind == "embedding"
            else configured_reader_payload(
                plan, result["question"], result["retrieval"]
            )
            if op["operation"] == "reader"
            else None
        )
        if payload is not None:
            expected = target.digest(
                {
                    "plan": target.digest(plan),
                    "method": method,
                    "dataset": dataset,
                    "qid": qid,
                    "operation": op["operation"],
                    "payload": payload,
                }
            )
            if (
                key != expected
                or target.digest(payload) != op["request_payload_sha256"]
            ):
                raise ValueError("E2_result_payload_changed")
        if op["operation"] == "reader":
            try:
                raw = reader_text(response)
                answer, status = parse_reader(plan, raw)
                if status != "ok":
                    raise ReaderCaseFailure("reader_parser_failed")
            except ReaderCaseFailure:
                if result["status"] not in ("failed", "attempted_failed") or result.get(
                    "answer"
                ):
                    raise ValueError("E2_failed_reader_promoted") from None
            else:
                if result["status"] != "completed" or result["answer"] != answer:
                    raise ValueError("E2_reader_result_changed")


def parent_snapshot(plan_path, directory):
    from scripts.token_accounting import verified_reference, read_records

    plan_path, directory = Path(plan_path).resolve(), Path(directory).resolve()
    parent = dense.read_json(plan_path)
    manifest_path = directory / "manifest.json"
    manifest = dense.read_json(manifest_path)
    reference = verified_reference(manifest, manifest_path)
    if (
        manifest["status"] != "failed"
        or manifest["plan_sha256"] != target.digest(parent)
        or reference["status"] != "verified"
        or not reference["summary"]["complete"]
        or (directory / "running.lock").exists()
        or parent.get("parent_run")
    ):
        raise ValueError("E2_parent_not_terminal_known_single_run")
    verify_parent_code(parent)
    claim = (
        Path(parent["e1_workspace"])
        / ".cache"
        / f"e2-{target.digest(parent)}.claim.json"
    )
    if dense.read_json(claim)["directory"] != str(directory):
        raise ValueError("E2_parent_claim_changed")
    records = read_records(directory / "usage.jsonl")
    files = {
        str(p): dense.sha256_file(p)
        for p in (plan_path, manifest_path, directory / "usage.jsonl", claim)
    }
    cases = {}
    seen_operations = set()
    for key, sha in manifest["results"].items():
        path = directory / f"question-{key}.json"
        if dense.sha256_file(path) != sha:
            raise ValueError("E2_parent_result_changed")
        result = dense.read_json(path)
        if key != case_key(result["dataset"], result["method"], result["question_id"]):
            raise ValueError("E2_parent_case_key_changed")
        verify_saved_case(parent, directory, result, records)
        if result["status"] == "failed":
            reader = next(
                op for op in result["operations"] if op["operation"] == "reader"
            )
            response = dense.read_json(
                directory / f"{reader['journal_object_id']}.response.json"
            )
            if response["choices"][0]["finish_reason"] != "length":
                raise ValueError("E2_parent_stop_not_known_reader_length")
        cases[key] = {
            "path": str(path),
            "sha256": sha,
            "dataset": result["dataset"],
            "method": result["method"],
            "question_id": result["question_id"],
            "status": "completed"
            if result["status"] == "completed"
            else "attempted_failed",
        }
        files[str(path)] = sha
        for op in result["operations"]:
            key_op = op["journal_object_id"]
            if key_op in seen_operations:
                raise ValueError("E2_parent_duplicate_operation")
            seen_operations.add(key_op)
            for suffix in (".json", ".response.json"):
                fp = directory / f"{key_op}{suffix}"
                files[str(fp)] = dense.sha256_file(fp)
    if {
        r.get("object_id") for r in records if r["event"] == "started"
    } != seen_operations:
        raise ValueError("E2_parent_unattributed_attempt")
    return parent, {
        "plan": str(plan_path),
        "directory": str(directory),
        "run_id": manifest["run_id"],
        "files": files,
        "cases": cases,
        "summary": reference["summary"],
        "runtime_commit": PARENT_RUNTIME,
    }


def prepare_continuation(parent_plan, parent_directory):
    parent, snapshot = parent_snapshot(parent_plan, parent_directory)
    fresh = prepare(parent["e1_plan"], parent["e1_workspace"])
    # Policies, cost bounds and code pins change; all scientific inputs stay exact.
    mutable = {
        "code_sha256",
        "mode",
        "failures",
        "cache",
        "max_posts",
        "max_llm_posts",
        "max_embedding_posts",
        "max_combined_tokens",
        "reader_calls",
        "filter_calls",
    }
    if {k: v for k, v in parent.items() if k not in mutable} != {
        k: v for k, v in fresh.items() if k not in mutable
    }:
        raise ValueError("E2_parent_configuration_incompatible")
    expected = {
        case_key(d, m, q): {"dataset": d, "method": m, "question_id": q}
        for d, data in fresh["datasets"].items()
        for m in METHODS
        for q in data["question_ids"]
    }
    remaining = [v for k, v in expected.items() if k not in snapshot["cases"]]
    if not set(snapshot["cases"]) <= set(expected):
        raise ValueError("E2_parent_cases_outside_plan")
    readers = len(remaining)
    filters = sum(r["method"] == "hipporag2" for r in remaining)
    posts = readers * 2 + filters
    reserve = (readers + filters) * (
        MESSAGE_BYTES + 1024 + 2048 + target.OPTIONS["max_tokens"]
    ) + readers * (QUERY_BYTES + 1024 + 2048)
    prior_tokens = sum(snapshot["summary"]["known_subtotal"].values())
    available_tokens = parent["max_combined_tokens"] - prior_tokens
    available_posts = parent["max_posts"] - snapshot["summary"]["attempts"]
    if reserve > available_tokens or posts > available_posts:
        raise ValueError("E2_continuation_budget_insufficient")
    fresh.update(
        version=CONTINUATION_VERSION,
        mode="smoke10_continuation_pending_approval",
        outcome_policy=OUTCOME_POLICY,
        failures="known reader length/empty/unusable -> attempted_failed, no retry, continue; filter/transport/unknown/budget/pin/infrastructure -> stop",
        cache="3 immutable parent cases reused by exact identity; reader failure retained; no replay of any attempted case",
        parent_run=snapshot,
        remaining_cases=remaining,
        reader_calls=readers,
        filter_calls=filters,
        max_posts=posts,
        max_llm_posts=readers + filters,
        max_embedding_posts=readers,
        max_combined_tokens=reserve,
        original_remaining_tokens=available_tokens,
        original_remaining_posts=available_posts,
    )
    return fresh


def check_parent_pins(plan):
    files = {
        **plan.get("parent_run", {}).get("files", {}),
        **plan.get("pilot_reuse", {}).get("files", {}),
    }
    for filename, sha in files.items():
        if dense.sha256_file(Path(filename)) != sha:
            raise ValueError("E2_parent_pin_changed")


def result_references(plan, manifest, directory):
    expected = {
        case_key(d, m, q)
        for d, data in plan["datasets"].items()
        for m in METHODS
        for q in data["question_ids"]
    }
    inherited = plan.get("parent_run", {}).get("cases", {})
    if set(inherited) & set(manifest["results"]):
        raise ValueError("E2_duplicate_case_in_lineage")
    refs = {k: (Path(v["path"]), v["sha256"]) for k, v in inherited.items()}
    refs.update(
        {
            k: (Path(directory) / f"question-{k}.json", sha)
            for k, sha in manifest["results"].items()
        }
    )
    if not set(refs) <= expected:
        raise ValueError("E2_cases_outside_plan")
    return refs


def lineage_records(plan, directory, manifest):
    from scripts.token_accounting import verified_reference, read_records

    check_parent_pins(plan)
    rows = []
    references = []
    seen = set()
    paths = []
    if plan.get("parent_run"):
        paths.append(Path(plan["parent_run"]["directory"]) / "manifest.json")
    paths.append(Path(directory) / "manifest.json")
    for path in paths:
        value = dense.read_json(path)
        reference = verified_reference(value, path)
        if reference["status"] != "verified":
            raise ValueError("E2_lineage_journal_changed")
        records = read_records(path.parent / "usage.jsonl")
        if records.corrupt_tail:
            raise ValueError("E2_lineage_journal_tail")
        for row in records:
            identity = (row["run_id"], row["attempt_id"], row["event"])
            if identity in seen:
                raise ValueError("E2_duplicate_physical_event")
            seen.add(identity)
        rows.extend(records)
        references.append({**reference, "path": str(reference["path"])})
    return rows, references


def verify(plan):
    if plan.get("version") == "e2-pilot200-v1":
        from scripts import e2_pilot

        return e2_pilot.verify(plan)
    if plan["version"] not in (VERSION, CONTINUATION_VERSION):
        raise ValueError("E2_plan_version_changed")
    for name, sha in plan["code_sha256"].items():
        if dense.sha256_file(ROOT / name) != sha:
            raise ValueError("E2_code_changed")
    if dense.sha256_file(Path(plan["e1_plan"])) != plan["e1_plan_sha256"]:
        raise ValueError("E2_E1_plan_changed")
    # Rebuild immutable metadata offline, including journal/artifact/corpus checks.
    candidate = (
        prepare_continuation(
            plan["parent_run"]["plan"], plan["parent_run"]["directory"]
        )
        if plan.get("parent_run")
        else prepare(plan["e1_plan"], plan["e1_workspace"])
    )
    if candidate != plan:
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
        if self.plan.get("version") == "e2-pilot200-v1":
            if (
                method not in METHODS
                or dataset not in self.plan["datasets"]
                or qid not in self.plan["datasets"][dataset]["question_ids"]
            ):
                raise ValueError("E2_pilot_case_outside_frozen_IDs")
            reuse = self.plan["pilot_reuse"]
            case = case_key(dataset, method, qid)
            if (operation == "reader" and case in reuse["readers"]) or (
                operation != "reader" and case in reuse["contexts"]
            ):
                raise ValueError("E2_pilot_compatible_reuse_must_not_POST")
            if operation == "filter" and method != "hipporag2":
                raise ValueError("E2_pilot_filter_only_Hippo")
            if operation == "reader" and (
                len(payload.get("messages", [])) != 4
                or payload["messages"][:3]
                != answer_only_payload("", {"passages": []})["messages"][:3]
            ):
                raise ValueError("E2_pilot_actual_reader_template_changed")
        if self.plan.get("version") == READER_PROBE_VERSION and (
            operation != "reader"
            or not any(
                (c["method"], c["dataset"], c["question_id"], c["payload"])
                == (method, dataset, qid, payload)
                for c in self.plan["cases"]
            )
        ):
            raise ValueError("E2_probe_only_frozen_reader_payloads")
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
        check_parent_pins(self.plan)
        operation_cap = {
            "reader": self.plan.get("reader_calls", 60),
            "filter": self.plan.get("filter_calls", 20),
            "query_embedding": self.plan["max_embedding_posts"],
        }[operation]
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
        if (
            sum(self.journal.summary()["known_subtotal"].values())
            > self.plan["max_combined_tokens"]
        ):
            raise ValueError("E2_reported_usage_exceeded_budget")
        # A stopped-but-invalid answer keeps its measured usage; it cannot be
        # replayed as a successful completed response.
        try:
            if kind == "llm":
                if body.get("model", MODEL) != MODEL:
                    raise ValueError("E2_response_model_changed")
                if (
                    operation == "reader"
                    and self.plan.get("outcome_policy") == OUTCOME_POLICY
                ):
                    reader_text(body)
                else:
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


class ReaderCaseFailure(ValueError):
    """A known paid reader response that is not a usable completed answer."""


def reader_text(body):
    usage = extract_usage(body, "llm", "target_api")
    if any(usage[k] is None for k in ("llm_input_tokens", "llm_output_tokens")):
        raise ValueError("E2_reader_unknown_usage")
    try:
        choice = body["choices"][0]
        finish = choice["finish_reason"]
        text = choice["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ReaderCaseFailure("reader_unusable_structure") from None
    if finish == "length":
        raise ReaderCaseFailure("reader_length")
    if finish != "stop":
        raise ReaderCaseFailure("reader_unusable_finish")
    if not isinstance(text, str) or not text.strip():
        raise ReaderCaseFailure("reader_empty")
    return text


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

    from scripts import e2_pilot

    reuse_key = case_key(dataset, method, query["id"])

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
            if operation == "reader" and reuse_key in plan.get("pilot_reuse", {}).get(
                "readers", {}
            ):
                body, provenance = e2_pilot.reader_reuse(plan, reuse_key, payload)
                attempt.update(provenance)
                hit = True
            else:
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
            attempt["transport_seconds"] = (
                finished[-1].get("wall_seconds") if finished else None
            )
            attempt["client_seconds"] = time.perf_counter() - t
            operations.append(attempt)

    stage_name = "query_embedding"
    t = time.perf_counter()
    try:
        reused_context = e2_pilot.context_reuse(plan, reuse_key)
        if reused_context is not None:
            retrieval, source_operations, context_provenance = reused_context
            operations.extend(source_operations)
            cache.update({o["operation"]: True for o in source_operations})
            result["context_provenance"] = context_provenance
            stages["context_replay"] = time.perf_counter() - t
        else:
            response = call(
                embedding_payload(plan, query["question"]), "query_embedding"
            )
            vectors = response["embeddings"]
            if len(vectors) != 1:
                raise ValueError("E2_query_embedding_shape")
            stages["query_embedding"] = time.perf_counter() - t

            def infer(messages):
                return completed_text(
                    call(
                        {"model": MODEL, "messages": messages, **target.OPTIONS},
                        "filter",
                    )
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
        payload = configured_reader_payload(plan, query["question"], retrieval)
        result["reader_request_sha256"] = target.digest(payload)
        result["reader_message_utf8_bytes"] = len(
            json.dumps(payload["messages"], ensure_ascii=False).encode()
        )
        stage_name = "reader"
        t = time.perf_counter()
        response = call(payload, "reader")
        stages["reader"] = time.perf_counter() - t
        raw = (
            reader_text(response)
            if plan.get("outcome_policy") == OUTCOME_POLICY
            else completed_text(response)
        )
        result["raw_answer"] = raw
        answer, status = parse_reader(plan, raw)
        if status != "ok":
            if plan.get("outcome_policy") == OUTCOME_POLICY:
                raise ReaderCaseFailure("reader_parser_failed")
            raise ValueError("E2_reader_parser_failed")
        result.update(status="completed", answer=answer)
    except Exception as exc:
        result["error"] = {"type": type(exc).__name__, "reason": str(exc)}
        result["answer"] = ""
        if plan.get("outcome_policy") == OUTCOME_POLICY:
            result["status"] = (
                "attempted_failed"
                if any(o.get("physical_attempted") for o in operations)
                else "not_attempted"
            )
            result["fatal"] = not isinstance(exc, ReaderCaseFailure)
            result["failure_scope"] = (
                "reader_response" if not result["fatal"] else "execution"
            )
    finally:
        if plan.get("version") == "e2-pilot200-v1":
            result["reader_version"] = plan["reader_version"]
            result["latency_mode"] = (
                "fresh_end_to_end"
                if "context_provenance" not in result
                else "cached_context_cached_reader"
                if cache.get("reader")
                else "cached_context_fresh_reader"
            )
            result["reader_generation_seconds"] = next(
                (
                    o.get("transport_seconds")
                    for o in operations
                    if o["operation"] == "reader" and not o.get("reused")
                ),
                None,
            )
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
    if result["status"] in ("not_attempted", "not_attempted_after_stop"):
        return {
            "em": None,
            "f1": None,
            "passage_recall_at_5": None,
            "supporting_provenance_coverage": None,
        }
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
    if plan.get("parent_run"):
        parent_id = target.digest(plan["parent_run"]["files"])
        child_claim = (
            Path(plan["e1_workspace"])
            / ".cache"
            / f"e2-continuation-of-{parent_id}.claim.json"
        )
        identity = {"plan_sha256": target.digest(plan), "directory": str(directory)}
        if child_claim.exists():
            if dense.read_json(child_claim) != identity:
                raise ValueError("E2_parent_continuation_already_claimed")
        else:
            with child_claim.open("x", encoding="utf-8") as stream:
                json.dump(identity, stream)
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
            if plan.get("parent_run"):
                parent = plan["parent_run"]
                manifest["parent_run"] = {
                    "run_id": parent["run_id"],
                    "manifest_sha256": parent["files"][
                        str(Path(parent["directory"]) / "manifest.json")
                    ],
                    "inherited_cases": len(parent["cases"]),
                }
            dense.write_json_atomic(mp, manifest)
        check_parent_pins(plan)
        result_references(plan, manifest, directory)
        if plan.get("parent_run") or plan.get("version") == "e2-pilot200-v1":
            from scripts.token_accounting import read_records

            existing_records = read_records(directory / "usage.jsonl")
            if not calls.journal.summary()["complete"]:
                raise ValueError("E2_unknown_child_no_resume")
            for key, sha in manifest["results"].items():
                path = directory / f"question-{key}.json"
                if dense.sha256_file(path) != sha:
                    raise ValueError("E2_saved_result_changed")
                saved_case = dense.read_json(path)
                if key != case_key(
                    saved_case["dataset"],
                    saved_case["method"],
                    saved_case["question_id"],
                ):
                    raise ValueError("E2_saved_case_identity_changed")
                verify_saved_case(plan, directory, saved_case, existing_records)
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
                    key = case_key(dataset, method, query["id"])
                    if key in plan.get("parent_run", {}).get("cases", {}):
                        continue  # Both completed answers AND the known failed reader are terminal cases.
                    result_path = directory / f"question-{key}.json"
                    if key in manifest["results"]:
                        if plan.get("outcome_policy") == OUTCOME_POLICY:
                            continue  # Verified above, no retrieval/filter/embedding/reader replay.
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
                    fatal = result["status"] != "completed" and (
                        plan.get("outcome_policy") != OUTCOME_POLICY
                        or result.get("fatal", True)
                    )
                    if fatal:
                        manifest["status"] = "failed"
                    dense.write_json_atomic(mp, manifest)
                    if fatal:
                        return manifest
                    time.sleep(4)
        manifest["status"] = (
            "completed"
            if len(result_references(plan, manifest, directory))
            == sum(
                len(d["question_ids"]) * len(METHODS) for d in plan["datasets"].values()
            )
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
    directory = Path(directory)
    manifest = dense.read_json(directory / "manifest.json")
    if manifest["plan_sha256"] != target.digest(plan):
        raise ValueError("E2_summary_config_changed")
    from scripts.token_accounting import summarize

    records, references = lineage_records(plan, directory, manifest)
    reference = {
        "status": "verified",
        "path": str(directory / "usage.jsonl"),
        "summary": summarize(records),
        "lineage": references,
    }
    refs = result_references(plan, manifest, directory)
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
                if key in refs:
                    path, sha = refs[key]
                    if dense.sha256_file(path) != sha:
                        raise ValueError("E2_result_changed")
                    result = dense.read_json(path)
                    if (
                        case_key(
                            result["dataset"], result["method"], result["question_id"]
                        )
                        != key
                    ):
                        raise ValueError("E2_result_case_changed")
                    result = {**result}
                    if result["status"] == "failed":
                        result["status"] = "attempted_failed"
                else:
                    result = {
                        "question_id": qid,
                        "method": method,
                        "dataset": dataset,
                        "status": "not_attempted",
                        "answer": "",
                    }
                scores = score_result(result, labels[qid])
                scored.append({**result, "metrics": scores})
            details.extend(scored)
            complete = [r for r in scored if r["status"] == "completed"]
            attempted = [r for r in scored if r["status"] != "not_attempted"]
            failed = [r for r in scored if r["status"] == "attempted_failed"]
            full = len(attempted) == len(scored)
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
            by_operation = {}
            for operation in ("query_embedding", "filter", "reader"):
                selected = [o for o in operations if o["operation"] == operation]
                if selected:
                    by_operation[operation] = {
                        "calls": len(selected),
                        "known_subtotal": {
                            k: sum(
                                o.get("logical_usage", {}).get(k) or 0 for o in selected
                            )
                            for k in (
                                "llm_input_tokens",
                                "llm_output_tokens",
                                "embedding_input_tokens",
                            )
                        },
                    }
            table.append(
                {
                    "dataset": dataset,
                    "method": method,
                    "planned": len(scored),
                    "completed": len(complete),
                    "attempted_failed": len(failed),
                    "not_attempted": len(scored) - len(attempted),
                    "comparison_complete": full,
                    "failure_rate": len(failed) / len(attempted) if attempted else None,
                    "completion_rate": len(complete) / len(scored),
                    "em": sum(r["metrics"]["em"] for r in attempted) / len(scored)
                    if full
                    else None,
                    "f1": sum(r["metrics"]["f1"] for r in attempted) / len(scored)
                    if full
                    else None,
                    "passage_recall_at_5": sum(
                        r["metrics"]["passage_recall_at_5"] for r in attempted
                    )
                    / len(scored)
                    if method != "raptor" and full
                    else None,
                    "provenance_coverage": sum(
                        r["metrics"]["supporting_provenance_coverage"]
                        for r in attempted
                    )
                    / len(scored)
                    if full
                    else None,
                    "mean_attempted_seconds": sum(r["wall_seconds"] for r in attempted)
                    / len(attempted)
                    if attempted
                    else None,
                    "mean_completed_seconds": sum(r["wall_seconds"] for r in complete)
                    / len(complete)
                    if complete
                    else None,
                    "logical_usage_by_model": usage,
                    "usage_by_operation": by_operation,
                    "limitations": "smoke10 development, not independent quality evidence; failed operation usage in global physical journal",
                }
            )
    result = {
        "run_id": manifest["run_id"],
        "rows": table,
        "question_results": details,
        "physical_query_accounting": reference,
        "comparison_complete": manifest["status"] == "completed"
        and all(r["comparison_complete"] for r in table),
        "historical_E1_excluded": True,
    }
    if plan.get("version") == "e2-pilot200-v1":
        from scripts import e2_pilot

        e2_pilot.enrich_report(plan, result)
    return result


def tracking_payload(plan, directory, dataset, method):
    """Adapt shared records to the existing MLflow/Langfuse exporters, offline.

    Common journal belongs to this whole smoke run, not six extra costs; partition
    its records by exact question request identities for each exported config.
    """
    from scripts.token_accounting import summarize

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
            reader_prompt_version=plan.get(
                "reader_version", dense.READER_PROMPT_VERSION
            ),
            prompt_tokens=reader.get("logical_usage", {}).get("llm_input_tokens"),
            completion_tokens=reader.get("logical_usage", {}).get("llm_output_tokens"),
            query_embedding_prompt_tokens=embedding.get("logical_usage", {}).get(
                "embedding_input_tokens"
            ),
            query_embedding_client_seconds=embedding.get("client_seconds"),
            generation_wall_seconds=reader.get("client_seconds"),
        )
        key = case_key(row["dataset"], row["method"], row["question_id"])
        producer = (
            Path(plan["parent_run"]["directory"])
            if key in plan.get("parent_run", {}).get("cases", {})
            else Path(directory)
        )
        if row.get("context_provenance"):
            row["context_source_run_id"] = row["context_provenance"]["run_id"]
        row["generation_reused"] = bool(reader.get("reused"))
        row["generation_source_run_id"] = reader.get("producer_run_id")
        row["generation_source_seconds"] = reader.get("source_transport_seconds")
        if reader.get("reused"):
            row["generation_wall_seconds"] = None
        if reader:
            response = (
                Path(reader["source_directory"])
                / f"{reader['source_object_id']}.response.json"
                if reader.get("reused")
                else producer / f"{reader['journal_object_id']}.response.json"
            )
            if response.exists():
                saved = dense.read_json(response)
                choice = saved.get("choices", [{}])[0]
                row["done_reason"] = choice.get("finish_reason")
                row["raw_answer"] = choice.get("message", {}).get("content")
        row["answer_extraction_status"] = (
            "ok"
            if row["status"] == "completed"
            else row.get("error", {}).get("reason", row["status"])
        )
        row.setdefault("question", "not attempted after stop")
        questions.append(
            {
                "row": row,
                "retrieved_passages": row.get("retrieval", {}).get("passages", []),
            }
        )
    physical, _ = lineage_records(
        plan, directory, dense.read_json(Path(directory) / "manifest.json")
    )
    phases = summarize([r for r in physical if r.get("object_id") in keys])
    aggregate = next(
        r for r in report["rows"] if r["dataset"] == dataset and r["method"] == method
    )
    manifest = {
        "mode": "e2-pilot200"
        if plan.get("version") == "e2-pilot200-v1"
        else "e2-smoke10",
        "generation": {
            "model": {"name": MODEL, "digest": None},
            "reader_prompt_version": plan.get(
                "reader_version", dense.READER_PROMPT_VERSION
            ),
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
            "scope": "partition of new physical query journal; E1 excluded",
            "historical_reuse": aggregate.get("reused_source_usage_by_operation"),
        },
    }


def write_report(plan_path, directory, public_prefix):
    """Generate private evaluation and a safe public table from immutable results.

    A failed smoke publishes technical coverage, not a fabricated six-way score.
    Does not check current execution code pins or enable resume: it reports the
    original pinned runtime and preserves its failed manifest/claims verbatim.
    """
    from collections import Counter

    plan_path, directory, prefix = map(Path, (plan_path, directory, public_prefix))
    plan = dense.read_json(plan_path)
    manifest_path = directory / "manifest.json"
    manifest_sha = dense.sha256_file(manifest_path)
    manifest = dense.read_json(manifest_path)
    report = summary(plan, directory)
    dense.write_json_atomic(directory / "evaluation.json", report)
    records, _ = lineage_records(plan, directory, manifest)
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
                    "attempted_failed": counts["attempted_failed"],
                    "not_attempted": counts["not_attempted"],
                }
            )
    failures = []
    for result in report["question_results"]:
        if result["status"] != "attempted_failed":
            continue
        failure = {
            "dataset": result["dataset"],
            "method": result["method"],
            "question_id": result["question_id"],
            "error": result.get("error"),
            "partial_response_accepted": False,
        }
        producer = directory
        key = case_key(result["dataset"], result["method"], result["question_id"])
        if key in plan.get("parent_run", {}).get("cases", {}):
            producer = Path(plan["parent_run"]["directory"])
        for op in result.get("operations", []):
            response = producer / f"{op['journal_object_id']}.response.json"
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
    e1_cost = dense.read_json(ROOT / "results/summary/e1-indexing.json")
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
        "remaining_original_tokens": plan.get(
            "original_remaining_tokens", plan["max_combined_tokens"]
        )
        - sum(manifest["token_accounting"]["summary"]["known_subtotal"].values())
        if manifest["token_accounting"]["summary"]["complete"]
        else None,
        "remaining_original_posts": plan.get(
            "original_remaining_posts", plan["max_posts"]
        )
        - manifest["token_accounting"]["summary"]["attempts"],
        "new_model_posts": manifest["token_accounting"]["summary"]["attempts"],
        "physical_lineage": report["physical_query_accounting"]["lineage"],
        "failures": failures,
        "comparison_complete": report["comparison_complete"],
        "comparative_metrics": report["rows"]
        if report["comparison_complete"]
        else None,
        "tracking": dense.read_json(directory / "tracking/receipt.json")
        if (directory / "tracking/receipt.json").exists()
        else None,
        "continuation_authorized": False,
        "e1_historical_cost_excluded": True,
        "e1_historical_cost": {
            "physical_known_tokens": e1_cost["physical_known_tokens"],
            "unknown_reserved_upper_bound": e1_cost["budget_charge_upper_bound"]
            - e1_cost["physical_known_tokens"],
            "cost_complete": e1_cost["cost_complete"],
            "source_sha256": dense.sha256_file(
                ROOT / "results/summary/e1-indexing.json"
            ),
        },
        "limitations": "development smoke only; failed run is not a completed comparison; E1 unknown61588 remains separate",
    }
    if plan.get("version") == "e2-pilot200-v1":
        from scripts import e2_pilot

        safe.update(
            pilot_accounting=report["pilot_accounting"],
            paired_comparisons=report["paired_comparisons"],
            comparative_metrics=report["rows"]
            if report["comparison_complete"]
            else None,
            kind="e2_pilot200",
        )
        dense.write_json_atomic(prefix.with_suffix(".json"), safe)
        e2_pilot.write_markdown(plan, report, safe, prefix)
        assert dense.sha256_file(manifest_path) == manifest_sha
        return safe
    dense.write_json_atomic(prefix.with_suffix(".json"), safe)
    lines = [
        "# E2 smoke10: " + manifest["status"],
        "",
        f"Run `{manifest['run_id']}`; plan `{safe['plan_sha256']}`.",
        "",
        f"Учтены60cases: {outcome_counts['completed']} completed, {outcome_counts['attempted_failed']} attempted_failed, {outcome_counts['not_attempted']} not_attempted. Reader/model/prompt/cap512 неизменны; retries0.",
        "",
    ]
    if report["comparison_complete"]:
        lines.extend(
            [
                "| Dataset | Method | EM % | F1 % | Completed / failed | Failure % | Mean query s | LLM in / out | BGE tokens | Passage recall@5 % | RAPTOR provenance % |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for r in report["rows"]:
            llm = r["logical_usage_by_model"].get(MODEL, {}).get("known_subtotal", {})
            embedding = (
                r["logical_usage_by_model"]
                .get(plan["embedding_model"], {})
                .get("known_subtotal", {})
            )
            recall = (
                f"{r['passage_recall_at_5'] * 100:.2f}"
                if r["passage_recall_at_5"] is not None
                else "—"
            )
            provenance = (
                f"{r['provenance_coverage'] * 100:.2f}"
                if r["method"] == "raptor"
                else "—"
            )
            lines.append(
                f"| {r['dataset']} | {r['method']} | {r['em'] * 100:.2f} | {r['f1'] * 100:.2f} | {r['completed']} / {r['attempted_failed']} | {r['failure_rate'] * 100:.1f} | {r['mean_attempted_seconds']:.3f} | {llm.get('llm_input_tokens', 0)} / {llm.get('llm_output_tokens', 0)} | {embedding.get('embedding_input_tokens', 0)} | {recall} | {provenance} |"
            )
    else:
        lines.extend(
            [
                "Сравнение неполное: EM/F1 для незавершённых групп=null; not_attempted не считается неправильным ответом.",
                "",
                "| Dataset | Method | Completed | Attempted failed | Not attempted |",
                "|---|---|---:|---:|---:|",
            ]
        )
        for r in rows:
            lines.append(
                f"| {r['dataset']} | {r['method']} | {r['completed']} | {r['attempted_failed']} | {r['not_attempted']} |"
            )
    filter_usage = {
        k: sum(
            r.get("usage_by_operation", {})
            .get("filter", {})
            .get("known_subtotal", {})
            .get(k, 0)
            for r in report["rows"]
        )
        for k in ("llm_input_tokens", "llm_output_tokens")
    }
    lines.extend(
        [
            "",
            f"Query LLM input={known['llm_input_tokens']}, output={known['llm_output_tokens']}; local BGE input={known['embedding_input_tokens']}. Query cost_complete={safe['query_cost_complete']}; unknown={safe['new_unknown_attempts']}; unfinished={safe['unfinished_attempts']}.",
            f"Модельных POST={safe['model_posts']} ({safe['llm_posts']}LLM/{safe['embedding_posts']}localBGE), новых child POST={safe['new_model_posts']}. Parent/child учтены один раз.",
            f"Hippo fact filter включён в LLM totals: input={filter_usage['llm_input_tokens']}, output={filter_usage['llm_output_tokens']}. Reader/filter отдельно — usage_by_operation в JSON.",
            "",
            "На законченном smoke denominator=10/cfg; attempted_failed даёт EM/F1=0. Mean query time включает failed cases, query embedding/retrieval/filter/reader; исключает preflight/index loading/паузы между cases. Source parent timing сохранён, это не cold-run benchmark.",
            "RAPTOR top5 — nodes. Passage recall@5 не сопоставим; provenance — покрытие union descendant source IDs, не доказательство сохранения нужного факта в summary.",
            f"E1 отдельно: physical known={e1_cost['physical_known_tokens']}; unknown reserve={safe['e1_historical_cost']['unknown_reserved_upper_bound']}; cost_complete={e1_cost['cost_complete']}. Reserve не actual usage; деньги не оценивались. E1 индексы не перестраивались.",
            "",
            f"Ошибки и точные source/request/response SHA: [{prefix.name}.json]({prefix.name}.json). Private raw: `{directory}`. Полные тексты/gold в Git не публикуются.",
            "Development tuning smoke n=10/dataset, не pilot200 и не выбор победителя. Hippo Qwen/GPT extraction policy/observed errors раскрыты в ADR0023; это сравнение конкретных конфигураций, не чистого эффекта архитектуры.",
            "",
            "**Один следующий шаг:** общий пересмотр reader для всех методов перед pilot200 из-за наблюдаемых reader length failures. Решение основано на завершённости ответа, не на лучшем F1; новая reader version не смешивается с v2. Новых model calls этот отчёт не разрешает.",
            "Refs #14; Draft, без pilot200/S500/check/holdout/новых моделей/rebuild/merge.",
        ]
    )
    prefix.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert dense.sha256_file(manifest_path) == manifest_sha
    return safe


READER_PROBE_VERSION = "e2-answer-only-probe-v1"
ANSWER_ONLY_SYSTEM = (
    "Answer the question using the supplied passages. Return exactly one line: "
    "Answer: <concise answer>. Do not include reasoning, analysis or explanation."
)


def answer_only_payload(question, retrieval):
    """One shared candidate: same demonstration/context, explicit answer only."""
    payload = reader_payload(question, retrieval)
    messages = payload["messages"]
    messages[0]["content"] = ANSWER_ONLY_SYSTEM
    for index in (1, 3):
        suffix = "\nThought: "
        if not messages[index]["content"].endswith(suffix):
            raise ValueError("E2_reader_template_suffix_changed")
        messages[index]["content"] = messages[index]["content"][: -len(suffix)]
    answer, status = dense.extract_target_reader_answer(messages[2]["content"])
    if status != "ok":
        raise ValueError("E2_reader_demo_changed")
    messages[2]["content"] = "Answer: " + answer
    return payload


def prepare_reader_probe(source_plan_path, source_directory):
    """Freeze 12 cached-context requests without labels, SDK loading or HTTP."""
    source_plan_path, source_directory = map(
        lambda p: Path(p).resolve(), (source_plan_path, source_directory)
    )
    source = dense.read_json(source_plan_path)
    manifest_path = source_directory / "manifest.json"
    manifest = dense.read_json(manifest_path)
    if (
        manifest["status"] != "completed"
        or manifest["plan_sha256"] != target.digest(source)
        or (source_directory / "running.lock").exists()
    ):
        raise ValueError("E2_probe_source_not_completed")
    physical, references = lineage_records(source, source_directory, manifest)
    if any(not r["summary"]["complete"] for r in references):
        raise ValueError("E2_probe_source_unknown")
    refs = result_references(source, manifest, source_directory)
    files = {str(source_plan_path): dense.sha256_file(source_plan_path)}
    files.update(source.get("parent_run", {}).get("files", {}))
    for reference in references:
        journal = Path(reference["path"])
        for path in (journal, journal.parent / "manifest.json"):
            files[str(path)] = dense.sha256_file(path)
    rows = {}
    for key, (path, sha) in refs.items():
        if dense.sha256_file(path) != sha:
            raise ValueError("E2_probe_source_result_changed")
        row = dense.read_json(path)
        original = (
            dense.read_json(Path(source["parent_run"]["plan"]))
            if key in source.get("parent_run", {}).get("cases", {})
            else source
        )
        verify_saved_case(original, path.parent, row, physical)
        rows[key] = row
        files[str(path)] = sha
        for operation in row["operations"]:
            for suffix in (".json", ".response.json"):
                saved = path.parent / (operation["journal_object_id"] + suffix)
                files[str(saved)] = dense.sha256_file(saved)
    if len(rows) != 60:
        raise ValueError("E2_probe_requires_60_source_cases")
    cases = []
    for dataset, data in source["datasets"].items():

        def complete(qid):
            return all(
                rows[case_key(dataset, m, qid)]["status"] == "completed"
                for m in METHODS
            )

        ids = data["question_ids"]
        failure = next((q for q in ids if not complete(q)), ids[0])
        control = next((q for q in ids if q != failure and complete(q)), None)
        if control is None:
            raise ValueError("E2_probe_no_common_completed_control")
        for qid, stratum in (
            (failure, "first_reader_failure_or_baseline"),
            (control, "first_all_completed_control"),
        ):
            for method in METHODS:
                row = rows[case_key(dataset, method, qid)]
                payload = answer_only_payload(row["question"], row["retrieval"])
                cases.append(
                    {
                        "dataset": dataset,
                        "method": method,
                        "question_id": qid,
                        "stratum": stratum,
                        "source_status": row["status"],
                        "payload": payload,
                        "payload_sha256": target.digest(payload),
                        "source_case_sha256": refs[case_key(dataset, method, qid)][1],
                    }
                )
    reserve = sum(
        len(json.dumps(c["payload"], ensure_ascii=False).encode())
        + 2048
        + target.OPTIONS["max_tokens"]
        for c in cases
    )
    return {
        "version": READER_PROBE_VERSION,
        "reader_version": "shared-answer-only-v1",
        "source_plan": str(source_plan_path),
        "source_directory": str(source_directory),
        "source_run_id": manifest["run_id"],
        "source_files": files,
        "code_sha256": {name: dense.sha256_file(ROOT / name) for name in CODE_FILES},
        "endpoint": "https://api.duckduck.cloud/v1",
        "reader_model": MODEL,
        "reader_options": target.OPTIONS,
        "cases": cases,
        "selection": "first known reader failure and first distinct all-method completed control in each frozen tuning order; statuses only, no labels/scores",
        "max_posts": len(cases),
        "max_llm_posts": len(cases),
        "reader_calls": len(cases),
        "max_embedding_posts": 0,
        "filter_calls": 0,
        "max_combined_tokens": reserve,
        "retry": 0,
        "redirects": 0,
        "timeout": [30, 300],
        "outcome_policy": OUTCOME_POLICY,
        "http_authorized": False,
        "stop": "first length/empty/invalid answer/unknown/HTTP/transport/budget/pin error; no retry or alternate prompt",
        "acceptance": "all12 stop, known usage, exactly one nonempty Answer line, no8word block repeated3times consecutively; then source-only audit for unsupported claims/omitted qualifications without gold; no automatic adoption/pilot",
        "cost": "new diagnostic budget, not remainder of exhausted smoke POST cap; prior209108 query tokens and incomplete E1 cost remain separate",
    }


def verify_reader_probe(plan):
    if plan.get("version") != READER_PROBE_VERSION:
        raise ValueError("E2_probe_version_changed")
    for filename, sha in {
        **plan["source_files"],
        **{str(ROOT / k): v for k, v in plan["code_sha256"].items()},
    }.items():
        if dense.sha256_file(Path(filename)) != sha:
            raise ValueError("E2_probe_source_or_code_changed")
    if prepare_reader_probe(plan["source_plan"], plan["source_directory"]) != plan:
        raise ValueError("E2_probe_payload_or_contract_changed")
    return True


def execute_reader_probe(plan_path, directory, *, approved_sha, config):
    """Existing Calls/Journal transport, cached contexts only, one diagnostic run."""
    import uuid

    plan_path, directory = Path(plan_path).resolve(), Path(directory).resolve()
    plan = dense.read_json(plan_path)
    verify_reader_probe(plan)
    if approved_sha != dense.sha256_file(plan_path) or not config:
        raise ValueError("E2_exact_plan_approval_required_before_HTTP")
    if config["base_url"] != plan["endpoint"] or config["model"] != MODEL:
        raise ValueError("E2_endpoint_or_model_changed")
    run_id = str(uuid.uuid4())
    claim = (
        Path(plan["source_directory"]).parent
        / f"reader-probe-{target.digest(plan)}.claim.json"
    )
    if directory.exists():
        raise ValueError("E2_probe_existing_output_no_retry")
    with claim.open("x", encoding="utf-8") as stream:
        json.dump({"run_id": run_id, "directory": str(directory)}, stream)
    calls = Calls(directory, plan, run_id=run_id)
    manifest = {
        "run_id": run_id,
        "plan_sha256": target.digest(plan),
        "reader_version": plan["reader_version"],
        "status": "running",
        "results": [],
    }
    dense.write_json_atomic(directory / "manifest.json", manifest)
    try:
        with target.requests.Session() as remote:
            for case in plan["cases"]:
                manifest["current_case"] = {
                    k: case[k] for k in ("dataset", "method", "question_id")
                }
                dense.write_json_atomic(directory / "manifest.json", manifest)
                for filename, sha in plan["source_files"].items():
                    if dense.sha256_file(Path(filename)) != sha:
                        raise ValueError("E2_probe_source_changed")
                body, _ = calls.call(
                    case["payload"],
                    method=case["method"],
                    dataset=case["dataset"],
                    qid=case["question_id"],
                    operation="reader",
                    session=remote,
                    url=plan["endpoint"] + "/chat/completions",
                    headers={"Authorization": "Bearer " + config["key"]},
                )
                raw = reader_text(body)
                answer, status = dense.extract_target_reader_answer(raw)
                if status != "ok" or raw.strip() != "Answer: " + answer:
                    raise ReaderCaseFailure("reader_not_single_answer_line")
                words = answer.split()
                if any(
                    words[i : i + 8] == words[i + 8 : i + 16] == words[i + 16 : i + 24]
                    for i in range(len(words) - 23)
                ):
                    raise ReaderCaseFailure("reader_repeated_8word_block_three_times")
                manifest["results"].append(
                    {
                        k: case[k]
                        for k in ("dataset", "method", "question_id", "payload_sha256")
                    }
                )
                dense.write_json_atomic(directory / "manifest.json", manifest)
        manifest["status"] = "responses_pending_source_audit"
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = {"type": type(exc).__name__, "reason": str(exc)}
    finally:
        manifest["token_accounting"] = calls.journal.reference()
        manifest["source_costs_not_recounted"] = True
        dense.write_json_atomic(directory / "manifest.json", manifest)
    return manifest
