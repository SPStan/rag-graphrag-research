"""Pilot200 plan and frozen per-case reuse, called only by the shared E2 runner."""

import copy
import json
from pathlib import Path

import numpy as np

from scripts import e2_evaluation as e2
from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts.token_accounting import (
    extract_usage,
    read_records,
    summarize,
    verified_reference,
)

VERSION = "e2-pilot200-v1"
READER = "shared-answer-only-v1"


def prepare(
    e1_plan,
    workspace,
    source_plan,
    source_directory,
    diagnostic_plan,
    diagnostic_directory,
):
    base = e2.prepare(e1_plan, workspace, pilot=True)
    return complete_plan(
        base, source_plan, source_directory, diagnostic_plan, diagnostic_directory
    )


def complete_plan(
    base, source_plan, source_directory, diagnostic_plan, diagnostic_directory
):
    """No labels/score selection: every compatible cached case is included."""
    source_plan, source_directory, diagnostic_plan, diagnostic_directory = map(
        lambda p: Path(p).resolve(),
        (source_plan, source_directory, diagnostic_plan, diagnostic_directory),
    )
    if base.get("parent_run"):
        raise ValueError("E2_pilot_base_cannot_inherit_Thought_answers")
    source = dense.read_json(source_plan)
    diagnostic = dense.read_json(diagnostic_plan)
    sm = dense.read_json(source_directory / "manifest.json")
    dm = dense.read_json(diagnostic_directory / "manifest.json")
    if sm["status"] != "completed" or dm["status"] != "responses_pending_source_audit":
        raise ValueError("E2_pilot_sources_not_terminal")
    if sm["plan_sha256"] != target.digest(source) or dm["plan_sha256"] != target.digest(
        diagnostic
    ):
        raise ValueError("E2_pilot_source_plan_changed")
    if diagnostic.get("reader_version") != READER or diagnostic["source_plan"] != str(
        source_plan
    ):
        raise ValueError("E2_pilot_diagnostic_incompatible")
    for field in (
        "hippo",
        "hippo_commit",
        "raptor_commit",
        "embedding_digest",
        "embedding_model",
        "reader_model",
        "reader_options",
        "top_k",
        "context_order",
        "message_utf8_bytes_limit",
        "query_utf8_bytes_limit",
        "overflow",
        "endpoint",
        "e1_plan_sha256",
        "parser",
        "evaluator",
    ):
        if base.get(field) != source.get(field):
            raise ValueError("E2_pilot_retrieval_contract_changed:" + field)
    # These modules implement the native retrieval/filter/embedding contract.
    for name in (
        "scripts/e1_indexers.py",
        "scripts/run_dense.py",
        "scripts/run_raptor_smoke.py",
        "scripts/preflight_hipporag_repair_prompts.py",
        "scripts/vendor/hipporag2_musique_template.py",
    ):
        if source["code_sha256"][name] != dense.sha256_file(e2.ROOT / name):
            raise ValueError("E2_pilot_source_retrieval_code_changed")
    files = dict(diagnostic["source_files"])
    for filename, sha in files.items():
        if dense.sha256_file(Path(filename)) != sha:
            raise ValueError("E2_pilot_source_pin_changed")
    for path in (
        source_plan,
        diagnostic_plan,
        source_directory / "manifest.json",
        diagnostic_directory / "manifest.json",
        diagnostic_directory / "usage.jsonl",
    ):
        files[str(path)] = dense.sha256_file(path)
    data_root = Path(dense.read_json(Path(base["e1_plan"]))["data_root"])
    current_queries = {}
    for dataset, data in base["datasets"].items():
        old = source["datasets"][dataset]
        queries = dense.read_json(data_root / f"data/processed/{dataset}/queries.json")
        old_queries = e2.select_in_view(queries, old["question_ids"], "query")
        if target.digest(old_queries) != old["queries_sha256"]:
            raise ValueError("E2_pilot_source_question_text_changed")
        current_queries[dataset] = {
            q["id"]: q["question"]
            for q in e2.select_in_view(queries, data["question_ids"], "query")
        }
        for field in (
            "corpus_sha256",
            "labels_sha256_evaluator_only",
            "indexes",
            "split_sha256",
        ):
            if data.get(field) != old.get(field):
                raise ValueError("E2_pilot_source_data_or_index_changed")
        if not set(old["question_ids"]) <= set(data["question_ids"]):
            raise ValueError("E2_pilot_source_ID_outside_pilot")
    physical, _ = e2.lineage_records(source, source_directory, sm)
    dr = verified_reference(dm, diagnostic_directory / "manifest.json")
    if dr["status"] != "verified" or not dr["summary"]["complete"]:
        raise ValueError("E2_pilot_diagnostic_unknown")
    drecords = read_records(diagnostic_directory / "usage.jsonl")
    refs = e2.result_references(source, sm, source_directory)
    contexts, readers, reused_cost = {}, {}, []
    for key, (path, sha) in refs.items():
        row = dense.read_json(path)
        original = (
            dense.read_json(Path(source["parent_run"]["plan"]))
            if key in source.get("parent_run", {}).get("cases", {})
            else source
        )
        if dense.sha256_file(path) != sha:
            raise ValueError("E2_pilot_source_case_changed")
        e2.verify_saved_case(original, path.parent, row, physical)
        if row["question"] != current_queries[row["dataset"]][row["question_id"]]:
            raise ValueError("E2_pilot_cached_question_changed")
        contexts[key] = {"path": str(path), "sha256": sha}
        for op in row["operations"]:
            if op["operation"] != "reader":
                if op["status"] != "completed":
                    raise ValueError("E2_pilot_context_not_complete")
                reused_cost.append(op)
    for case in diagnostic["cases"]:
        key = e2.case_key(case["dataset"], case["method"], case["question_id"])
        if key not in contexts:
            raise ValueError("E2_pilot_reader_without_compatible_context")
        row = dense.read_json(Path(contexts[key]["path"]))
        payload = e2.answer_only_payload(row["question"], row["retrieval"])
        if (
            payload != case["payload"]
            or target.digest(payload) != case["payload_sha256"]
        ):
            raise ValueError("E2_pilot_reader_payload_changed")
        object_id = target.digest(
            {
                "plan": target.digest(diagnostic),
                "method": case["method"],
                "dataset": case["dataset"],
                "qid": case["question_id"],
                "operation": "reader",
                "payload": payload,
            }
        )
        checkpoint = diagnostic_directory / (object_id + ".json")
        response = diagnostic_directory / (object_id + ".response.json")
        saved, body = dense.read_json(checkpoint), dense.read_json(response)
        terminal = [
            r
            for r in drecords
            if r["event"] == "finished" and r.get("object_id") == object_id
        ]
        if (
            len(terminal) != 1
            or terminal[0]["usage_status"] != "complete"
            or terminal[0]["status"] != "success"
            or saved["status"] != "completed"
            or saved["response"] != body
            or saved["response_sha256"] != target.digest(body)
        ):
            raise ValueError("E2_pilot_reader_checkpoint_or_usage_changed")
        usage = extract_usage(body, "llm", "target_api")
        if usage != {k: terminal[0][k] for k in usage}:
            raise ValueError("E2_pilot_reader_cost_changed")
        e2.parse_reader({"reader_version": READER}, e2.reader_text(body))
        files[str(checkpoint)], files[str(response)] = (
            dense.sha256_file(checkpoint),
            dense.sha256_file(response),
        )
        readers[key] = {
            "source_directory": str(diagnostic_directory),
            "source_object_id": object_id,
            "producer_run_id": dm["run_id"],
            "payload_sha256": case["payload_sha256"],
            "logical_usage": usage,
            "source_transport_seconds": terminal[0]["wall_seconds"],
        }
        reused_cost.append({"logical_usage": usage})
    if len(readers) != len(diagnostic["cases"]):
        raise ValueError("E2_pilot_duplicate_reuse_case")
    total = sum(
        len(d["question_ids"]) * len(e2.METHODS) for d in base["datasets"].values()
    )
    embedding = total - len(contexts)
    filters = sum(len(d["question_ids"]) for d in base["datasets"].values()) - sum(
        dense.read_json(Path(v["path"]))["method"] == "hipporag2"
        for v in contexts.values()
    )
    reader = total - len(readers)
    envelope = e2.MESSAGE_BYTES + 1024 + 2048 + target.OPTIONS["max_tokens"]
    cached_reader_reserve = sum(
        len(
            json.dumps(
                e2.answer_only_payload(
                    (r := dense.read_json(Path(v["path"])))["question"], r["retrieval"]
                ),
                ensure_ascii=False,
            ).encode()
        )
        + 2048
        + target.OPTIONS["max_tokens"]
        for k, v in contexts.items()
        if k not in readers
    )
    embedding_reserve = sum(
        len(
            json.dumps(
                e2.embedding_payload(base, question), ensure_ascii=False
            ).encode()
        )
        + 2048
        for dataset, queries in current_queries.items()
        for qid, question in queries.items()
        for method in e2.METHODS
        if e2.case_key(dataset, method, qid) not in contexts
    )
    reserve = (
        (embedding + filters) * envelope + embedding_reserve + cached_reader_reserve
    )
    # The original source+child records are already deduplicated by lineage_records.
    identity = [(r["run_id"], r["attempt_id"], r["event"]) for r in physical + drecords]
    if len(set(identity)) != len(identity):
        raise ValueError("E2_pilot_duplicate_source_event")
    development = summarize(physical + drecords)
    if not development["complete"]:
        raise ValueError("E2_pilot_source_cost_unknown")
    reused = {
        k: sum(op["logical_usage"].get(k) or 0 for op in reused_cost)
        for k in ("llm_input_tokens", "llm_output_tokens", "embedding_input_tokens")
    }
    result = copy.deepcopy(base)
    result.update(
        version=VERSION,
        mode="pilot200_pending_approval",
        reader_version=READER,
        outcome_policy=e2.OUTCOME_POLICY,
        reader_template_policy="fixed shared-answer-only-v1 for all methods/datasets; no Thought",
        reader_templates={
            d: target.digest(e2.answer_only_payload("", {"passages": []}))
            for d in base["datasets"]
        },
        reader_calls=reader,
        filter_calls=filters,
        max_posts=reader + filters + embedding,
        max_llm_posts=reader + filters,
        max_embedding_posts=embedding,
        max_combined_tokens=reserve,
        failures="known reader failure continues without retry; unknown/transport/filter/infra/budget/pin fatal; no automatic recovery of failed run",
        pilot_reuse={
            "source_plan": str(source_plan),
            "source_directory": str(source_directory),
            "diagnostic_plan": str(diagnostic_plan),
            "diagnostic_directory": str(diagnostic_directory),
            "files": files,
            "contexts": contexts,
            "readers": readers,
            "development_physical": development,
            "reused_source_known": reused,
        },
        pilot_protocol={
            "cases": total,
            "tuning_only": True,
            "bootstrap_samples": 2000,
            "bootstrap_seed": 42,
            "ci": 0.95,
            "latency": "fresh full latency only for uncached contexts; generation transport and historical timings separate",
            "reserve_formula": "fresh context reader + filter each <=35584; fresh BGE exact UTF8 payload bytes+2048; cached context reader exact UTF8 payload bytes+2048+512",
            "cached_reader_reserve": cached_reader_reserve,
            "fresh_embedding_reserve": embedding_reserve,
            "reader_format_gate": "target Answer parser + one line + no 8word block repeated3times; meaning errors do not stop",
        },
    )
    return result


def verify(plan):
    e2.check_parent_pins(plan)
    for name, sha in plan["code_sha256"].items():
        if dense.sha256_file(e2.ROOT / name) != sha:
            raise ValueError("E2_code_changed")
    reuse = plan["pilot_reuse"]
    candidate = prepare(
        plan["e1_plan"],
        plan["e1_workspace"],
        reuse["source_plan"],
        reuse["source_directory"],
        reuse["diagnostic_plan"],
        reuse["diagnostic_directory"],
    )
    if candidate != plan:
        raise ValueError("E2_pilot_plan_or_reuse_changed")
    return True


def _source(plan, key):
    ref = plan.get("pilot_reuse", {}).get("contexts", {}).get(key)
    if ref is None:
        return None
    path = Path(ref["path"])
    if dense.sha256_file(path) != ref["sha256"]:
        raise ValueError("E2_pilot_cached_context_changed")
    return dense.read_json(path)


def context_reuse(plan, key):
    row = _source(plan, key)
    if row is None:
        return None
    path = Path(plan["pilot_reuse"]["contexts"][key]["path"])
    operations = []
    for original in row["operations"]:
        if original["operation"] == "reader":
            continue
        op = copy.deepcopy(original)
        op.update(
            reused=True,
            cache_hit=True,
            physical_attempted=False,
            source_directory=str(path.parent),
            source_object_id=original["journal_object_id"],
            producer_run_id=row["run_id"],
            source_client_seconds=original["client_seconds"],
            client_seconds=None,
            transport_seconds=None,
        )
        operations.append(op)
    return (
        copy.deepcopy(row["retrieval"]),
        operations,
        {
            "run_id": row["run_id"],
            "case_sha256": plan["pilot_reuse"]["contexts"][key]["sha256"],
            "source_stage_seconds": row["stage_seconds"],
            "source_wall_seconds": row["wall_seconds"],
            "note": "historical Thought-run values; old reader stage is not reused and no source time is added to current wall time",
        },
    )


def reader_reuse(plan, key, payload):
    source = copy.deepcopy(plan["pilot_reuse"]["readers"][key])
    if source["payload_sha256"] != target.digest(payload):
        raise ValueError("E2_pilot_reused_reader_payload_changed")
    body = dense.read_json(
        Path(source["source_directory"])
        / (source["source_object_id"] + ".response.json")
    )
    source.update(reused=True)
    return body, source


def verify_reuse_result(plan, result):
    key = e2.case_key(result["dataset"], result["method"], result["question_id"])
    source = _source(plan, key)
    if source is not None:
        if (
            result.get("retrieval") != source["retrieval"]
            or result["question"] != source["question"]
        ):
            raise ValueError("E2_pilot_reuse_context_mismatch")
        expected = context_reuse(plan, key)[1]
        actual = [
            op
            for op in result["operations"]
            if op.get("reused") and op["operation"] != "reader"
        ]
        if expected != actual:
            raise ValueError("E2_pilot_reuse_stage_mismatch")
    for op in result["operations"]:
        if not op.get("reused"):
            continue
        if op["operation"] == "reader":
            if key not in plan["pilot_reuse"]["readers"]:
                raise ValueError("E2_pilot_unplanned_reader_reuse")
            payload = e2.configured_reader_payload(
                plan, result["question"], result["retrieval"]
            )
            body, expected = reader_reuse(plan, key, payload)
            if any(op.get(k) != v for k, v in expected.items()) or op[
                "request_payload_sha256"
            ] != target.digest(payload):
                raise ValueError("E2_pilot_reuse_reader_mismatch")
            answer, _ = e2.parse_reader(plan, e2.reader_text(body))
            if result["status"] != "completed" or result["answer"] != answer:
                raise ValueError("E2_pilot_reused_answer_changed")
        elif source is None:
            raise ValueError("E2_pilot_unplanned_context_reuse")


def _usage(ops):
    result = {}
    for name in ("reader", "filter", "query_embedding"):
        selected = [o for o in ops if o["operation"] == name]
        fields = (
            ("embedding_input_tokens",)
            if name == "query_embedding"
            else ("llm_input_tokens", "llm_output_tokens")
        )
        unknown = sum(
            any(o.get("logical_usage", {}).get(k) is None for k in fields)
            for o in selected
            if o.get("physical_attempted") or o.get("reused")
        )
        result[name] = {
            "calls": len(selected),
            "unknown_operations": unknown,
            "complete": unknown == 0,
            "known_subtotal": {
                k: sum(o.get("logical_usage", {}).get(k) or 0 for o in selected)
                for k in (
                    "llm_input_tokens",
                    "llm_output_tokens",
                    "embedding_input_tokens",
                )
            },
        }
    return result


def enrich_report(plan, report):
    # Replaying a stage from an earlier pilot run does not turn its physical
    # cost into development/source expense. Attribute within the same lineage.
    physical_run_ids = {plan.get("parent_run", {}).get("run_id")} | {
        p["run_id"] for p in plan.get("physical_parents", [])
    }

    def pilot_physical(op):
        return not op.get("reused") or op.get("producer_run_id") in physical_run_ids

    for row in report["rows"]:
        cases = [
            r
            for r in report["question_results"]
            if (r["dataset"], r["method"]) == (row["dataset"], row["method"])
        ]
        ops = [o for c in cases for o in c.get("operations", [])]
        fresh = [
            c["wall_seconds"]
            for c in cases
            if c.get("latency_mode") == "fresh_end_to_end"
        ]
        generation = [
            c["reader_generation_seconds"]
            for c in cases
            if c.get("reader_generation_seconds") is not None
        ]
        row.update(
            new_physical_usage_by_operation=_usage(
                [o for o in ops if pilot_physical(o)]
            ),
            reused_source_usage_by_operation=_usage(
                [o for o in ops if o.get("reused") and not pilot_physical(o)]
            ),
            fresh_e2e_cases=len(fresh),
            fresh_reader_cases=len(generation),
            mean_fresh_e2e_seconds=sum(fresh) / len(fresh) if fresh else None,
            mean_reader_transport_seconds=sum(generation) / len(generation)
            if generation
            else None,
            mean_attempted_seconds=None,
            mean_completed_seconds=None,
            limitations="development pilot, not independent confirmation; cached latency not fresh E2E",
        )
    actual_sources = {}
    lineage_sources = {}
    for case in report["question_results"]:
        for op in case.get("operations", []):
            if op.get("reused"):
                identity = (op["producer_run_id"], op["source_object_id"])
                if (
                    identity in actual_sources
                    and actual_sources[identity] != op["logical_usage"]
                ):
                    raise ValueError("E2_pilot_conflicting_reuse_cost")
                if op["producer_run_id"] in (
                    {plan.get("parent_run", {}).get("run_id")}
                    | {p["run_id"] for p in plan.get("physical_parents", [])}
                ):
                    lineage_sources[identity] = op["logical_usage"]
                else:
                    actual_sources[identity] = op["logical_usage"]
    actual_reused = {
        k: sum(u.get(k) or 0 for u in actual_sources.values())
        for k in ("llm_input_tokens", "llm_output_tokens", "embedding_input_tokens")
    }
    report["pilot_accounting"] = {
        "new_physical": report["physical_query_accounting"]["summary"],
        "reused_source_known": actual_reused,
        "available_source_reuse_known": plan["pilot_reuse"]["reused_source_known"],
        "used_source_operations": len(actual_sources),
        "lineage_stage_reuse_known": {
            k: sum(u.get(k) or 0 for u in lineage_sources.values())
            for k in ("llm_input_tokens", "llm_output_tokens", "embedding_input_tokens")
        },
        "lineage_stage_reuse_scope": "already included in physical parent journal; never added again",
        "development_physical": plan["pilot_reuse"]["development_physical"],
        "scope": "reused costs are a subset of development cost; do not add development twice; E1 excluded/incomplete",
    }
    report["paired_comparisons"] = []
    if report["comparison_complete"]:
        for dataset, data in plan["datasets"].items():
            methods = {
                m: {
                    r["question_id"]: r
                    for r in report["question_results"]
                    if r["dataset"] == dataset and r["method"] == m
                }
                for m in e2.METHODS
            }
            n = len(data["question_ids"])
            draws = np.random.default_rng(42).integers(
                0, n, (plan["pilot_protocol"]["bootstrap_samples"], n)
            )
            for i, left in enumerate(e2.METHODS):
                for right in e2.METHODS[i + 1 :]:
                    for metric in ("em", "f1"):
                        delta = np.array(
                            [
                                methods[left][q]["metrics"][metric]
                                - methods[right][q]["metrics"][metric]
                                for q in data["question_ids"]
                            ]
                        )
                        samples = delta[draws].mean(axis=1)
                        report["paired_comparisons"].append(
                            {
                                "dataset": dataset,
                                "left": left,
                                "right": right,
                                "metric": metric,
                                "n": n,
                                "delta": float(delta.mean()),
                                "ci95": np.quantile(samples, [0.025, 0.975]).tolist(),
                                "samples": len(draws),
                                "seed": 42,
                                "interpretation": "descriptive paired tuning bootstrap, no independent confirmation",
                            }
                        )


def write_markdown(plan, report, safe, prefix):
    def number(value, scale=1):
        return "—" if value is None else f"{value * scale:.3f}"

    lines = [
        "# E2 pilot200: " + safe["status"],
        "",
        f"Run `{safe['run_id']}`; plan `{safe['plan_sha256']}`.",
        "",
        "Development/tuning pilot; one fixed shared-answer-only-v1, cap512. Not independent quality evidence.",
        "",
        "| Dataset | Method | EM % | F1 % | Completed / failed / not attempted | Failure % | Passage recall@5 % | RAPTOR provenance % | Fresh E2E s (n) | Reader call s (n) | New R(in/out); F(in/out); BGE(in) | Reused R(in/out); F(in/out); BGE(in) |",
        "|---|---|---:|---:|---|---:|---:|---:|---|---|---|---|",
    ]
    if not report["comparison_complete"]:
        lines.insert(
            4,
            "Сравнение неполное: ниже только техническое покрытие/завершённые группы, не полный comparative result.",
        )
    for row in report["rows"]:

        def usage(field):
            stages = row[field]

            def llm(name):
                values = stages[name]["known_subtotal"]
                return f"{values['llm_input_tokens']}/{values['llm_output_tokens']}"

            return f"R {llm('reader')}; F {llm('filter')}; BGE {stages['query_embedding']['known_subtotal']['embedding_input_tokens']}"

        lines.append(
            f"| {row['dataset']} | {row['method']} | {number(row['em'], 100)} | {number(row['f1'], 100)} | {row['completed']} / {row['attempted_failed']} / {row['not_attempted']} | {number(row['failure_rate'], 100)} | {number(row['passage_recall_at_5'], 100)} | {number(row['provenance_coverage'], 100) if row['method'] == 'raptor' else '—'} | {number(row['mean_fresh_e2e_seconds'])} ({row['fresh_e2e_cases']}) | {number(row['mean_reader_transport_seconds'])} ({row['fresh_reader_cases']}) | {usage('new_physical_usage_by_operation')} | {usage('reused_source_usage_by_operation')} |"
        )
    lines += [
        "",
        "Reader/filter LLM input/output and embedding tokens are separated in JSON; each cell separates reader(R) input/output, filter(F) input/output and BGE input. Not-attempted is not a wrong answer; incomplete groups have null EM/F1. Known reader failures count as0 only in completed groups.",
        "Cached context/reader results are not fresh latency; source timing provenance stays in private per-case data and is never added across runs. RAPTOR provenance coverage is not passage recall@5.",
        "",
        f"Pilot physical lineage known: {safe['known_query_tokens']}; total POST={safe['model_posts']}; current run POST={safe['new_model_posts']}; unknown={safe['new_unknown_attempts']}. Reused source costs are a subset of the separately reported development expense, not additional physical cost. E1known32601955/unknown reserve61588/cost_complete=false separate.",
        "",
    ]
    if not report["comparison_complete"]:
        lines.append("Comparison incomplete; no paired inference reported.")
    for pair in report["paired_comparisons"]:
        lines.append(
            f"{pair['dataset']} {pair['left']}−{pair['right']} {pair['metric']}: Δ={pair['delta']:.4f}, paired95% CI {pair['ci95']}; n={pair['n']},2000resamples/seed42; descriptive tuning result."
        )
    lines += [
        "",
        "Includes mixed Hippo extraction configuration and disclosed source errors; no architecture-only causality. Refs #14; Draft, no merge/holdout/S500.",
    ]
    prefix.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# One bounded continuation of the terminal pilot, not a general retry engine.
PILOT_RUNTIME = "41ee909c14ffca5dff552fa65d46f33f39d9ed8d"
CONTINUATION_BYTES = 65536


def input_size_bounds(plan):
    """Worst top5 escaped-text size, no retrieval, labels or token-count claims."""
    source = dense.read_json(Path(plan["e1_plan"]))
    bounds = {}
    for dataset, data in plan["datasets"].items():
        raw = Path(source["data_root"]) / f"data/processed/{dataset}"
        corpus = dense.read_json(raw / "corpus.json")
        queries = e2.select_in_view(
            dense.read_json(raw / "queries.json"), data["question_ids"], "query"
        )
        question = max(
            queries,
            key=lambda q: len(json.dumps(q["question"], ensure_ascii=False).encode()),
        )["question"]
        row = next(r for r in data["indexes"] if r["method"] == "raptor")
        tree = dense.read_json(
            Path(plan["e1_workspace"]) / row["e1_row"]["output"] / "tree.json"
        )
        nodes = [
            {"title": f"RAPTOR node {n['index']}", "text": n["text"]}
            for n in tree["nodes"]
        ]
        for method, items in (("raptor", nodes), ("dense_or_hippo", corpus)):
            # Projection has identical title/text escaping to the message string;
            # all other per-passage delimiters have constant length.
            selected = sorted(
                items,
                key=lambda x: len(
                    json.dumps(
                        {k: x[k] for k in ("title", "text")}, ensure_ascii=False
                    ).encode()
                ),
                reverse=True,
            )[:5]
            payload = e2.answer_only_payload(
                question, {"passages": selected}, message_limit=2**63 - 1
            )
            bounds[f"{dataset}/{method}"] = {
                "nodes": len(items),
                "largest_5_text_bytes": [len(x["text"].encode()) for x in selected],
                "max_question_json_bytes": len(
                    json.dumps(question, ensure_ascii=False).encode()
                ),
                "synthetic_top5_message_bytes": len(
                    json.dumps(payload["messages"], ensure_ascii=False).encode()
                ),
            }
    return bounds


def validate_original_pilot(parent):
    """Rebuild all original data/index/reuse pins with current verification code."""
    import hashlib
    import subprocess

    if (
        parent.get("version") != VERSION
        or parent.get("parent_run")
        or parent.get("pilot_continuation")
    ):
        raise ValueError("E2_only_original_pilot_can_parent")
    for name, sha in parent["code_sha256"].items():
        original = subprocess.check_output(
            ["git", "-C", str(e2.ROOT), "show", PILOT_RUNTIME + ":" + name]
        )
        # Original approved Windows runtime hashed CRLF working-tree bytes;
        # Git stores LF blobs. Reconstruct that exact representation, not a new SHA.
        original = original.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if hashlib.sha256(original).hexdigest() != sha:
            raise ValueError("E2_pilot_parent_runtime_SHA_changed")
    reuse = parent["pilot_reuse"]
    rebuilt = prepare(
        parent["e1_plan"],
        parent["e1_workspace"],
        reuse["source_plan"],
        reuse["source_directory"],
        reuse["diagnostic_plan"],
        reuse["diagnostic_directory"],
    )
    rebuilt["code_sha256"] = parent["code_sha256"]
    if rebuilt != parent:
        raise ValueError("E2_original_pilot_contract_changed")


def continuation_snapshot(parent_path, directory):
    parent_path, directory = Path(parent_path).resolve(), Path(directory).resolve()
    parent = dense.read_json(parent_path)
    validate_original_pilot(parent)
    mp = directory / "manifest.json"
    manifest = dense.read_json(mp)
    ref = verified_reference(manifest, mp)
    if (
        manifest["status"] != "failed"
        or manifest["plan_sha256"] != target.digest(parent)
        or ref["status"] != "verified"
        or not ref["summary"]["complete"]
        or (directory / "running.lock").exists()
    ):
        raise ValueError("E2_pilot_parent_not_terminal_known")
    claim = (
        Path(parent["e1_workspace"])
        / ".cache"
        / f"e2-{target.digest(parent)}.claim.json"
    )
    if dense.read_json(claim) != {"directory": str(directory)}:
        raise ValueError("E2_pilot_parent_claim_changed")
    files = {}  # Historical source pins remain in pilot_reuse, without duplication.
    for path in (parent_path, mp, directory / "usage.jsonl", claim):
        files[str(path)] = dense.sha256_file(path)
    records = read_records(directory / "usage.jsonl")
    cases, overflow, seen = {}, {}, set()
    for key, sha in manifest["results"].items():
        path = directory / f"question-{key}.json"
        if dense.sha256_file(path) != sha:
            raise ValueError("E2_pilot_parent_result_changed")
        result = dense.read_json(path)
        if key != e2.case_key(
            result["dataset"], result["method"], result["question_id"]
        ):
            raise ValueError("E2_pilot_parent_case_changed")
        e2.verify_saved_case(parent, directory, result, records)
        files[str(path)] = sha
        if result["status"] == "completed":
            # Actual outbound reader payload, parser and result verified above;
            # increased admission does not alter a single byte of this payload.
            payload = e2.answer_only_payload(
                result["question"],
                result["retrieval"],
                message_limit=CONTINUATION_BYTES,
            )
            if target.digest(payload) != result["reader_request_sha256"]:
                raise ValueError("E2_completed_payload_changed")
            cases[key] = {
                "path": str(path),
                "sha256": sha,
                "dataset": result["dataset"],
                "method": result["method"],
                "question_id": result["question_id"],
                "status": "completed",
            }
        elif (
            result.get("fatal")
            and result["method"] == "raptor"
            and result.get("error")
            == {"type": "ValueError", "reason": "E2_context_overflow_no_truncation"}
            and result.get("retrieval", {}).get("passages")
            and [o["operation"] for o in result["operations"]] == ["query_embedding"]
            and all(
                o.get("physical_attempted") and o["status"] == "completed"
                for o in result["operations"]
            )
        ):
            overflow[key] = {"path": str(path), "sha256": sha}
        else:
            raise ValueError("E2_only_pre_reader_overflow_can_continue")
        for op in result["operations"]:
            if op.get("reused"):
                continue
            identity = op["journal_object_id"]
            if identity in seen:
                raise ValueError("E2_duplicate_parent_operation")
            seen.add(identity)
            for suffix in (".json", ".response.json"):
                fp = directory / (identity + suffix)
                files[str(fp)] = dense.sha256_file(fp)
    if len(overflow) != 1 or seen != {
        r["object_id"] for r in records if r["event"] == "started"
    }:
        raise ValueError("E2_unattributed_or_nonunique_parent_attempt")
    return (
        parent,
        {
            "plan": str(parent_path),
            "directory": str(directory),
            "run_id": manifest["run_id"],
            "files": files,
            "cases": cases,
            "summary": ref["summary"],
            "runtime_commit": PILOT_RUNTIME,
        },
        overflow,
    )


def prepare_input_continuation(parent_path, directory, proof_path):
    parent, snapshot, overflow = continuation_snapshot(parent_path, directory)
    proof_path = Path(proof_path).resolve()
    proof = dense.read_json(proof_path)
    if (
        proof["message_utf8_bytes_limit"] != CONTINUATION_BYTES
        or proof["size_bounds"] != input_size_bounds(parent)
        or max(v["synthetic_top5_message_bytes"] for v in proof["size_bounds"].values())
        > CONTINUATION_BYTES
        or proof["conservative_input_plus_output_bound"]
        != CONTINUATION_BYTES + 2048 + target.OPTIONS["max_tokens"]
        or proof["reported_context_window"] != 262144
    ):
        raise ValueError("E2_input_bound_proof_changed")
    for filename, sha in proof["tokenizer_files"].items():
        if dense.sha256_file(Path(filename)) != sha:
            raise ValueError("E2_native_tokenizer_pin_changed")
    fresh = copy.deepcopy(parent)
    fresh["code_sha256"] = {
        name: dense.sha256_file(e2.ROOT / name) for name in e2.CODE_FILES
    }
    fresh["pilot_reuse"]["contexts"].update(overflow)
    fresh["pilot_reuse"]["files"][str(proof_path)] = dense.sha256_file(proof_path)
    fresh["pilot_reuse"]["files"].update(proof["tokenizer_files"])
    expected = {
        e2.case_key(d, m, q): {"dataset": d, "method": m, "question_id": q}
        for d, data in fresh["datasets"].items()
        for m in e2.METHODS
        for q in data["question_ids"]
    }
    if not set(snapshot["cases"]) <= set(expected) or not set(overflow) <= set(
        expected
    ):
        raise ValueError("E2_parent_ID_outside_plan")
    remaining = {k: v for k, v in expected.items() if k not in snapshot["cases"]}
    if any(v["method"] != "raptor" for v in remaining.values()):
        raise ValueError("E2_continuation_only_remaining_RAPTOR")
    source = dense.read_json(Path(parent["e1_plan"]))
    queries = {
        d: {
            q["id"]: q["question"]
            for q in e2.select_in_view(
                dense.read_json(
                    Path(source["data_root"]) / f"data/processed/{d}/queries.json"
                ),
                data["question_ids"],
                "query",
            )
        }
        for d, data in fresh["datasets"].items()
    }
    readers = sum(k not in fresh["pilot_reuse"]["readers"] for k in remaining)
    embedding = sum(k not in fresh["pilot_reuse"]["contexts"] for k in remaining)
    er = sum(
        len(
            json.dumps(
                e2.embedding_payload(fresh, queries[c["dataset"]][c["question_id"]]),
                ensure_ascii=False,
            ).encode()
        )
        + 2048
        for k, c in remaining.items()
        if k not in fresh["pilot_reuse"]["contexts"]
    )
    # Per-request checked_post uses exact bytes; reserve a max envelope for every
    # remaining reader, including those whose context is already available.
    reserve = (
        readers * (CONTINUATION_BYTES + 1024 + 2048 + target.OPTIONS["max_tokens"]) + er
    )
    available_tokens = parent["max_combined_tokens"] - sum(
        snapshot["summary"]["known_subtotal"].values()
    )
    available_posts = parent["max_posts"] - snapshot["summary"]["attempts"]
    if reserve > available_tokens or readers + embedding > available_posts:
        raise ValueError("E2_continuation_exceeds_original_remainder")
    fresh.update(
        mode="pilot200_continuation_pending_approval",
        pilot_continuation={
            "parent_plan": str(Path(parent_path).resolve()),
            "parent_directory": str(Path(directory).resolve()),
            "bound_proof": str(proof_path),
            "overflow_context_cases": overflow,
            "recovery": "none after fatal; same-output only after clean method boundary; no unknown replay",
            "embedding_reserve": er,
            "inherited_payloads_unchanged": len(snapshot["cases"]),
        },
        parent_run=snapshot,
        remaining_cases=list(remaining.values()),
        message_utf8_bytes_limit=CONTINUATION_BYTES,
        reader_calls=readers,
        filter_calls=0,
        max_llm_posts=readers,
        max_embedding_posts=embedding,
        max_posts=readers + embedding,
        max_combined_tokens=reserve,
        original_remaining_tokens=available_tokens,
        original_remaining_posts=available_posts,
    )
    return fresh


def verify_continuation(plan):
    spec = plan["pilot_continuation"]
    candidate = prepare_continuation(
        spec["parent_plan"], spec["parent_directory"], spec["bound_proof"]
    )
    if candidate != plan:
        raise ValueError("E2_continuation_plan_changed")
    return True


TRANSPORT_PARENT_RUNTIME = "3914d70a17554fd6f466026b0aa5f60a02cde715"


def validate_transport_parent(parent):
    """Only the issued first continuation can supply a sealed unknown case."""
    import hashlib
    import subprocess

    if not parent.get("pilot_continuation") or parent.get("sealed_unknown"):
        raise ValueError("E2_only_first_continuation_can_supply_unknown")
    for name, sha in parent["code_sha256"].items():
        original = subprocess.check_output(
            ["git", "-C", str(e2.ROOT), "show", TRANSPORT_PARENT_RUNTIME + ":" + name]
        )
        lf = original.replace(b"\r\n", b"\n")
        if sha not in {
            hashlib.sha256(lf).hexdigest(),
            hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest(),
        }:
            raise ValueError("E2_transport_parent_runtime_changed")
    spec = parent["pilot_continuation"]
    candidate = prepare_input_continuation(
        spec["parent_plan"], spec["parent_directory"], spec["bound_proof"]
    )
    candidate["code_sha256"] = parent["code_sha256"]
    if candidate != parent:
        raise ValueError("E2_transport_parent_contract_changed")


def seal_unknown_reader(parent, directory, result, records):
    """Verify an absent reader response, never turn an unknown POST into a miss."""
    if (
        result["status"] != "attempted_failed"
        or not result.get("fatal")
        or result.get("error", {}).get("type") != "ConnectionError"
        or "RemoteDisconnected" not in result["error"]["reason"]
        or result["method"] != "raptor"
        or result.get("answer")
        or result.get("raw_answer")
        or [o["operation"] for o in result["operations"]]
        != ["query_embedding", "reader"]
    ):
        raise ValueError("E2_not_terminal_remote_reader_failure")
    embedding, reader = result["operations"]
    partial = copy.deepcopy(result)
    partial["operations"] = [embedding]
    e2.verify_saved_case(parent, directory, partial, records)
    payload = e2.configured_reader_payload(
        parent, result["question"], result["retrieval"]
    )
    object_id = target.digest(
        {
            "plan": target.digest(parent),
            "method": result["method"],
            "dataset": result["dataset"],
            "qid": result["question_id"],
            "operation": "reader",
            "payload": payload,
        }
    )
    terminal = [
        r
        for r in records
        if r["event"] == "finished" and r.get("object_id") == object_id
    ]
    unknown = [
        r
        for r in records
        if r["event"] == "finished" and r["usage_status"] != "complete"
    ]
    checkpoint = Path(directory) / (object_id + ".json")
    saved = dense.read_json(checkpoint)
    if (
        len(terminal) != 1
        or terminal != unknown
        or terminal[0]["status"] != "error"
        or terminal[0]["kind"] != "llm"
        or terminal[0]["provider"] != "target_api"
        or terminal[0]["model"] != e2.MODEL
        or terminal[0]["llm_input_tokens"] is not None
        or terminal[0]["llm_output_tokens"] is not None
        or reader.get("logical_usage", {}).get("llm_input_tokens") is not None
        or reader.get("logical_usage", {}).get("llm_output_tokens") is not None
        or reader["journal_object_id"] != object_id
        or reader["request_payload_sha256"] != target.digest(payload)
        or result["reader_request_sha256"] != target.digest(payload)
        or not reader.get("physical_attempted")
        or reader["status"] != "failed"
        or saved != {"status": "started", "key": object_id}
        or (Path(directory) / (object_id + ".response.json")).exists()
    ):
        raise ValueError("E2_unknown_reader_identity_or_outcome_changed")
    return {
        "run_id": result["run_id"],
        "object_id": object_id,
        "case_key": e2.case_key(
            result["dataset"], result["method"], result["question_id"]
        ),
        "reservation_tokens": len(json.dumps(payload, ensure_ascii=False).encode())
        + 2048
        + target.OPTIONS["max_tokens"],
        "usage_status": "unknown",
        "response_status": "absent",
        "retry": "forbidden",
        "metric_policy": "terminal infrastructure failure; pipeline EM/F1=0, failure disclosed; not a wrong reader answer",
    }


def prepare_unattempted(parent_path, directory, proof_path):
    """Explicitly reauthorized unattempted-only run; keep one unknown sealed."""
    parent_path, directory = Path(parent_path).resolve(), Path(directory).resolve()
    parent = dense.read_json(parent_path)
    validate_transport_parent(parent)
    e2.check_parent_pins(parent)
    mp = directory / "manifest.json"
    m = dense.read_json(mp)
    ref = verified_reference(m, mp)
    if (
        m["status"] != "failed"
        or m["plan_sha256"] != target.digest(parent)
        or ref["status"] != "verified"
        or (directory / "running.lock").exists()
    ):
        raise ValueError("E2_transport_parent_not_terminal")
    records = read_records(directory / "usage.jsonl")
    starts = [r for r in records if r["event"] == "started"]
    ends = [r for r in records if r["event"] == "finished"]
    if (
        records.corrupt_tail
        or len(starts) != len(ends)
        or {r["attempt_id"] for r in starts} != {r["attempt_id"] for r in ends}
    ):
        raise ValueError("E2_unfinished_or_corrupt_transport_parent")
    claim = (
        Path(parent["e1_workspace"])
        / ".cache"
        / f"e2-{target.digest(parent)}.claim.json"
    )
    parent_claim = (
        Path(parent["e1_workspace"])
        / ".cache"
        / f"e2-continuation-of-{target.digest(parent['parent_run']['files'])}.claim.json"
    )
    if dense.read_json(claim) != {"directory": str(directory)} or dense.read_json(
        parent_claim
    ) != {"plan_sha256": target.digest(parent), "directory": str(directory)}:
        raise ValueError("E2_transport_parent_claim_changed")
    cases = copy.deepcopy(parent["parent_run"]["cases"])
    files = dict(parent["parent_run"]["files"])
    for path in (parent_path, mp, directory / "usage.jsonl", claim, parent_claim):
        files[str(path)] = dense.sha256_file(path)
    unknowns, seen = [], set()
    for key, sha in m["results"].items():
        path = directory / f"question-{key}.json"
        if key in cases or dense.sha256_file(path) != sha:
            raise ValueError("E2_transport_parent_case_changed")
        row = dense.read_json(path)
        if key != e2.case_key(row["dataset"], row["method"], row["question_id"]):
            raise ValueError("E2_transport_parent_key_changed")
        if row["status"] == "completed":
            e2.verify_saved_case(parent, directory, row, records)
        else:
            unknowns.append(seal_unknown_reader(parent, directory, row, records))
        cases[key] = {
            "path": str(path),
            "sha256": sha,
            "dataset": row["dataset"],
            "method": row["method"],
            "question_id": row["question_id"],
            "status": row["status"],
        }
        files[str(path)] = sha
        for op in row["operations"]:
            if op.get("reused"):
                continue
            opid = op["journal_object_id"]
            if opid in seen:
                raise ValueError("E2_duplicate_transport_parent_attempt")
            seen.add(opid)
            for suffix in (".json", ".response.json"):
                artifact = directory / (opid + suffix)
                if artifact.exists():
                    files[str(artifact)] = dense.sha256_file(artifact)
    if len(unknowns) != 1 or seen != {r["object_id"] for r in starts}:
        raise ValueError("E2_not_one_sealed_unknown_or_unattributed_attempt")
    sealed = unknowns[0]
    fresh = copy.deepcopy(parent)
    fresh["code_sha256"] = {n: dense.sha256_file(e2.ROOT / n) for n in e2.CODE_FILES}
    expected = {
        e2.case_key(d, m, q): {"dataset": d, "method": m, "question_id": q}
        for d, data in parent["datasets"].items()
        for m in e2.METHODS
        for q in data["question_ids"]
    }
    if not set(cases) <= set(expected):
        raise ValueError("E2_transport_parent_case_outside_view")
    remaining = {k: r for k, r in expected.items() if k not in cases}
    if any(r["method"] != "raptor" for k, r in remaining.items()):
        raise ValueError("E2_remaining_only_unattempted_RAPTOR")
    if Path(proof_path).resolve() != Path(parent["pilot_continuation"]["bound_proof"]):
        raise ValueError("E2_input_proof_changed_after_transport_stop")
    source = dense.read_json(Path(parent["e1_plan"]))
    er = 0
    for dataset, data in parent["datasets"].items():
        queries = e2.select_in_view(
            dense.read_json(
                Path(source["data_root"]) / f"data/processed/{dataset}/queries.json"
            ),
            data["question_ids"],
            "query",
        )
        er += sum(
            len(
                json.dumps(
                    e2.embedding_payload(parent, q["question"]), ensure_ascii=False
                ).encode()
            )
            + 2048
            for q in queries
            if e2.case_key(dataset, "raptor", q["id"]) in remaining
            and e2.case_key(dataset, "raptor", q["id"])
            not in parent["pilot_reuse"]["contexts"]
        )
    n = sum(k not in parent["pilot_reuse"]["readers"] for k in remaining)
    embeddings = sum(k not in parent["pilot_reuse"]["contexts"] for k in remaining)
    reserve = n * (CONTINUATION_BYTES + 1024 + 2048 + target.OPTIONS["max_tokens"]) + er
    available = (
        parent["max_combined_tokens"]
        - sum(ref["summary"]["known_subtotal"].values())
        - sealed["reservation_tokens"]
    )
    posts = parent["max_posts"] - len(starts)
    if reserve > available or n + embeddings > posts:
        raise ValueError("E2_sealed_unknown_reservation_or_POST_budget_exceeded")
    fresh.update(
        mode="pilot200_unattempted_after_explicit_reauthorization",
        sealed_unknown=[sealed],
        physical_parents=[
            {
                "directory": parent["parent_run"]["directory"],
                "run_id": parent["parent_run"]["run_id"],
            },
            {"directory": str(directory), "run_id": m["run_id"]},
        ],
        parent_run={
            "plan": str(parent_path),
            "directory": str(directory),
            "run_id": m["run_id"],
            "files": files,
            "cases": cases,
            "summary": ref["summary"],
            "runtime_commit": TRANSPORT_PARENT_RUNTIME,
        },
        pilot_continuation={
            "parent_plan": str(parent_path),
            "parent_directory": str(directory),
            "bound_proof": str(Path(proof_path).resolve()),
            "reauthorized_unattempted_only": True,
            "automatic_recovery": 0,
            "embedding_reserve": er,
            "inherited_terminal_cases": len(cases),
            "failure_score_policy": sealed["metric_policy"],
        },
        remaining_cases=list(remaining.values()),
        reader_calls=n,
        filter_calls=0,
        max_llm_posts=n,
        max_embedding_posts=embeddings,
        max_posts=n + embeddings,
        max_combined_tokens=reserve,
        original_remaining_tokens=available,
        original_remaining_posts=posts,
    )
    fresh["pilot_protocol"]["reserve_formula"] = (
        "new readers*(65536+1024+2048+512) + exact new BGE UTF8 payload bytes+2048; sealed unknown reserve subtracted before new budget"
    )
    return fresh


def prepare_continuation(parent_path, directory, proof_path):
    parent = dense.read_json(Path(parent_path))
    if parent.get("pilot_continuation"):
        return prepare_unattempted(parent_path, directory, proof_path)
    return prepare_input_continuation(parent_path, directory, proof_path)
