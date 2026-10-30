"""Offline freeze of S500 configuration/reuse; deliberately has no execute mode."""

import argparse
import ast
import copy
import json
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

from scripts import e1_indexers as indexes
from scripts import e2_evaluation as e2
from scripts import e2_pilot as pilot
from scripts import run_dense as dense
from scripts import run_dense_target as target
from scripts import token_accounting as accounting

ROOT = Path(__file__).resolve().parents[1]
PLAN = "results/summary/e2-pilot200-unattempted-plan.json"
OUTPUT = "results/raw/e2-pilot200-unattempted-v1"
PUBLIC = "results/summary/full-experiment.json"
FIELDS = accounting.TOKEN_FIELDS
CONTRACT = (
    "endpoint",
    "embedding_endpoint",
    "reader_model",
    "embedding_model",
    "embedding_digest",
    "reader_options",
    "reader_templates",
    "reader_version",
    "parser",
    "evaluator",
    "top_k",
    "context_order",
    "hippo",
    "hippo_commit",
    "raptor_commit",
    "outcome_policy",
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def contract(plan):
    return {key: plan[key] for key in CONTRACT}


def check_split(ids, split):
    require(len(ids) == len(set(ids)) == 500, "S500_unique_ordered_500")
    for name, start, end in (
        ("pilot200_ids", 0, 200),
        ("signal_tuning_ids", 0, 300),
        ("signal_check_ids", 300, 400),
        ("legacy_holdout_reserved_ids", 400, 500),
    ):
        require(split[name] == ids[start:end], "split_or_pilot_changed")
    require(split["seed"] == 42, "split_seed_changed")


class Roots:
    """Translate only declared historical roots; never rewrite immutable plans."""

    def __init__(self, artifact, data, index, original, source):
        self.artifact, self.data, self.index = map(Path, (artifact, data, index))
        self.pairs = [
            (Path(original), self.artifact),
            (Path(source["data_root"]), self.data),
            (Path(source["workspace"]), self.index),
        ]

    def resolve(self, path):
        path = Path(path)
        for old, new in self.pairs:
            if path.is_relative_to(old):
                return new / path.relative_to(old)
        return path

    def safe(self, path):
        path = self.resolve(path)
        for name, root in (
            ("artifact", self.artifact),
            ("index", self.index),
            ("data", self.data),
            ("repo", ROOT),
        ):
            if path.is_relative_to(root):
                return name + ":" + path.relative_to(root).as_posix()
        raise ValueError("undeclared_public_path")


@contextmanager
def offline_io(roots):
    """Use existing strict readers with relocation and a hard network prohibition."""
    read, sha = dense.read_json, dense.sha256_file
    records, reference = accounting.read_records, accounting.verified_reference

    def read_json(path):
        require(Path(path).name != "labels.json", "gold_read_forbidden")
        return read(roots.resolve(path))

    def verify_reference(manifest, path):
        return reference(manifest, roots.resolve(path))

    def read_records(path):
        return records(roots.resolve(path))

    with ExitStack() as stack:
        for name in (
            "requests.sessions.Session.request",
            "socket.socket.connect",
            "socket.socket.connect_ex",
        ):
            stack.enter_context(patch(name, side_effect=RuntimeError("HTTP_forbidden")))
        stack.enter_context(patch.object(dense, "read_json", read_json))
        stack.enter_context(
            patch.object(dense, "sha256_file", lambda p: sha(roots.resolve(p)))
        )
        for module in (accounting, pilot):
            stack.enter_context(patch.object(module, "read_records", read_records))
            stack.enter_context(
                patch.object(module, "verified_reference", verify_reference)
            )
        yield


def classify(plan, producer, directory, result, sha, queries, records):
    """A referenced missing/broken result is incompatible, never a fresh miss."""
    try:
        require(contract(producer) == contract(plan), "semantic_contract_changed")
        require(
            dense.sha256_file(
                directory
                / f"question-{e2.case_key(result['dataset'], result['method'], result['question_id'])}.json"
            )
            == sha,
            "result_SHA_changed",
        )
        require(
            result["question"] == queries[result["question_id"]], "question_changed"
        )

        def pin(p):
            return next(
                x
                for x in p["datasets"][result["dataset"]]["indexes"]
                if x["method"] == result["method"]
            )

        require(pin(plan) == pin(producer), "index_contract_changed")
        dataset = result["dataset"]
        require(
            plan["datasets"][dataset].get("corpus_sha256")
            == producer["datasets"][dataset].get("corpus_sha256"),
            "corpus_contract_changed",
        )
        require(
            result["reader_request_sha256"]
            == target.digest(
                e2.configured_reader_payload(
                    plan, result["question"], result["retrieval"]
                )
            ),
            "reader_payload_changed",
        )
        if result["status"] == "completed":
            e2.verify_saved_case(producer, directory, result, records)
            return "compatible_completed", "exact_payload_checkpoint_usage"
        sealed = pilot.seal_unknown_reader(producer, directory, result, records)
        require(sealed in plan["sealed_unknown"], "unapproved_terminal_failure")
        return "terminal_failure", "sealed_unknown_no_retry"
    except (OSError, ValueError, KeyError) as exc:
        return "incompatible", type(exc).__name__ + ":" + str(exc)


def usage_fields(operation):
    return (
        ("embedding_input_tokens",)
        if operation == "query_embedding"
        else ("llm_input_tokens", "llm_output_tokens")
    )


def usage_complete(operation):
    return all(
        operation["logical_usage"].get(key) is not None
        for key in usage_fields(operation["operation"])
    )


def usage_add(totals, operation):
    for key in FIELDS:
        value = operation["logical_usage"].get(key)
        if value is not None:
            totals[key] += value


def usage_row():
    return {
        "known_operations": 0,
        "unknown_operations": 0,
        "partial_operations": 0,
        "fully_unknown_operations": 0,
        "unknown_fields": dict.fromkeys(FIELDS, 0),
        "known_subtotal": dict.fromkeys(FIELDS, 0),
        "forecast_complete": {
            "operations": 0,
            "subtotal": dict.fromkeys(FIELDS, 0),
            "maximum_operation_tokens": None,
        },
    }


def observe_usage(row, operation):
    """Preserve every reported token; forecast only fully measured operations."""
    usage_add(row["known_subtotal"], operation)
    fields = usage_fields(operation["operation"])
    values = operation["logical_usage"]
    complete = usage_complete(operation)
    row["known_operations" if complete else "unknown_operations"] += 1
    for key in fields:
        row["unknown_fields"][key] += values.get(key) is None
    if not complete:
        partial = any(values.get(key) is not None for key in fields)
        row["partial_operations" if partial else "fully_unknown_operations"] += 1
        return
    stats = row["forecast_complete"]
    stats["operations"] += 1
    for key in fields:
        stats["subtotal"][key] += values[key]
    total = sum(values[key] for key in fields)
    prior = stats["maximum_operation_tokens"]
    stats["maximum_operation_tokens"] = total if prior is None else max(prior, total)


def budget(configurations, queries, plan, bounds, logical):
    posts, reserve, forecast = Counter(), Counter(), {}
    missing_observations, allocations = [], []
    headroom = 0
    for config in configurations:
        d, m = config["dataset"], config["method"]
        n = len(config["missing_ids"])
        operations = ("reader", "query_embedding") + (
            ("filter",) if m == "hipporag2" else ()
        )
        for operation in operations:
            posts[operation] += n
        bound = bounds[f"{d}/{'raptor' if m == 'raptor' else 'dense_or_hippo'}"][
            "synthetic_top5_message_bytes"
        ]
        require(bound <= plan["message_utf8_bytes_limit"], "full500_input_overflow")
        reader_reserve = bound + 1024 + 2048 + 512
        reserve["reader"] += n * reader_reserve
        reserve["filter"] += n * (65536 + 1024 + 2048 + 512) if m == "hipporag2" else 0
        if n:
            headroom = max(
                headroom,
                reader_reserve,
                65536 + 1024 + 2048 + 512 if m == "hipporag2" else 0,
            )
        for q in config["missing_ids"]:
            payload = e2.embedding_payload(plan, queries[d][q])
            require(
                len(queries[d][q].encode()) <= plan["query_utf8_bytes_limit"],
                "query_overflow",
            )
            amount = len(json.dumps(payload, ensure_ascii=False).encode()) + 2048
            reserve["query_embedding"] += amount
            headroom = max(headroom, amount)
        for operation in operations:
            stats = logical.get(d + "/" + m, {}).get(operation, usage_row())[
                "forecast_complete"
            ]
            samples = stats["operations"]
            if n and not samples:
                missing_observations.append(d + "/" + m + "/" + operation)
            for key in usage_fields(operation):
                field = operation + "/" + key
                estimate = (
                    n * stats["subtotal"][key] / samples
                    if samples
                    else 0
                    if not n
                    else None
                )
                prior = forecast.get(field, 0)
                forecast[field] = (
                    None if prior is None or estimate is None else prior + estimate
                )
            allocations.append(
                {
                    "dataset": d,
                    "method": m,
                    "operation": operation,
                    "new_calls_upper": n,
                    "complete_pilot_operations": samples,
                    "pilot_maximum_operation_tokens": stats["maximum_operation_tokens"],
                    "allocation_tokens": n * stats["maximum_operation_tokens"]
                    if samples
                    else 0
                    if not n
                    else None,
                }
            )
    complete = not missing_observations
    total_forecast = round(sum(forecast.values()), 3) if complete else None
    empirical = sum(a["allocation_tokens"] for a in allocations) if complete else None
    return {
        "new_posts_upper": dict(posts),
        "new_posts_total_upper": sum(posts.values()),
        "forecast_tokens_by_operation": {
            k: round(v, 3) if v is not None else None
            for k, v in sorted(forecast.items())
        },
        "forecast_known_combined_tokens": total_forecast,
        "forecast_complete": complete,
        "forecast_missing_observations": missing_observations,
        "conservative_reservations_by_operation": dict(reserve),
        "conservative_combined_tokens": sum(reserve.values()),
        "reserve_is_measured_usage": False,
        "authorized": False,
        "forecast_policy": "per-configuration means of fully measured operations only; numerator and denominator use the same complete subset; partial known tokens retained in reporting only; absent observations produce null, not zero",
        "operational_budget_proposal": {
            "authorized": False,
            "completion_guaranteed": False,
            "basis": "missing calls times maximum fully measured pilot operation tokens per configuration/operation, plus one largest request admission reservation; no quality-based selection or rounded target cap",
            "allocations": allocations,
            "pilot_maximum_allocation_tokens": empirical,
            "admission_headroom_tokens": headroom,
            "proposed_new_token_cap": empirical + headroom if complete else None,
            "margin_over_forecast_tokens": round(
                empirical + headroom - total_forecast, 3
            )
            if complete
            else None,
            "required_preflight": "single serial worker; before each POST require new_known + new_unknown_reserves + in_flight_reserves + exact_candidate_reservation <= approved_new_cap and operation/total POST caps; reserve before transport; stop without POST if insufficient; reconcile actual usage durably; any new unknown/partial/transport/budget/pin error stops; no retry or automatic continuation",
            "transport_reservation": "existing checked_post: serialized payload UTF8 bytes + 2048 + max_tokens for LLM; fixed reader cap512 unchanged; admission upper includes1024 envelope",
            "existing_unknown_reserve_separate": sum(
                x["reservation_tokens"] for x in plan.get("sealed_unknown", [])
            ),
            "scope": "new missing cases only; E1, development, parent known expense and historical unknown remain separate, never charged twice; approved execution-plan integration and verification still required",
            "insufficient_budget": "stop before next POST; may finish fewer than1800 cases even with no technical error; further budget requires a new decision",
        },
        "scope": "proposal for missing cases only; issue15 budget criterion pending approval; old pilot POST allowance exhausted; removed administrative90M ceiling is not research authorization",
    }


def freeze(artifact_root, data_root, index_root):
    artifact_root, data_root, index_root = map(
        lambda p: Path(p).resolve(), (artifact_root, data_root, index_root)
    )
    plan = dense.read_json(artifact_root / PLAN)
    source = dense.read_json(index_root / ".cache/e1-hotpot-local-recovery2-plan.json")
    original = Path(plan["parent_run"]["directory"]).parents[2]
    roots = Roots(artifact_root, data_root, index_root, original, source)
    with offline_io(roots):
        return build(plan, source, roots)


def build(plan, source, roots):
    require(
        plan["reader_options"] == target.OPTIONS and plan["reader_model"] == e2.MODEL,
        "runtime_options_changed",
    )
    require(
        plan["reader_version"] == pilot.READER
        and plan["message_utf8_bytes_limit"] == 65536,
        "reader_contract_changed",
    )
    require(
        dense.sha256_file(plan["e1_plan"]) == plan["e1_plan_sha256"], "E1_plan_changed"
    )
    # All inference/evaluator modules are byte-identical to the last execution.
    # e2_pilot has a subsequent accounting-only correction: compare its reuse functions.
    import os
    import subprocess

    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    old = subprocess.check_output(
        ["git", "-C", str(ROOT), "show", "4bd1d25:scripts/e2_pilot.py"], env=env
    ).decode()
    names = {
        "context_reuse",
        "reader_reuse",
        "verify_reuse_result",
        "seal_unknown_reader",
    }
    trees = [
        ast.parse(text)
        for text in (old, (ROOT / "scripts/e2_pilot.py").read_text(encoding="utf-8"))
    ]
    signatures = [
        {
            n.name: ast.dump(n, include_attributes=False)
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in names
        }
        for tree in trees
    ]
    require(
        signatures[0] == signatures[1] and set(signatures[0]) == names,
        "reuse_logic_changed",
    )
    for name, sha in plan["code_sha256"].items():
        if name == "scripts/e2_evaluation.py" and dense.sha256_file(ROOT / name) != sha:
            from scripts import e2_s500

            original = subprocess.check_output(
                ["git", "-C", str(ROOT), "show", "4bd1d25:" + name], env=env
            ).decode()
            e2_s500.compatible_runner(
                original, (ROOT / name).read_text(encoding="utf-8")
            )
        elif name == "scripts/track_dense.py" and dense.sha256_file(ROOT / name) != sha:
            original = subprocess.check_output(
                ["git", "-C", str(ROOT), "show", "4bd1d25:" + name], env=env
            ).decode()
            compatible_tracking_reader(
                original, (ROOT / name).read_text(encoding="utf-8")
            )
        elif name != "scripts/e2_pilot.py":
            require(
                dense.sha256_file(ROOT / name) == sha,
                "inference_or_evaluator_code_changed:" + name,
            )
    manifest = dense.read_json(roots.artifact / OUTPUT / "manifest.json")
    require(
        manifest["status"] == "completed"
        and manifest["plan_sha256"] == target.digest(plan),
        "pilot_not_terminal",
    )
    records, _ = e2.lineage_records(plan, roots.artifact / OUTPUT, manifest)
    physical = accounting.summarize(records)
    e1_report = dense.read_json(roots.artifact / "results/summary/e1-indexing.json")
    require(
        e1_report["physical_known_tokens"] == 32601955
        and e1_report["budget_charge_upper_bound"] == 32663543
        and not e1_report["cost_complete"],
        "E1_cost_provenance_changed",
    )
    require(
        not physical["journal_corrupt_tail"]
        and all(p["unfinished"] == 0 for p in physical["phases"]),
        "unfinished_usage",
    )
    producers = {}
    p, directory = plan, roots.artifact / OUTPUT
    provenance = []
    while True:
        m = dense.read_json(directory / "manifest.json")
        require(m["plan_sha256"] == target.digest(p), "producer_plan_changed")
        e2.check_parent_pins(p)
        producers[m["run_id"]] = (p, directory)
        provenance.append(
            {
                "run_id": m["run_id"],
                "plan_digest": target.digest(p),
                "manifest": roots.safe(directory / "manifest.json"),
                "manifest_sha256": dense.sha256_file(directory / "manifest.json"),
                "runtime_code_sha256": [
                    {"file": name, "sha256": sha}
                    for name, sha in sorted(p["code_sha256"].items())
                ],
                "runtime_commit": {
                    "84454233-8d21-4731-922a-5a31184610e0": pilot.PILOT_RUNTIME,
                    "fadc0797-34e3-4468-8f0d-bc9ef1289f3a": "3914d70a17554fd6f466026b0aa5f60a02cde715",
                    "20a6360f-24f4-4151-a70c-76632d0a81aa": "4bd1d25fa9e8e545044652171a6047dbe95cb503",
                }[m["run_id"]],
            }
        )
        if not p.get("parent_run"):
            break
        directory = roots.resolve(p["parent_run"]["directory"])
        p = dense.read_json(p["parent_run"]["plan"])
    print("Verified terminal lineage and source pins", flush=True)
    refs = e2.result_references(plan, manifest, roots.artifact / OUTPUT)
    lock_path = ROOT / "data/sources.lock.json"
    source_lock = dense.read_json(lock_path)
    require(
        source_lock["repository"] == "osunlp/HippoRAG_2", "source_repository_changed"
    )
    queries, datasets, full = {}, {}, copy.deepcopy(plan)
    for dataset, data in plan["datasets"].items():
        ids_path = ROOT / f"data/ids/{dataset}_s500.json"
        split_path = ROOT / f"data/ids/{dataset}_comparison_split.json"
        s500, split = dense.read_json(ids_path), dense.read_json(split_path)
        ids = s500["question_ids"]
        require(
            source_lock["revision"] == s500["source_revision"],
            "source_revision_changed",
        )
        check_split(ids, split)
        require(
            split["source_sha256"] == dense.sha256_file(ids_path)
            and dense.sha256_file(split_path) == data["split_sha256"]
            and data["question_ids"] == ids[:200],
            "pinned_split_changed",
        )
        raw = roots.data / f"data/processed/{dataset}"
        corpus = dense.read_json(raw / "corpus.json")
        require(
            dense.sha256_file(raw / "corpus.json") == data["corpus_sha256"],
            "corpus_changed",
        )
        require(
            dense.sha256_file(raw / "labels.json")
            == data["labels_sha256_evaluator_only"],
            "gold_hash_changed",
        )
        selected = e2.select_in_view(
            dense.read_json(raw / "queries.json"), ids, "query"
        )
        require(
            target.digest(selected[:200]) == data["queries_sha256"],
            "pilot_queries_changed",
        )
        queries[dataset] = {q["id"]: q["question"] for q in selected}
        full["datasets"][dataset]["question_ids"] = ids
        datasets[dataset] = {
            "ordered_ids": ids,
            "ordered_ids_sha256": e2.ordered_ids_sha256(ids),
            "s500_file_sha256": dense.sha256_file(ids_path),
            "split_file_sha256": dense.sha256_file(split_path),
            "queries_sha256": target.digest(selected),
            "corpus_sha256": data["corpus_sha256"],
            "labels_sha256_hash_only": data["labels_sha256_evaluator_only"],
            "source_revision": s500["source_revision"],
            "partitions": {
                "pilot": [0, 200],
                "tuning": [0, 300],
                "signal_check": [300, 400],
                "historical_reserve": [400, 500],
            },
        }
        for pin in data["indexes"]:
            path = roots.index / pin["e1_row"]["output"] / "manifest.json"
            require(
                dense.sha256_file(path) == pin["manifest_sha256"],
                "index_manifest_changed",
            )
            im = dense.read_json(path)
            require(
                target.digest(im["artifacts"]) == pin["artifacts_sha256"],
                "index_artifacts_changed",
            )
            indexes.load_ready_e1(source, pin["e1_row"], corpus, roots.index)
            print("Verified index " + dataset + "/" + pin["method"], flush=True)
    bounds = pilot.input_size_bounds(full)
    configurations, counts, identities = [], Counter(), set()
    logical = defaultdict(lambda: defaultdict(usage_row))
    for dataset, data in datasets.items():
        for method in e2.METHODS:
            cases, missing = [], []
            for qid in data["ordered_ids"]:
                key = e2.case_key(dataset, method, qid)
                require(key not in identities, "duplicate_case")
                identities.add(key)
                if key not in refs:
                    counts["missing"] += 1
                    missing.append(qid)
                    continue
                path, sha = refs[key]
                path = roots.resolve(path)
                try:
                    result = dense.read_json(path)
                    require(
                        (result["dataset"], result["method"], result["question_id"])
                        == (dataset, method, qid),
                        "result_identity_changed",
                    )
                    producer, directory = producers[result["run_id"]]
                    status, reason = classify(
                        plan,
                        producer,
                        directory,
                        result,
                        sha,
                        queries[dataset],
                        records,
                    )
                except (OSError, ValueError, KeyError) as exc:
                    status, reason = "incompatible", type(exc).__name__ + ":" + str(exc)
                counts[status] += 1
                case = {
                    "question_id": qid,
                    "status": status,
                    "reason": reason.split(":")[0],
                    "result": roots.safe(path),
                    "result_sha256": sha,
                }
                if status in ("compatible_completed", "terminal_failure"):
                    case.update(
                        run_id=result["run_id"],
                        reader_request_sha256=result["reader_request_sha256"],
                        operations_sha256=target.digest(result["operations"]),
                    )
                    for op in result["operations"]:
                        row = logical[dataset + "/" + method][op["operation"]]
                        observe_usage(row, op)
                cases.append(case)
            pin = next(
                x for x in plan["datasets"][dataset]["indexes"] if x["method"] == method
            )
            print("Verified cases " + dataset + "/" + method, flush=True)
            configurations.append(
                {
                    "dataset": dataset,
                    "method": method,
                    "index": pin,
                    "cases": cases,
                    "missing_ids": missing,
                }
            )
    require(
        len(identities) == 3000
        and len(refs) == sum(counts[k] for k in counts if k != "missing"),
        "case_coverage_changed",
    )
    budget_value = budget(configurations, queries, plan, bounds, logical)
    return {
        "schema_version": 1,
        "kind": "offline_full_S500_freeze",
        "executable": False,
        "http_authorized": False,
        "seed": 42,
        "cases": 3000,
        "counts": dict(counts),
        "contract": contract(plan),
        "data_source": {
            "repository": source_lock["repository"],
            "revision": source_lock["revision"],
            "lock": "repo:data/sources.lock.json",
            "lock_sha256": dense.sha256_file(lock_path),
            "scope": "source metadata pinned; processed corpus/query bytes verified; raw gold never parsed",
        },
        "input_message_bytes_limit": 65536,
        "input_bounds": bounds,
        "datasets": datasets,
        "configurations": configurations,
        "pilot_provenance": provenance,
        "sealed_unknown": [
            {
                ("case_id_sha256" if key == "case_key" else key): value
                for key, value in item.items()
            }
            for item in plan["sealed_unknown"]
        ],
        "logical_reused_usage_by_configuration": dict(logical),
        "pilot_physical": physical,
        "budget_proposal": budget_value,
        "development_physical": plan["pilot_reuse"]["development_physical"],
        "source_reuse_subset_of_development": plan["pilot_reuse"][
            "reused_source_known"
        ],
        "E1_separate": {
            "known_tokens": 32601955,
            "unknown_reserve": 61588,
            "cost_complete": False,
        },
        "accounting_policy": "physical journals once by run/attempt; logical reuse not added; development includes source; E1 separate; sealed reserve22545 is not usage; full project historical cost not reconciled",
        "research_caps": {
            "pilot_original_tokens": 57189854,
            "pilot_original_POST": 2708,
            "pilot_POST_remaining": 0,
            "E1_indexing_original_tokens": 68000000,
            "administrative_90M_ceiling": "removed",
            "new_budget_approval_required": True,
        },
        "interpretation": "S500 descriptive, includes development; pilot200 subset of tuning300; signal21 formula/direction/threshold tuning only before signal-check gold/metrics; precomputed answers grant no selection permission; reserve includes disclosed exposure; absence of history is not evidence of untouched data",
        "errors": "known reader length/empty/parser failure=case failure,no retry; budget/pin/transport/unknown/infra/filter malformed=fatal; empty valid Hippo filter=DPR; sealed failure carried as infrastructure pipeline zero, not reader answer; no automatic rerun",
        "models": {
            "reader_revision_quantization": "unreported endpoint alias",
            "embedding_revision": plan["embedding_digest"],
            "RAPTOR_provenance": "summary-node source coverage, not passage recall@5",
            "Hippo_extractor": "mixed E1 provenance retained; disclosed extraction errors and semantic_verified=false",
            "mixed_extractor_policy": source["mixed_extractor"],
            "indexing_parameters": source["parameters"],
            "indexing_model_revision_quantization": source[
                "deployed_revision_and_quantization"
            ],
        },
        "verification": {
            "base_commit": "e67b92f50d567d4b17ede29fffebe9b1e537d6f2",
            "history_audit_sha256": dense.sha256_file(
                ROOT / "results/summary/question-usage-audit.json"
            ),
            "E1_accounting_report_sha256": dense.sha256_file(
                roots.artifact / "results/summary/e1-indexing.json"
            ),
            "reader_evaluator_code": "matches last execution pins; reuse functions AST matches4bd1d25; reporting-only changes allowed",
            "network": "blocked",
            "gold": "file hash only; never parsed",
            "issue21_signal": "not selected",
        },
    }


def dataset_worklist(source, dataset):
    """Stage a verified dataset freeze; never authorize or execute requests."""
    require(dataset in ("musique", "hotpotqa"), "S500_dataset_forbidden")
    data = source["datasets"][dataset]
    ids = data["ordered_ids"]
    require(len(ids) == len(set(ids)) == 500, dataset + "_expected_500_unique_ids")
    require(
        e2.ordered_ids_sha256(ids) == data["ordered_ids_sha256"],
        dataset + "_ID_pin_changed",
    )
    configs = [c for c in source["configurations"] if c["dataset"] == dataset]
    require(
        len(configs) == 3 and {c["method"] for c in configs} == set(e2.METHODS),
        dataset + "_three_methods_required",
    )
    all_cases, inherited, missing, methods = set(), 0, 0, []
    for method in e2.METHODS:
        config = next(c for c in configs if c["method"] == method)
        reuse = config["cases"]
        new_ids = config["missing_ids"]
        require(
            all(
                c["status"] == "compatible_completed"
                or (
                    dataset == "hotpotqa"
                    and c["status"] == "terminal_failure"
                    and c.get("reason") == "sealed_unknown_no_retry"
                    and any(
                        u["case_id_sha256"]
                        == e2.case_key(dataset, method, c["question_id"])
                        and u["run_id"] == c["run_id"]
                        for u in source["sealed_unknown"]
                    )
                )
                for c in reuse
            ),
            dataset + "_source_case_not_completed",
        )
        require(
            [c["question_id"] for c in reuse] + new_ids == ids,
            dataset + "_case_partition_changed",
        )
        keys = [e2.case_key(dataset, method, qid) for qid in ids]
        require(not all_cases.intersection(keys), dataset + "_duplicate_case")
        all_cases.update(keys)
        inherited += len(reuse)
        missing += len(new_ids)
        methods.append(
            {
                "method": method,
                "index": config["index"],
                "inherited_results": reuse,
                "new_question_ids": new_ids,
            }
        )
    require(len(all_cases) == 1500, dataset + "_case_count_changed")
    parent_budget = source["budget_proposal"]["operational_budget_proposal"]
    allocations = [a for a in parent_budget["allocations"] if a["dataset"] == dataset]
    require(
        len(allocations) == 7
        and all(a["allocation_tokens"] is not None for a in allocations),
        dataset + "_budget_observations_missing",
    )
    empirical = sum(a["allocation_tokens"] for a in allocations)
    headroom = parent_budget["admission_headroom_tokens"]
    value = {
        "schema_version": 1,
        "kind": dataset + "_S500_worklist",
        "status": "prepared_pending_issue15_and_execution_plan",
        "executable": False,
        "http_authorized": False,
        "execution_complete": False,
        "source": {
            "path": "repo:results/summary/full-experiment.json",
            "canonical_json_sha256": target.digest(source),
            "dependency": "PR37 / issue15; budget not approved",
        },
        "dataset": dataset,
        "question_ids": ids,
        "ordered_ids_sha256": data["ordered_ids_sha256"],
        "corpus_sha256": data["corpus_sha256"],
        "queries_sha256": data["queries_sha256"],
        "contract": source["contract"],
        "methods": methods,
        "counts": {
            "expected_cases": 1500,
            "inherited_completed": inherited,
            "not_attempted": missing,
            "terminal_failures": 0,
        },
        "budget_proposal": {
            "authorized": False,
            "new_posts_upper": {
                "reader": missing,
                "filter": len(
                    next(c for c in configs if c["method"] == "hipporag2")[
                        "missing_ids"
                    ]
                ),
                "query_embedding": missing,
            },
            "new_posts_total_upper": sum(a["new_calls_upper"] for a in allocations),
            "pilot_maximum_allocation_tokens": empirical,
            "admission_headroom_tokens": headroom,
            "proposed_new_token_cap": empirical + headroom,
            "completion_guaranteed": False,
            "allocations": allocations,
            "required_preflight": parent_budget["required_preflight"],
        },
        "historical_accounting": {
            "source": "parent freeze; never charge logical reuse twice",
            "out_of_scope_sealed_unknown": source["sealed_unknown"],
            "cost_complete": False,
        },
        "preparation_model_calls": 0,
        "remaining_work": [
            "issue15 budget approval",
            "approved MuSiQue execution-plan and guarded runner integration with offline tests",
            "execute only missing cases",
            "strict terminal audit and common evaluator; retain all errors",
            "per-case metrics and safe summary for downstream tasks12/14",
        ],
    }

    if dataset == "hotpotqa":
        failed = [
            c
            for m in methods
            for c in m["inherited_results"]
            if c["status"] == "terminal_failure"
        ]
        require(
            inherited == 600 and missing == 900 and len(failed) == 1,
            "hotpotqa_expected_599_answers_one_failure_900_missing",
        )
        require(
            empirical == 4913100 and empirical + headroom == 4982220,
            "hotpotqa_budget_basis_changed",
        )
        value["counts"].update(inherited_completed=599, terminal_failures=1)
        value["status"] = "prepared_pending_execution_plan_and_scientific_approval"
        value["source"]["dependency"] = (
            "issue15 completed; approved Hot budget is a separate ADR0028 decision, not HTTP authorization"
        )
        value["historical_accounting"] = {
            "source": "parent freeze; no double accounting",
            "sealed_unknown": source["sealed_unknown"],
            "cost_complete": False,
        }
        value["remaining_work"] = [
            "scientific approval for issue17",
            "verified Hot execution-plan/transport tests",
            "explicit execution authorization",
            "missing-only execution and terminal audit",
        ]
    return value


def musique_worklist(source):
    return dataset_worklist(source, "musique")


def hotpotqa_worklist(source):
    return dataset_worklist(source, "hotpotqa")


def compatible_tracking_reader(original, current):
    """Only local observation pagination may evolve; inference/export AST stays fixed."""

    def normalize(source):
        tree = ast.parse(source)
        for node in tree.body:
            if (
                isinstance(node, ast.FunctionDef)
                and node.name == "get_all_langfuse_observations"
            ):
                node.body = [ast.Pass()]
        return ast.dump(tree, include_attributes=False)

    require(
        normalize(original) == normalize(current),
        "tracking_change_outside_observation_reader",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "prepare",
            "verify",
            "prepare-hotpotqa",
            "verify-hotpotqa",
            "prepare-musique",
            "verify-musique",
            "prepare-musique-execution",
            "prepare-musique-unattempted",
            "verify-musique-execution",
            "prepare-hotpotqa-execution",
            "verify-hotpotqa-execution",
        ),
    )
    for root in ("artifact", "data", "index"):
        parser.add_argument("--" + root + "-root", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / PUBLIC)
    parser.add_argument(
        "--dataset-plan",
        type=Path,
        default=ROOT / "results/summary/e2-musique-s500-plan.json",
    )
    parser.add_argument(
        "--execution-plan",
        type=Path,
        default=ROOT / ".cache/e2-musique-s500-execution-plan.json",
    )
    parser.add_argument(
        "--parent-plan",
        type=Path,
        default=ROOT / ".cache/e2-musique-s500-execution-plan.json",
    )
    parser.add_argument(
        "--parent-output", type=Path, default=ROOT / "results/raw/e2-musique-s500-v1"
    )
    parser.add_argument(
        "--continuation-authorization",
        type=Path,
        default=ROOT / "results/summary/e2-musique-s500-unattempted-authorization.json",
    )
    args = parser.parse_args(argv)
    if args.action in ("prepare-hotpotqa-execution", "verify-hotpotqa-execution"):
        from scripts import e2_hotpot

        original = dense.read_json(ROOT / PLAN)
        e1 = dense.read_json(Path(original["e1_plan"]))
        require(
            args.artifact_root.resolve() == ROOT
            and args.data_root.resolve() == Path(e1["data_root"]).resolve()
            and args.index_root.resolve() == Path(original["e1_workspace"]).resolve(),
            "Hot_execution_roots_changed",
        )
        if args.action == "prepare-hotpotqa-execution":
            plan = e2_hotpot.prepare(args.dataset_plan)
            require(
                not args.execution_plan.exists()
                or dense.read_json(args.execution_plan) == plan,
                "Hot_frozen_execution_plan_cannot_be_overwritten",
            )
            dense.write_json_atomic(args.execution_plan, plan)
        else:
            plan = dense.read_json(args.execution_plan)
            e2_hotpot.verify(plan)
        print(
            json.dumps(
                {
                    "version": plan["version"],
                    "plan_file_sha256": dense.sha256_file(args.execution_plan),
                    "new_POST_cap": plan["max_posts"],
                    "new_token_cap": plan["max_combined_tokens"],
                    "inherited": len(plan["parent_run"]["cases"]),
                    "HTTP": 0,
                }
            )
        )
        return
    if args.action in (
        "prepare-musique-execution",
        "verify-musique-execution",
        "prepare-musique-unattempted",
    ):
        from scripts import e2_s500

        original = dense.read_json(ROOT / PLAN)
        e1 = dense.read_json(Path(original["e1_plan"]))
        require(
            args.artifact_root.resolve() == ROOT
            and args.data_root.resolve() == Path(e1["data_root"]).resolve()
            and args.index_root.resolve() == Path(original["e1_workspace"]).resolve(),
            "S500_execution_roots_changed",
        )
        if args.action in ("prepare-musique-execution", "prepare-musique-unattempted"):
            plan = (
                e2_s500.prepare_unattempted(
                    args.parent_plan,
                    args.parent_output,
                    args.continuation_authorization,
                )
                if args.action == "prepare-musique-unattempted"
                else e2_s500.prepare(args.dataset_plan)
            )
            require(
                not args.execution_plan.exists()
                or dense.read_json(args.execution_plan) == plan,
                "S500_frozen_execution_plan_cannot_be_overwritten",
            )
            dense.write_json_atomic(args.execution_plan, plan)
        else:
            plan = dense.read_json(args.execution_plan)
            e2_s500.verify(plan)
        print(
            json.dumps(
                {
                    "version": plan["version"],
                    "plan_file_sha256": dense.sha256_file(args.execution_plan),
                    "new_POST_cap": plan["max_posts"],
                    "new_token_cap": plan["max_combined_tokens"],
                    "inherited": len(plan["parent_run"]["cases"]),
                    "HTTP": 0,
                }
            )
        )
        return
    value = freeze(args.artifact_root, args.data_root, args.index_root)
    if args.action in ("prepare-hotpotqa", "verify-hotpotqa"):
        require(value == dense.read_json(args.manifest), "full_manifest_changed")
        worklist = hotpotqa_worklist(value)
        path = args.artifact_root / "results/summary/e2-hotpotqa-s500-plan.json"
        if args.action == "prepare-hotpotqa":
            require(
                not path.exists() or dense.read_json(path) == worklist,
                "hotpotqa_worklist_cannot_be_overwritten",
            )
            dense.write_json_atomic(path, worklist)
        else:
            require(dense.read_json(path) == worklist, "hotpotqa_worklist_changed")
        print(json.dumps({"counts": worklist["counts"], "HTTP": 0}))
        return
    if args.action in ("prepare-musique", "verify-musique"):
        require(value == dense.read_json(args.manifest), "full_manifest_changed")
        require(
            value["counts"].get("incompatible", 0) == 0,
            "incompatible_artifacts_no_execution",
        )
        worklist = musique_worklist(value)
        if args.action == "prepare-musique":
            args.dataset_plan.write_text(
                json.dumps(
                    worklist, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            require(
                worklist == dense.read_json(args.dataset_plan),
                "musique_worklist_changed",
            )
        print(
            json.dumps(
                {
                    "counts": worklist["counts"],
                    "budget": worklist["budget_proposal"],
                    "HTTP": 0,
                },
                ensure_ascii=False,
            )
        )
        return
    if args.action == "prepare":
        args.manifest.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
    else:
        require(value == dense.read_json(args.manifest), "full_manifest_changed")
    print(
        json.dumps(
            {"counts": value["counts"], "budget": value["budget_proposal"], "HTTP": 0},
            ensure_ascii=False,
        )
    )
    require(
        value["counts"].get("incompatible", 0) == 0,
        "incompatible_artifacts_no_execution",
    )


if __name__ == "__main__":
    main()
