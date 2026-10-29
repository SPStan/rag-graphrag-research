"""Approved MuSiQue S500 extension of the existing shared E2 runner."""

import ast
import copy
import json
from pathlib import Path

from scripts import e2_evaluation as e2, run_dense as dense, run_dense_target as target
from scripts import token_accounting as accounting

VERSION = "e2-musique-s500-v1"
EXPECTED_IDS = 500
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
                and test.comparators[0].value == VERSION
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
    """Rebuild private execution metadata offline; never modifies old sources."""
    from scripts import full_experiment as full

    worklist_path, authorization_path = (
        Path(worklist_path).resolve(),
        Path(authorization_path).resolve(),
    )
    worklist, auth = dense.read_json(worklist_path), dense.read_json(authorization_path)
    validate_authorization(auth)
    source_path = ROOT / full.PUBLIC
    frozen = dense.read_json(source_path)
    original_path, original_dir = ROOT / full.PLAN, ROOT / full.OUTPUT
    parent = dense.read_json(original_path)
    e1 = dense.read_json(Path(parent["e1_plan"]))
    actual = full.freeze(ROOT, e1["data_root"], parent["e1_workspace"])
    require(
        actual == frozen and full.musique_worklist(frozen) == worklist,
        "S500_source_or_worklist_changed",
    )
    require(
        worklist["budget_proposal"]["proposed_new_token_cap"] == TOKEN_CAP,
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
            key = e2.case_key("musique", method["method"], result["question_id"])
            path, sha = refs[key]
            require(
                sha == result["result_sha256"] and dense.sha256_file(path) == sha,
                "S500_inherited_result_changed",
            )
            cases[key] = {"path": str(path), "sha256": sha, "status": "completed"}
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
    data = copy.deepcopy(parent["datasets"]["musique"])
    data["question_ids"] = worklist["question_ids"]
    raw = Path(e1["data_root"]) / "data/processed/musique"
    data["queries_sha256"] = target.digest(
        e2.select_in_view(
            dense.read_json(raw / "queries.json"), data["question_ids"], "query"
        )
    )
    data["ordered_ids_sha256"] = worklist["ordered_ids_sha256"]
    value.update(
        version=VERSION,
        mode="approved_musique_S500_missing_only",
        datasets={"musique": data},
        http_authorized=True,
        max_posts=2100,
        max_llm_posts=1200,
        max_embedding_posts=900,
        reader_calls=900,
        filter_calls=300,
        max_combined_tokens=TOKEN_CAP,
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
    return value


def verify(plan):
    require(
        plan.get("version") == VERSION
        and set(plan["datasets"]) == {"musique"}
        and len(plan["datasets"]["musique"]["question_ids"]) == EXPECTED_IDS,
        "S500_only_frozen_MuSiQue500",
    )
    require(
        prepare(plan["s500"]["worklist"], plan["s500"]["authorization"]) == plan,
        "S500_execution_plan_changed",
    )
    return True


def guard(calls, payload, method, dataset, qid, operation):
    plan = calls.plan
    require(
        plan.get("http_authorized") is True
        and set(plan["datasets"]) == {"musique"}
        and dataset == "musique"
        and method in e2.METHODS
        and qid in plan["datasets"]["musique"]["question_ids"],
        "S500_case_outside_approved_scope",
    )
    require(
        plan["max_combined_tokens"] <= TOKEN_CAP
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
    report["historical_source_accounting"] = plan["s500"]["source_global_cost"]


def write_report(plan_path, directory, public_prefix):
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
        set(plan["datasets"]) == {"musique"}
        and len(plan["datasets"]["musique"]["question_ids"]) == EXPECTED_IDS,
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
    dense.write_json_atomic(directory / "evaluation.json", report)
    starts = [r for r in records if r["event"] == "started"]
    known = accounting.summarize(records)
    safe = {
        "kind": "e2_musique_S500",
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
    dense.write_json_atomic(prefix.with_suffix(".json"), safe)
    lines = [
        "# MuSiQue S500: " + manifest["status"],
        "",
        "Descriptive S500 includes development. Source latency is not fresh E2E. RAPTOR provenance is not passage recall@5. Mixed Hippo errors and incomplete E1/source cost retained.",
        "",
        "| Method | Completed / failed / not attempted | EM | F1 | Passage recall@5 | RAPTOR provenance | Fresh E2E seconds (n) | New reader/filter/BGE known tokens |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for r in report["rows"]:
        usage = r["new_physical_usage"]
        tokens = "/".join(
            str(sum(usage[op]["known_subtotal"].values()))
            for op in ("reader", "filter", "query_embedding")
        )
        lines.append(
            f"| {r['method']} | {r['completed']} / {r['attempted_failed']} / {r['not_attempted']} | {r['em']} | {r['f1']} | {r['passage_recall_at_5']} | {r['provenance_coverage'] if r['method'] == 'raptor' else None} | {r['mean_fresh_e2e_seconds']} ({r['fresh_e2e_cases']}) | {tokens} |"
        )
    lines += [
        "",
        f"New physical known tokens {known['known_subtotal']}; POST {len(starts)}; usage complete={known['complete']}. Historical global expense remains separate; never add logical reuse twice. Refs #16.",
    ]
    prefix.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    require(
        dense.sha256_file(manifest_path) == manifest_sha,
        "S500_manifest_modified_during_report",
    )
    return safe
