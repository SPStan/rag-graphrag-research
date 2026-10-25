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
                [o for o in ops if not o.get("reused")]
            ),
            reused_source_usage_by_operation=_usage(
                [o for o in ops if o.get("reused")]
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
    for case in report["question_results"]:
        for op in case.get("operations", []):
            if op.get("reused"):
                identity = (op["producer_run_id"], op["source_object_id"])
                if (
                    identity in actual_sources
                    and actual_sources[identity] != op["logical_usage"]
                ):
                    raise ValueError("E2_pilot_conflicting_reuse_cost")
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
        f"New physical known: {safe['known_query_tokens']}; new POST={safe['new_model_posts']}; unknown={safe['new_unknown_attempts']}. Reused source costs are a subset of the separately reported development expense, not additional physical cost. E1known32601955/unknown reserve61588/cost_complete=false separate.",
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
