"""Approved MuSiQue S500 extension of the existing shared E2 runner."""

import ast
import copy
import json
import hashlib
import subprocess
from pathlib import Path

from scripts import e2_evaluation as e2, run_dense as dense, run_dense_target as target
from scripts import token_accounting as accounting

VERSION = "e2-musique-s500-v1"
EXPECTED_IDS = 500
EXPECTED_MISSING = 199
PARENT_RUNTIME = "e144ad93cbd07f051090673f9baf8e158ceca126"
PARENT_PLAN_SHA = "99d5e84615cc09259f2ea39726e035243d40e62005261f0acee33ccc9bb7401e"
TOKEN_CAP = 5990220
POST_CAPS = {"reader": 900, "filter": 300, "query_embedding": 900}
ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "results/summary/e2-musique-s500-authorization.json"
CODE_FILES = (*e2.CODE_FILES, "scripts/full_experiment.py", "scripts/e2_s500.py")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compatible_runner(original, current):
    """Every legacy AST node must match after removing only new-version guards."""

    class Legacy(ast.NodeTransformer):
        def visit_If(self, node):
            node = self.generic_visit(node)
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value in (VERSION, "e2-hotpotqa-s500-v1")
            ):
                require(not node.orelse, "S500_extension_modified_legacy_else")
                return None
            return node

    old, new = ast.parse(original), ast.parse(current)
    require(
        ast.dump(old, include_attributes=False)
        == ast.dump(Legacy().visit(new), include_attributes=False),
        "S500_legacy_runner_semantics_changed",
    )


def validate_authorization(value):
    require(
        value.get("kind") == "musique_budget_authorization"
        and value.get("approved") is True
        and value.get("dataset") == "musique"
        and value.get("new_token_cap") == TOKEN_CAP
        and value.get("new_POST_caps") == POST_CAPS
        and value.get("authorization_source")
        == "direct user message in this task, 2026-10-29"
        and value.get("retry") == 0,
        "S500_budget_authorization_changed",
    )


def prepare(worklist_path, authorization_path=AUTHORIZATION):
    return prepare_dataset(
        worklist_path,
        authorization_path,
        dataset="musique",
        version=VERSION,
        token_cap=TOKEN_CAP,
        validator=validate_authorization,
    )


def prepare_dataset(
    worklist_path, authorization_path, *, dataset, version, token_cap, validator
):
    """Rebuild private execution metadata offline; never modifies old sources."""
    from scripts import full_experiment as full

    worklist_path, authorization_path = (
        Path(worklist_path).resolve(),
        Path(authorization_path).resolve(),
    )
    worklist, auth = dense.read_json(worklist_path), dense.read_json(authorization_path)
    validator(auth)
    source_path = ROOT / full.PUBLIC
    frozen = dense.read_json(source_path)
    original_path, original_dir = ROOT / full.PLAN, ROOT / full.OUTPUT
    parent = dense.read_json(original_path)
    e1 = dense.read_json(Path(parent["e1_plan"]))
    actual = full.freeze(ROOT, e1["data_root"], parent["e1_workspace"])
    require(
        actual == frozen and full.dataset_worklist(frozen, dataset) == worklist,
        "S500_source_or_worklist_changed",
    )
    require(
        worklist["budget_proposal"]["proposed_new_token_cap"] == token_cap,
        "S500_budget_basis_changed",
    )
    manifest_path = original_dir / "manifest.json"
    manifest = dense.read_json(manifest_path)
    refs = e2.result_references(parent, manifest, original_dir)
    files = {
        str(p): dense.sha256_file(p)
        for p in (
            original_path,
            manifest_path,
            original_dir / "usage.jsonl",
            source_path,
            worklist_path,
            authorization_path,
        )
    }
    files.update(parent.get("parent_run", {}).get("files", {}))
    files.update(parent.get("pilot_reuse", {}).get("files", {}))
    cases = {}
    for method in worklist["methods"]:
        for result in method["inherited_results"]:
            key = e2.case_key(dataset, method["method"], result["question_id"])
            path, sha = refs[key]
            require(
                sha == result["result_sha256"] and dense.sha256_file(path) == sha,
                "S500_inherited_result_changed",
            )
            cases[key] = {
                "path": str(path),
                "sha256": sha,
                "status": "completed"
                if result["status"] == "compatible_completed"
                else "failed",
            }
            files[str(path)] = sha
    require(len(cases) == 600, "S500_expected_600_inherited_cases")
    value = {
        k: copy.deepcopy(v)
        for k, v in parent.items()
        if k
        not in (
            "parent_run",
            "physical_parents",
            "pilot_continuation",
            "sealed_unknown",
            "remaining_cases",
            "original_remaining_tokens",
            "original_remaining_posts",
            "pilot_protocol",
        )
    }
    data = copy.deepcopy(parent["datasets"][dataset])
    data["question_ids"] = worklist["question_ids"]
    raw = Path(e1["data_root"]) / f"data/processed/{dataset}"
    data["queries_sha256"] = target.digest(
        e2.select_in_view(
            dense.read_json(raw / "queries.json"), data["question_ids"], "query"
        )
    )
    data["ordered_ids_sha256"] = worklist["ordered_ids_sha256"]
    value.update(
        version=version,
        mode="approved_" + dataset + "_S500_missing_only",
        datasets={dataset: data},
        http_authorized=True,
        max_posts=2100,
        max_llm_posts=1200,
        max_embedding_posts=900,
        reader_calls=900,
        filter_calls=300,
        max_combined_tokens=token_cap,
        pilot_reuse={"contexts": {}, "readers": {}, "files": {}},
        code_sha256={name: dense.sha256_file(ROOT / name) for name in CODE_FILES},
        parent_run={
            "plan": str(original_path),
            "directory": str(original_dir),
            "run_id": manifest["run_id"],
            "files": files,
            "cases": cases,
        },
        s500={
            "worklist": str(worklist_path),
            "authorization": str(authorization_path),
            "source": str(source_path),
            "source_digest": target.digest(frozen),
            "source_global_cost": {
                k: frozen[k]
                for k in (
                    "pilot_physical",
                    "development_physical",
                    "E1_separate",
                    "sealed_unknown",
                )
            },
            "scope": "new physical expense only; source global cost separate; no automatic recovery",
        },
    )
    if dataset == "hotpotqa":
        value["sealed_unknown"] = copy.deepcopy(parent["sealed_unknown"])
    return value


def verify(plan):
    require(
        plan.get("version") == VERSION
        and set(plan["datasets"]) == {"musique"}
        and len(plan["datasets"]["musique"]["question_ids"]) == EXPECTED_IDS,
        "S500_only_frozen_MuSiQue500",
    )
    spec = plan["s500"].get("continuation")
    candidate = (
        prepare_unattempted(
            spec["parent_plan"], spec["parent_directory"], spec["authorization"]
        )
        if spec
        else prepare(plan["s500"]["worklist"], plan["s500"]["authorization"])
    )
    require(candidate == plan, "S500_execution_plan_changed")
    return True


def guard(calls, payload, method, dataset, qid, operation):
    return guard_dataset(
        calls,
        payload,
        method,
        dataset,
        qid,
        operation,
        expected_dataset="musique",
        token_cap=TOKEN_CAP,
    )


def guard_dataset(
    calls, payload, method, dataset, qid, operation, *, expected_dataset, token_cap
):
    plan = calls.plan
    spec = plan["s500"].get("continuation")
    if spec:
        if expected_dataset == "musique":
            require(
                method == "raptor" and operation in ("reader", "query_embedding"),
                "S500_unattempted_RAPTOR_only",
            )
        require(
            dense.sha256_file(Path(spec["authorization"]))
            == spec["authorization_sha256"],
            "S500_continuation_authorization_changed",
        )
    require(
        plan.get("http_authorized") is True
        and set(plan["datasets"]) == {expected_dataset}
        and dataset == expected_dataset
        and method in e2.METHODS
        and qid in plan["datasets"][expected_dataset]["question_ids"],
        "S500_case_outside_approved_scope",
    )
    require(
        plan["max_combined_tokens"] <= token_cap
        and plan["max_posts"] <= 2100
        and plan["reader_calls"] <= 900
        and plan["filter_calls"] <= 300
        and plan["max_embedding_posts"] <= 900,
        "S500_budget_expansion_forbidden",
    )
    require(
        e2.case_key(dataset, method, qid) not in plan["parent_run"]["cases"],
        "S500_inherited_case_must_not_POST",
    )
    require(
        operation in ("reader", "query_embedding", "filter")
        and (operation != "filter" or method == "hipporag2"),
        "S500_operation_forbidden",
    )
    if operation == "reader":
        require(
            payload.get("messages", [])[:3]
            == e2.answer_only_payload("", {"passages": []})["messages"][:3]
            and len(payload.get("messages", [])) == 4,
            "S500_reader_template_changed",
        )
    key = target.digest(
        {
            "plan": calls.plan_sha,
            "method": method,
            "dataset": dataset,
            "qid": qid,
            "operation": operation,
            "payload": payload,
        }
    )
    if (calls.directory / (key + ".json")).exists():
        return  # Core verifies exact terminal checkpoint, never retries unknown.
    summary = calls.journal.summary()
    require(summary["complete"], "S500_unknown_or_unfinished_no_next_POST")
    reserve = len(json.dumps(payload, ensure_ascii=False).encode()) + 2048
    if operation != "query_embedding":
        reserve += payload.get("max_tokens", target.OPTIONS["max_tokens"])
    require(
        sum(summary["known_subtotal"].values()) + reserve
        <= plan["max_combined_tokens"],
        "S500_pre_POST_budget_reservation_exceeded",
    )


def current_records(plan, directory, manifest):
    e2.check_parent_pins(plan)
    path = Path(directory) / "manifest.json"
    reference = accounting.verified_reference(manifest, path)
    require(reference["status"] == "verified", "S500_current_journal_changed")
    records = accounting.read_records(path.parent / "usage.jsonl")
    require(not records.corrupt_tail, "S500_corrupt_journal")
    return records, [{**reference, "path": str(reference["path"])}]


def enrich_report(plan, report):
    from scripts import full_experiment as full

    inherited = plan["parent_run"]["cases"]
    for row in report["rows"]:
        cases = [c for c in report["question_results"] if c["method"] == row["method"]]
        fresh = [
            c
            for c in cases
            if e2.case_key(c["dataset"], c["method"], c["question_id"]) not in inherited
            and c["status"] != "not_attempted"
        ]
        row["fresh_e2e_cases"] = len(fresh)
        row["mean_fresh_e2e_seconds"] = (
            sum(c["wall_seconds"] for c in fresh) / len(fresh) if fresh else None
        )
        row["mean_attempted_seconds"] = row["mean_completed_seconds"] = None
        for label, selected in (
            ("new_physical_usage", fresh),
            (
                "inherited_logical_usage",
                [c for c in cases if c not in fresh and c["status"] != "not_attempted"],
            ),
        ):
            buckets = {
                op: full.usage_row() for op in ("reader", "filter", "query_embedding")
            }
            for case in selected:
                for op in case["operations"]:
                    full.observe_usage(buckets[op["operation"]], op)
            row[label] = buckets
        row["limitations"] = (
            "S500 descriptive, includes tuning/pilot; inherited latency is not fresh E2E; mixed Hippo errors retained"
        )
    spec = plan["s500"].get("continuation")
    if spec:
        for row in report["rows"]:
            fresh = [
                c
                for c in report["question_results"]
                if c["method"] == row["method"]
                and e2.case_key(c["dataset"], c["method"], c["question_id"])
                not in spec["initial_reuse_cases"]
                and c["status"] != "not_attempted"
            ]
            row["S500_fresh_e2e_cases"] = len(fresh)
            row["S500_mean_fresh_e2e_seconds"] = (
                sum(c["wall_seconds"] for c in fresh) / len(fresh) if fresh else None
            )
            buckets = {
                op: full.usage_row() for op in ("reader", "filter", "query_embedding")
            }
            for case in fresh:
                for op in case["operations"]:
                    full.observe_usage(buckets[op["operation"]], op)
            row["S500_physical_usage"] = buckets
    report["historical_source_accounting"] = plan["s500"]["source_global_cost"]


def apply_report_evidence(safe, directory, evidence_path):
    """Attach a reviewed, hash-bound appendix; never import a previous output."""
    evidence = dense.read_json(evidence_path)
    require(
        evidence["run_id"] == safe["run_id"]
        and evidence["plan_sha256"] == safe["plan_sha256"]
        and evidence["manifest_sha256"] == safe["manifest_sha256"],
        "S500_evidence_run_binding_changed",
    )
    sections = evidence["sections"]
    require(
        target.digest(sections) == evidence["sections_sha256"],
        "S500_evidence_sections_changed",
    )
    require(not (set(sections) & set(safe)), "S500_evidence_cannot_override_core")
    for relative, sha in evidence["artifact_sha256"].items():
        path = (ROOT / relative).resolve()
        require(path.is_relative_to(ROOT.resolve()), "S500_evidence_path_escape")
        require(
            path.is_file() and dense.sha256_file(path) == sha,
            "S500_evidence_artifact_changed",
        )
    audit = sections["terminal_audit"]
    require(
        audit["run_id"] == safe["run_id"]
        and audit["manifest_sha256"] == safe["manifest_sha256"]
        and audit["plan_sha256"] == safe["plan_sha256"]
        and audit["journal_sha256"] == dense.sha256_file(directory / "usage.jsonl")
        and audit["private_evaluation_sha256"]
        == dense.sha256_file(directory / "evaluation.json"),
        "S500_evidence_audit_binding_changed",
    )
    audit_path = evidence["terminal_audit_relative_path"]
    require(audit_path in evidence["artifact_sha256"], "S500_evidence_audit_unpinned")
    saved_audit = dense.read_json(ROOT / audit_path)
    sealed = saved_audit.get("sealed_unknown", {})
    if "case_key" in sealed:
        sealed["case_id_sha256"] = sealed.pop("case_key")
    require(saved_audit == audit, "S500_evidence_audit_changed")
    tracking = sections["tracking"]
    require(
        evidence["artifact_sha256"].get(tracking["receipt_relative_path"])
        == tracking["receipt_sha256"],
        "S500_evidence_receipt_binding_changed",
    )
    receipt = dense.read_json(ROOT / tracking["receipt_relative_path"])
    require(
        set(receipt["views"]) == set(tracking["views"]), "S500_evidence_views_changed"
    )
    for key, view in tracking["views"].items():
        saved = receipt["views"][key]
        require(
            saved["status"] == "verified"
            and all(
                view[k] == saved[k]
                for k in ("cases", "completed", "failed", "fulltext_roundtrip")
            )
            and view["mlflow_run_id"] == saved["mlflow"]["mlflow_run_id"]
            and view["langfuse_trace_id"] == saved["langfuse"]["trace_id"]
            and view["linked_JSONL_sha256"] == saved["linked_JSONL"]["sha256"],
            "S500_evidence_tracking_changed",
        )
    source = safe["historical_source_accounting"]
    if "pilot_physical" in source:
        historic = [source["pilot_physical"], source["development_physical"]]
        physical = safe["S500_physical_accounting"]
        cumulative = sections["cumulative_E2_accounting"]
        sealed = safe.get("sealed_historical_unknown", []) + source["sealed_unknown"]
        require(
            cumulative["unknown_operations"] == len(sealed)
            and cumulative["unknown_reservations_not_actual"]
            == sum(x["reservation_tokens"] for x in sealed),
            "S500_evidence_unknown_accounting_changed",
        )
        require(
            cumulative["known_tokens"]
            == sum(physical["known_subtotal"].values())
            + sum(sum(x["known_subtotal"].values()) for x in historic)
            and cumulative["physical_POST"]
            == physical["POST"] + sum(x["attempts"] for x in historic)
            and cumulative["cost_complete"] is False,
            "S500_evidence_cumulative_accounting_changed",
        )
    for sealed in safe.get("sealed_historical_unknown", []):
        if "case_key" in sealed:
            sealed["case_id_sha256"] = sealed.pop("case_key")
    safe.update(copy.deepcopy(sections))


def write_report(plan_path, directory, public_prefix, *, evidence_path=None):
    return write_dataset_report(
        plan_path,
        directory,
        public_prefix,
        dataset="musique",
        evidence_path=evidence_path,
    )


def write_dataset_report(
    plan_path, directory, public_prefix, *, dataset, evidence_path=None
):
    plan, directory, prefix = (
        dense.read_json(Path(plan_path)),
        Path(directory),
        Path(public_prefix),
    )
    manifest_path = directory / "manifest.json"
    require(
        not (directory / "running.lock").exists(), "S500_report_requires_stopped_worker"
    )
    manifest_sha = dense.sha256_file(manifest_path)
    manifest = dense.read_json(manifest_path)
    require(
        manifest["status"] in ("completed", "failed", "partial_completed_methods"),
        "S500_report_requires_terminal_or_paused_run",
    )
    require(
        set(plan["datasets"]) == {dataset}
        and len(plan["datasets"][dataset]["question_ids"]) == EXPECTED_IDS,
        "S500_report_scope_changed",
    )
    prefix.parent.mkdir(parents=True, exist_ok=True)
    refs = e2.result_references(plan, manifest, directory)
    records, _ = current_records(plan, directory, manifest)
    unverified_fatal_cases = []
    for key in manifest["results"]:
        path, sha = refs[key]
        require(dense.sha256_file(path) == sha, "S500_new_result_changed")
        result = dense.read_json(path)
        if result.get("fatal") and result["status"] != "completed":
            # Preserve uncertain artifacts; a started checkpoint is never success.
            # Strict successful-case audit cannot verify an absent HTTP response.
            require(
                manifest["status"] == "failed",
                "S500_fatal_case_requires_failed_manifest",
            )
            require(
                result["config_sha256"] == target.digest(plan),
                "S500_failed_config_changed",
            )
            for op in result["operations"]:
                terminal = [
                    r
                    for r in records
                    if r["event"] == "finished"
                    and r.get("object_id") == op["journal_object_id"]
                ]
                if not op.get("physical_attempted"):
                    require(not terminal, "S500_unattempted_operation_has_usage")
                    continue
                require(
                    len(terminal) == 1
                    and op.get("logical_usage")
                    == {k: terminal[0][k] for k in accounting.TOKEN_FIELDS},
                    "S500_failed_usage_changed",
                )
            unverified_fatal_cases.append(key)
        else:
            e2.verify_saved_case(plan, directory, result, records)
    starts = [r for r in records if r["event"] == "started"]
    expected_objects = {
        op["journal_object_id"]
        for key in manifest["results"]
        for op in dense.read_json(refs[key][0])["operations"]
        if op.get("physical_attempted")
    }
    require(
        {r["object_id"] for r in starts} == expected_objects
        and len(starts) == len(expected_objects),
        "S500_unbound_or_duplicate_physical_attempt",
    )
    if manifest["status"] == "completed":
        require(
            len(refs) == EXPECTED_IDS * len(e2.METHODS)
            and accounting.summarize(records)["complete"]
            and not unverified_fatal_cases,
            "S500_incomplete_terminal_audit",
        )
    report = e2.summary(plan, directory)
    evaluation = directory / "evaluation.json"
    if evaluation.exists():
        require(
            dense.read_json(evaluation) == report, "S500_existing_evaluation_changed"
        )
    else:
        dense.write_json_atomic(evaluation, report)
    starts = [r for r in records if r["event"] == "started"]
    known = accounting.summarize(records)
    safe = {
        "kind": "e2_" + dataset + "_S500",
        "run_id": manifest["run_id"],
        "status": manifest["status"],
        "plan_sha256": dense.sha256_file(plan_path),
        "manifest_sha256": manifest_sha,
        "comparison_complete": report["comparison_complete"],
        "rows": report["rows"],
        "new_physical_accounting": known,
        "new_POST": len(starts),
        "model_posts": len(starts),
        "strict_success_audit_complete": not unverified_fatal_cases,
        "unverified_fatal_case_ids": unverified_fatal_cases,
        "terminal_artifact_sha256": {
            p.name: dense.sha256_file(p)
            for p in directory.glob("*.json")
            if p.name != "evaluation.json"
        },
        "historical_source_accounting": plan["s500"]["source_global_cost"],
        "inherited_cases": len(plan["parent_run"]["cases"]),
        "new_terminal_cases": len(manifest["results"]),
        "raw_directory": "results/raw/" + directory.name,
        "further_experiments_authorized": False,
    }
    spec = plan["s500"].get("continuation")
    safe["cost_complete"] = (
        known["complete"] and not spec and not plan.get("sealed_unknown")
    )
    if spec:
        previous = spec["parent_physical"]
        combined = {
            k: known["known_subtotal"][k] + previous["known_subtotal"][k]
            for k in accounting.TOKEN_FIELDS
        }
        safe.update(
            sealed_historical_unknown=plan["sealed_unknown"],
            S500_physical_accounting={
                "known_subtotal": combined,
                "POST": len(starts) + previous["POST"],
                "unknown_reservation_not_actual": previous[
                    "unknown_reservation_not_actual"
                ],
                "cost_complete": False,
            },
            total_coverage={
                "expected": EXPECTED_IDS * len(e2.METHODS),
                "completed": sum(r["completed"] for r in report["rows"]),
                "attempted_failed": sum(r["attempted_failed"] for r in report["rows"]),
                "not_attempted": sum(r["not_attempted"] for r in report["rows"]),
            },
        )
    # The published appendix is independent of the destination prefix. This also
    # reproduces the full report into a new temporary directory without raw writes.
    appendix = evidence_path or ROOT / "results/summary/e2-musique-s500-evidence.json"
    if dataset == "musique" and Path(appendix).exists():
        evidence = dense.read_json(appendix)
        if (
            evidence_path is not None
            or directory.name == evidence["raw_directory_name"]
        ):
            apply_report_evidence(safe, directory, appendix)
    if dataset == "hotpotqa":
        safe["execution_code_sha256"] = plan["code_sha256"]
        safe["report_code_sha256"] = dense.sha256_file(Path(__file__))
        if spec:
            safe["S500_physical_accounting"]["cost_complete"] = (
                known["complete"]
                and spec["parent_physical"]["unknown_reservation_not_actual"] == 0
            )
        history = plan["s500"]["historical_E2_report"]
        require(
            dense.sha256_file(Path(history["path"])) == history["sha256"],
            "Hot_history_changed",
        )
        prior = dense.read_json(Path(history["path"]))["cumulative_E2_accounting"]
        safe["sealed_historical_unknown"] = plan["sealed_unknown"]
        safe["historical_E2_report"] = history
        physical = safe.get(
            "S500_physical_accounting",
            {"known_subtotal": known["known_subtotal"], "POST": len(starts)},
        )
        safe["cumulative_E2_accounting"] = {
            "known_tokens": prior.get("known_tokens", 0)
            + sum(physical["known_subtotal"].values()),
            "physical_POST": prior.get("physical_POST", 0) + physical["POST"],
            "unknown_operations": prior.get("unknown_operations"),
            "unknown_reservations_not_actual": prior.get(
                "unknown_reservations_not_actual"
            ),
            "prior": prior,
            "new_physical": known,
            "new_POST": len(starts),
            "cost_complete": False,
            "scope": "prior E2 plus Hot new physical once; logical reuse and E1 excluded",
        }
        safe["terminal_audit"] = {
            "expected": EXPECTED_IDS * len(e2.METHODS),
            "inherited": len(plan["parent_run"]["cases"]),
            "new": len(manifest["results"]),
            "completed": sum(r["completed"] for r in report["rows"]),
            "failed": sum(r["attempted_failed"] for r in report["rows"]),
            "not_attempted": sum(r["not_attempted"] for r in report["rows"]),
            "manifest_sha256": manifest_sha,
            "journal_sha256": dense.sha256_file(directory / "usage.jsonl"),
        }
    dense.write_json_atomic(prefix.with_suffix(".json"), safe)
    lines = [
        "# " + dataset + " S500: " + manifest["status"],
        "",
        "Descriptive S500 includes development. Source latency is not fresh E2E. RAPTOR provenance is not passage recall@5. Mixed Hippo errors and incomplete E1/source cost retained.",
        "",
        "| Method | Completed / failed / not attempted | EM | F1 | Passage recall@5 | RAPTOR provenance | Fresh E2E seconds (n) | S500 reader/filter/BGE known tokens |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for r in report["rows"]:
        usage = r.get("S500_physical_usage", r["new_physical_usage"])
        tokens = "/".join(
            str(sum(usage[op]["known_subtotal"].values()))
            for op in ("reader", "filter", "query_embedding")
        )
        lines.append(
            f"| {r['method']} | {r['completed']} / {r['attempted_failed']} / {r['not_attempted']} | {r['em']} | {r['f1']} | {r['passage_recall_at_5']} | {r['provenance_coverage'] if r['method'] == 'raptor' else None} | {r.get('S500_mean_fresh_e2e_seconds', r['mean_fresh_e2e_seconds'])} ({r.get('S500_fresh_e2e_cases', r['fresh_e2e_cases'])}) | {tokens} |"
        )
    lines += [
        "",
        f"New physical known tokens {known['known_subtotal']}; POST {len(starts)}; usage complete={known['complete']}. Historical global expense remains separate; never add logical reuse twice. Refs #{16 if dataset == 'musique' else 17}.",
    ]
    if spec:
        lines += [
            "",
            "Historical failures remain immutable: pipeline EM/F1=0 with their original error markers. Unknown usage stays null; reservation is not actual usage. No paid or unknown failure was retried.",
            "",
            f"S500 cumulative physical: {safe['S500_physical_accounting']}; source/development and E1 remain separate. Fresh latency includes original S500 parent plus child, excludes initial pilot600. Child runtime/code pins are separate from immutable parent runtime.",
        ]
    if "tracking" in safe:
        lines += [
            "",
            "Verified offline appendix: terminal audit, tracking receipt, cumulative E2 accounting and execution/postprocessing metadata are hash-bound to this run; no tracking export performed.",
            "",
            "Cumulative E2: " + str(safe["cumulative_E2_accounting"]),
        ]
    prefix.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    require(
        dense.sha256_file(manifest_path) == manifest_sha,
        "S500_manifest_modified_during_report",
    )
    return safe


def verify_transport_runtime(parent, runtime=PARENT_RUNTIME, code_files=None):
    require(
        set(parent["code_sha256"])
        == set(CODE_FILES if code_files is None else code_files),
        "S500_parent_code_set_changed",
    )
    for name, sha in parent["code_sha256"].items():
        blob = subprocess.check_output(
            ["git", "-C", str(ROOT), "show", runtime + ":" + name]
        ).replace(b"\r\n", b"\n")
        require(
            sha
            in {
                hashlib.sha256(blob).hexdigest(),
                hashlib.sha256(blob.replace(b"\n", b"\r\n")).hexdigest(),
            },
            "S500_parent_runtime_changed",
        )


def prepare_unattempted(parent_path, directory, authorization_path):
    """One explicitly authorized sealed-unknown child of the original S500 run."""
    from scripts import e2_pilot as pilot

    parent_path, directory, authorization_path = map(
        lambda p: Path(p).resolve(), (parent_path, directory, authorization_path)
    )
    parent, auth = dense.read_json(parent_path), dense.read_json(authorization_path)
    require(
        dense.sha256_file(parent_path) == PARENT_PLAN_SHA
        and not parent["s500"].get("continuation")
        and not parent.get("sealed_unknown"),
        "S500_only_original_parent_no_second_unknown_child",
    )
    require(
        auth
        == {
            "kind": "musique_unattempted_authorization",
            "approved": True,
            "user_quote": "Делай то что нужно",
            "context": "reply to notification of one unknown reader and request for decision on199unattempted; continue only those cases without retrying unknown",
            "source": "direct user message in this task, 2026-10-29",
            "parent_plan_sha256": PARENT_PLAN_SHA,
            "expected_unattempted": EXPECTED_MISSING,
            "budget_expansion": False,
            "retry_unknown": False,
            "failure_metric_policy": "terminal infrastructure failure; pipeline EM/F1=0, failure disclosed; not a wrong reader answer",
        },
        "S500_unattempted_authorization_changed",
    )
    verify_transport_runtime(parent)
    candidate = prepare(parent["s500"]["worklist"], parent["s500"]["authorization"])
    candidate["code_sha256"] = parent["code_sha256"]
    require(candidate == parent, "S500_parent_contract_changed")
    e2.check_parent_pins(parent)
    mp = directory / "manifest.json"
    manifest = dense.read_json(mp)
    reference = accounting.verified_reference(manifest, mp)
    require(
        manifest["status"] == "failed"
        and manifest["plan_sha256"] == target.digest(parent)
        and not (directory / "running.lock").exists()
        and reference["status"] == "verified",
        "S500_parent_not_terminal",
    )
    records = accounting.read_records(directory / "usage.jsonl")
    starts = [r for r in records if r["event"] == "started"]
    ends = [r for r in records if r["event"] == "finished"]
    require(
        not records.corrupt_tail
        and len(starts) == len(ends)
        and {r["attempt_id"] for r in starts} == {r["attempt_id"] for r in ends},
        "S500_unfinished_parent_attempts",
    )
    claim = (
        Path(parent["e1_workspace"])
        / ".cache"
        / f"e2-{target.digest(parent)}.claim.json"
    )
    parent_claim = (
        claim.parent
        / f"e2-continuation-of-{target.digest(parent['parent_run']['files'])}.claim.json"
    )
    require(
        dense.read_json(claim) == {"directory": str(directory)}
        and dense.read_json(parent_claim)
        == {"plan_sha256": target.digest(parent), "directory": str(directory)},
        "S500_parent_claim_changed",
    )
    files, cases = (
        dict(parent["parent_run"]["files"]),
        copy.deepcopy(parent["parent_run"]["cases"]),
    )
    for path in (parent_path, mp, directory / "usage.jsonl", claim, parent_claim):
        files[str(path)] = dense.sha256_file(path)
    unknown, seen = [], set()
    for key, sha in manifest["results"].items():
        path = directory / f"question-{key}.json"
        result = dense.read_json(path)
        require(
            key not in cases
            and dense.sha256_file(path) == sha
            and key
            == e2.case_key(result["dataset"], result["method"], result["question_id"]),
            "S500_parent_case_changed",
        )
        if result["status"] == "completed":
            e2.verify_saved_case(parent, directory, result, records)
        else:
            unknown.append(
                pilot.seal_unknown_reader(parent, directory, result, records)
            )
        cases[key] = {"path": str(path), "sha256": sha, "status": result["status"]}
        files[str(path)] = sha
        for op in result["operations"]:
            obj = op["journal_object_id"]
            require(
                obj not in seen and not op.get("reused"),
                "S500_duplicate_or_reused_parent_attempt",
            )
            seen.add(obj)
            for suffix in (".json", ".response.json"):
                artifact = directory / (obj + suffix)
                if artifact.exists():
                    files[str(artifact)] = dense.sha256_file(artifact)
    require(
        len(unknown) == 1
        and len(starts) == len(seen)
        and seen == {r["object_id"] for r in starts},
        "S500_unknown_or_unbound_parent_attempts",
    )
    expected = {
        e2.case_key(d, m, q): {"dataset": d, "method": m, "question_id": q}
        for d, data in parent["datasets"].items()
        for m in e2.METHODS
        for q in data["question_ids"]
    }
    require(set(cases) <= set(expected), "S500_parent_cases_outside_view")
    remaining = [v for k, v in expected.items() if k not in cases]
    require(
        len(remaining) == EXPECTED_MISSING
        and all(v["method"] == "raptor" for v in remaining),
        "S500_only_expected_unattempted_RAPTOR",
    )
    known = reference["summary"]["known_subtotal"]
    available = (
        parent["max_combined_tokens"]
        - sum(known.values())
        - unknown[0]["reservation_tokens"]
    )
    available_posts = parent["max_posts"] - len(starts)
    require(
        available > 0 and 2 * len(remaining) <= available_posts,
        "S500_no_remaining_budget",
    )
    fresh = copy.deepcopy(parent)
    fresh.update(
        mode="musique_unattempted_after_explicit_reauthorization",
        sealed_unknown=unknown,
        pilot_continuation={
            "reauthorized_unattempted_only": True,
            "automatic_recovery": 0,
        },
        parent_run={
            "plan": str(parent_path),
            "directory": str(directory),
            "run_id": manifest["run_id"],
            "files": files,
            "cases": cases,
        },
        remaining_cases=remaining,
        max_combined_tokens=available,
        max_posts=2 * len(remaining),
        max_llm_posts=len(remaining),
        max_embedding_posts=len(remaining),
        reader_calls=len(remaining),
        filter_calls=0,
        code_sha256={n: dense.sha256_file(ROOT / n) for n in CODE_FILES},
    )
    fresh["s500"]["continuation"] = {
        "parent_plan": str(parent_path),
        "parent_directory": str(directory),
        "authorization": str(authorization_path),
        "authorization_sha256": dense.sha256_file(authorization_path),
        "parent_physical": {
            "known_subtotal": known,
            "POST": len(starts),
            "unknown_reservation_not_actual": unknown[0]["reservation_tokens"],
        },
        "initial_reuse_cases": sorted(parent["parent_run"]["cases"]),
    }
    return fresh
