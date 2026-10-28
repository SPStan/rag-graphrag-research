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


def usage_complete(operation):
    relevant = (
        ("embedding_input_tokens",)
        if operation["operation"] == "query_embedding"
        else ("llm_input_tokens", "llm_output_tokens")
    )
    return all(operation["logical_usage"].get(key) is not None for key in relevant)


def usage_add(totals, operation):
    values = operation["logical_usage"]
    for key in FIELDS:
        if values.get(key) is not None:
            totals[key] += values[key]


def budget(configurations, queries, plan, bounds, logical):
    posts = Counter()
    reserve = Counter()
    forecast = Counter()
    for config in configurations:
        d, m = config["dataset"], config["method"]
        n = len(config["missing_ids"])
        posts["reader"] += n
        posts["filter"] += n if m == "hipporag2" else 0
        posts["query_embedding"] += n
        bound = bounds[f"{d}/{'raptor' if m == 'raptor' else 'dense_or_hippo'}"][
            "synthetic_top5_message_bytes"
        ]
        require(bound <= plan["message_utf8_bytes_limit"], "full500_input_overflow")
        reserve["reader"] += n * (bound + 1024 + 2048 + 512)
        reserve["filter"] += n * (65536 + 1024 + 2048 + 512) if m == "hipporag2" else 0
        for q in config["missing_ids"]:
            payload = e2.embedding_payload(plan, queries[d][q])
            require(
                len(queries[d][q].encode()) <= plan["query_utf8_bytes_limit"],
                "query_overflow",
            )
            reserve["query_embedding"] += (
                len(json.dumps(payload, ensure_ascii=False).encode()) + 2048
            )
        for operation, row in logical[d + "/" + m].items():
            # Denominator includes only known operations, not a fabricated unknown zero.
            require(row["known_operations"] > 0, "forecast_no_known_operations")
            for key in FIELDS:
                forecast[operation + "/" + key] += (
                    n * row["known_subtotal"][key] / row["known_operations"]
                )
    return {
        "new_posts_upper": dict(posts),
        "new_posts_total_upper": sum(posts.values()),
        "forecast_tokens_by_operation": {
            k: round(v, 3) for k, v in sorted(forecast.items())
        },
        "forecast_known_combined_tokens": round(sum(forecast.values()), 3),
        "conservative_reservations_by_operation": dict(reserve),
        "conservative_combined_tokens": sum(reserve.values()),
        "reserve_is_measured_usage": False,
        "authorized": False,
        "forecast_policy": "per-configuration pilot logical known-operation means; filter upper one/case; no cross-method BGE dedup; unknown excluded from means",
        "scope": "proposal for missing cases only; old pilot POST allowance exhausted; no administrative90M ceiling does not grant research budget",
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
        if name != "scripts/e2_pilot.py":
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
    logical = defaultdict(
        lambda: defaultdict(
            lambda: {
                "known_operations": 0,
                "unknown_operations": 0,
                "known_subtotal": dict.fromkeys(FIELDS, 0),
            }
        )
    )
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
                        unknown = not usage_complete(op)
                        row[
                            "unknown_operations" if unknown else "known_operations"
                        ] += 1
                        usage_add(row["known_subtotal"], op)
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    for root in ("artifact", "data", "index"):
        parser.add_argument("--" + root + "-root", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=ROOT / PUBLIC)
    args = parser.parse_args(argv)
    value = freeze(args.artifact_root, args.data_root, args.index_root)
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
