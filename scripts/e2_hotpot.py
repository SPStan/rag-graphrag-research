"""Explicit HotpotQA S500 binding of the shared planner and transport."""

import copy
from pathlib import Path
from scripts import e2_s500 as shared, run_dense as dense

VERSION = "e2-hotpotqa-s500-v1"
TOKEN_CAP = 4982220
EXPECTED_IDS = 500
ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "results/summary/e2-hotpotqa-s500-authorization.json"
CODE_FILES = (*shared.CODE_FILES, "scripts/e2_hotpot.py")
PARENT_RUNTIME = "7a6779182468448957ee1df746007c4b5019bfec"
PARENT_PLAN_SHA = "ce5a2b70c805e99d23ffcc26e1d34638df8cb249371500e6fda8de143c6b9b50"
EXPECTED_MISSING = 429
FILTER_CASE_KEY = ""  # Bound below by the common case identity function.


def validate_authorization(value):
    shared.require(
        value
        == {
            "kind": "hotpotqa_S500_execution_authorization",
            "dataset": "hotpotqa",
            "approved": True,
            "new_token_cap": TOKEN_CAP,
            "new_POST_caps": {"reader": 900, "filter": 300, "query_embedding": 900},
            "retry": 0,
            "automatic_resumes": 2,
            "source": "direct user instruction 2026-10-30; scientific approval required before merge, not execution",
            "scope": "900missing only; sealed unknown never repeated; fixed scientific configuration",
        },
        "Hot_authorization_changed",
    )


def prepare(worklist_path, authorization_path=AUTHORIZATION):
    authorization_path = Path(authorization_path)
    plan = shared.prepare_dataset(
        worklist_path,
        authorization_path,
        dataset="hotpotqa",
        version=VERSION,
        token_cap=TOKEN_CAP,
        validator=validate_authorization,
    )
    plan["code_sha256"] = {n: dense.sha256_file(ROOT / n) for n in CODE_FILES}
    history = ROOT / "results/summary/e2-musique-s500.json"
    plan["parent_run"]["files"][str(history)] = dense.sha256_file(history)
    plan["s500"]["historical_E2_report"] = {
        "path": str(history),
        "sha256": dense.sha256_file(history),
    }
    plan["s500"]["dataset"] = "hotpotqa"
    plan["s500"]["authorization_sha256"] = dense.sha256_file(authorization_path)
    return plan


def verify(plan):
    shared.require(
        set(plan["datasets"]) == {"hotpotqa"}
        and len(plan["datasets"]["hotpotqa"]["question_ids"]) == EXPECTED_IDS,
        "Hot_scope_changed",
    )
    spec = plan["s500"].get("continuation")
    candidate = (
        prepare_unattempted(
            spec["parent_plan"], spec["parent_directory"], spec["authorization"]
        )
        if spec
        else prepare(plan["s500"]["worklist"], plan["s500"]["authorization"])
    )
    shared.require(candidate == plan, "Hot_execution_plan_changed")
    return True


def guard(calls, payload, method, dataset, qid, operation):
    shared.require(
        dense.sha256_file(Path(calls.plan["s500"]["authorization"]))
        == calls.plan["s500"]["authorization_sha256"],
        "Hot_authorization_changed",
    )
    spec = calls.plan["s500"].get("continuation")
    if spec:
        from scripts import e2_evaluation as e2

        ledger = dense.read_json(Path(spec["registry"]))
        shared.require(
            ledger["automatic_resumes"] == 2
            and ledger["plan_digest"] == e2.target.digest(calls.plan),
            "Hot_continuation_not_admitted",
        )
    return shared.guard_dataset(
        calls,
        payload,
        method,
        dataset,
        qid,
        operation,
        expected_dataset="hotpotqa",
        token_cap=TOKEN_CAP,
    )


def write_report(plan_path, directory, public_prefix):
    return shared.write_dataset_report(
        plan_path, directory, public_prefix, dataset="hotpotqa"
    )


def resume_preflight(plan_path, directory, registry_path):
    """Admit only a clean stopped boundary, in the same output/plan/claims.

    A failed manifest, stale lock, unbound POST or missing durable checkpoint
    remains a blocker. This does not convert any failed run into a runnable run.
    """
    import os
    from scripts import e2_evaluation as e2, token_accounting as accounting

    plan_path, directory, registry_path = map(
        Path, (plan_path, directory, registry_path)
    )
    plan = dense.read_json(plan_path)
    verify(plan)
    shared.require(
        not (directory / "running.lock").exists(), "Hot_active_or_stale_lock_no_resume"
    )
    manifest = dense.read_json(directory / "manifest.json")
    shared.require(
        manifest["status"] == "partial_completed_methods",
        "Hot_resume_requires_clean_method_boundary",
    )
    shared.require(
        manifest["plan_sha256"] == e2.target.digest(plan), "Hot_resume_plan_changed"
    )
    records, _ = shared.current_records(plan, directory, manifest)
    shared.require(accounting.summarize(records)["complete"], "Hot_unknown_no_resume")
    refs = e2.result_references(plan, manifest, directory)
    objects = set()
    for key in manifest["results"]:
        result = dense.read_json(refs[key][0])
        e2.verify_saved_case(plan, directory, result, records)
        objects.update(
            o["journal_object_id"]
            for o in result["operations"]
            if o.get("physical_attempted")
        )
    starts = [r for r in records if r["event"] == "started"]
    shared.require(
        len(starts) == len(objects) and {r["object_id"] for r in starts} == objects,
        "Hot_unbound_attempt_no_resume",
    )
    state = dense.read_json(registry_path)
    shared.require(
        state["plan_sha256"] == dense.sha256_file(plan_path)
        and state["output"] == str(directory.resolve()),
        "Hot_recovery_registry_changed",
    )
    shared.require(state["automatic_resumes"] < 2, "Hot_recovery_limit")
    # Exclusive durable ledger lock; an interrupted admission blocks rather than resets.
    with registry_path.with_suffix(".lock").open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
        stream.flush()
        os.fsync(stream.fileno())
        state["automatic_resumes"] += 1
        state.setdefault("admissions", []).append(
            {
                "manifest_sha256": dense.sha256_file(directory / "manifest.json"),
                "new_POST": len(starts),
            }
        )
        dense.write_json_atomic(registry_path, state)
    registry_path.with_suffix(".lock").unlink()
    return state


def admit_preclaim_rebind(old_plan_path, new_plan_path, directory, registry_path):
    """Technical code-only rebind before ANY run/claim/POST has been created.

    This is not continuation of a failed run: existing output or either claim
    rejects admission. Old plans/diagnostics remain immutable.
    """
    import os
    from scripts import e2_evaluation as e2

    old_plan_path, new_plan_path, directory, registry_path = map(
        Path, (old_plan_path, new_plan_path, directory, registry_path)
    )
    old, new = dense.read_json(old_plan_path), dense.read_json(new_plan_path)
    shared.require(
        old["version"] == new["version"] == VERSION, "Hot_preclaim_version_changed"
    )
    shared.require(
        {k: v for k, v in old.items() if k != "code_sha256"}
        == {k: v for k, v in new.items() if k != "code_sha256"},
        "Hot_preclaim_not_code_only",
    )
    shared.require(not directory.exists(), "Hot_existing_output_not_preclaim")
    for plan in (old, new):
        workspace = Path(plan["e1_workspace"]) / ".cache"
        shared.require(
            not (workspace / f"e2-{e2.target.digest(plan)}.claim.json").exists(),
            "Hot_existing_plan_claim_not_preclaim",
        )
        shared.require(
            not (
                workspace
                / f"e2-continuation-of-{e2.target.digest(plan['parent_run']['files'])}.claim.json"
            ).exists(),
            "Hot_existing_parent_claim_not_preclaim",
        )
    verify(new)
    state = dense.read_json(registry_path)
    shared.require(
        state["plan_sha256"] == dense.sha256_file(old_plan_path)
        and state["output"] == str(directory.resolve()),
        "Hot_preclaim_registry_mismatch",
    )
    shared.require(state["automatic_resumes"] < 2, "Hot_recovery_limit")
    with registry_path.with_suffix(".lock").open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
        stream.flush()
        os.fsync(stream.fileno())
        state["automatic_resumes"] += 1
        state.setdefault("admissions", []).append(
            {
                "kind": "preclaim_code_only_rebind",
                "old_plan_sha256": dense.sha256_file(old_plan_path),
                "new_plan_sha256": dense.sha256_file(new_plan_path),
                "physical_POST": 0,
                "unknown": 0,
            }
        )
        state["plan_sha256"] = dense.sha256_file(new_plan_path)
        dense.write_json_atomic(registry_path, state)
    registry_path.with_suffix(".lock").unlink()
    return state


def continuation_authorization(parent_sha, manifest_sha):
    return {
        "kind": "Hot_known_failure_unattempted_authorization",
        "approved": True,
        "user_quote": "Делай то что нужно",
        "source": "direct reply 2026-10-30 after notification of E2_filter_shape_invalid and429not_attempted",
        "parent_plan_sha256": parent_sha,
        "parent_manifest_sha256": manifest_sha,
        "expected_unattempted": EXPECTED_MISSING,
        "retry_paid_or_unknown": False,
        "budget_expansion": False,
        "filter_policy": "fatal in original run; retain failed case unchanged with pipeline zero, never retry; new run only previously unattempted cases",
    }


def prepare_unattempted(parent_path, directory, authorization_path):
    """Existing missing-only lineage, limited to one known-failure Hot child."""
    from scripts import e2_evaluation as e2, token_accounting as accounting

    parent_path, directory, authorization_path = (
        Path(p).resolve() for p in (parent_path, directory, authorization_path)
    )
    parent = dense.read_json(parent_path)
    shared.require(
        dense.sha256_file(parent_path) == PARENT_PLAN_SHA
        and not parent["s500"].get("continuation"),
        "Hot_only_original_failed_parent",
    )
    manifest_path = directory / "manifest.json"
    auth = dense.read_json(authorization_path)
    shared.require(
        auth
        == continuation_authorization(
            PARENT_PLAN_SHA, dense.sha256_file(manifest_path)
        ),
        "Hot_unattempted_authorization_changed",
    )
    shared.verify_transport_runtime(
        parent, runtime=PARENT_RUNTIME, code_files=CODE_FILES
    )
    candidate = prepare(parent["s500"]["worklist"], parent["s500"]["authorization"])
    candidate["code_sha256"] = parent["code_sha256"]
    shared.require(candidate == parent, "Hot_parent_contract_changed")
    e2.check_parent_pins(parent)
    manifest = dense.read_json(manifest_path)
    reference = accounting.verified_reference(manifest, manifest_path)
    shared.require(
        manifest["status"] == "failed"
        and manifest["plan_sha256"] == e2.target.digest(parent)
        and not (directory / "running.lock").exists()
        and reference["status"] == "verified"
        and reference["summary"]["complete"],
        "Hot_parent_not_terminal_known",
    )
    records = accounting.read_records(directory / "usage.jsonl")
    shared.require(
        not records.corrupt_tail and accounting.summarize(records)["complete"],
        "Hot_new_unknown_or_unfinished_no_continuation",
    )
    workspace = Path(parent["e1_workspace"]) / ".cache"
    claim = workspace / f"e2-{e2.target.digest(parent)}.claim.json"
    parent_claim = (
        workspace
        / f"e2-continuation-of-{e2.target.digest(parent['parent_run']['files'])}.claim.json"
    )
    shared.require(
        dense.read_json(claim) == {"directory": str(directory)}
        and dense.read_json(parent_claim)
        == {"plan_sha256": e2.target.digest(parent), "directory": str(directory)},
        "Hot_parent_claim_changed",
    )
    files, cases = (
        dict(parent["parent_run"]["files"]),
        copy.deepcopy(parent["parent_run"]["cases"]),
    )
    for path in (
        parent_path,
        manifest_path,
        directory / "usage.jsonl",
        claim,
        parent_claim,
        authorization_path,
    ):
        files[str(path)] = dense.sha256_file(path)
    seen, fatal = set(), []
    for key, sha in manifest["results"].items():
        path = directory / f"question-{key}.json"
        result = dense.read_json(path)
        shared.require(
            key not in cases
            and dense.sha256_file(path) == sha
            and key
            == e2.case_key(result["dataset"], result["method"], result["question_id"]),
            "Hot_parent_case_changed",
        )
        e2.verify_saved_case(parent, directory, result, records)
        if result.get("fatal"):
            shared.require(
                key
                == (
                    FILTER_CASE_KEY
                    or e2.case_key("hotpotqa", "hipporag2", "5adcc5715542990d50227d0a")
                )
                and result["error"]
                == {"type": "ValueError", "reason": "E2_filter_shape_invalid"}
                and result["method"] == "hipporag2"
                and result["operations"][-1]["operation"] == "filter",
                "Hot_unexpected_fatal_parent_case",
            )
            fatal.append(key)
        cases[key] = {"path": str(path), "sha256": sha, "status": result["status"]}
        files[str(path)] = sha
        for op in result["operations"]:
            obj = op["journal_object_id"]
            shared.require(
                obj not in seen
                and op.get("physical_attempted")
                and not op.get("reused"),
                "Hot_duplicate_parent_operation",
            )
            seen.add(obj)
            for suffix in (".json", ".response.json"):
                artifact = directory / (obj + suffix)
                files[str(artifact)] = dense.sha256_file(artifact)
    starts = [r for r in records if r["event"] == "started"]
    shared.require(
        len(fatal) == 1
        and len(starts) == len(seen)
        and seen == {r["object_id"] for r in starts},
        "Hot_unbound_or_unexpected_parent_attempts",
    )
    expected = {
        e2.case_key(d, m, q): {"dataset": d, "method": m, "question_id": q}
        for d, data in parent["datasets"].items()
        for m in e2.METHODS
        for q in data["question_ids"]
    }
    shared.require(set(cases) <= set(expected), "Hot_parent_outside_frozen_IDs")
    remaining = [v for k, v in expected.items() if k not in cases]
    shared.require(
        len(remaining) == EXPECTED_MISSING
        and all(v["method"] in ("hipporag2", "raptor") for v in remaining),
        "Hot_only_exact_unattempted_scope",
    )
    reader, filters, embeddings = (
        len(remaining),
        sum(v["method"] == "hipporag2" for v in remaining),
        len(remaining),
    )
    available = parent["max_combined_tokens"] - sum(
        reference["summary"]["known_subtotal"].values()
    )
    shared.require(
        available > 0
        and reader + filters + embeddings <= parent["max_posts"] - len(starts),
        "Hot_remaining_budget_exhausted",
    )
    fresh = copy.deepcopy(parent)
    fresh.update(
        mode="Hot_unattempted_after_explicit_decision",
        parent_run={
            "plan": str(parent_path),
            "directory": str(directory),
            "run_id": manifest["run_id"],
            "files": files,
            "cases": cases,
        },
        remaining_cases=remaining,
        max_combined_tokens=available,
        max_posts=reader + filters + embeddings,
        max_llm_posts=reader + filters,
        max_embedding_posts=embeddings,
        reader_calls=reader,
        filter_calls=filters,
        code_sha256={n: dense.sha256_file(ROOT / n) for n in CODE_FILES},
    )
    fresh["s500"]["continuation"] = {
        "parent_plan": str(parent_path),
        "parent_directory": str(directory),
        "authorization": str(authorization_path),
        "authorization_sha256": dense.sha256_file(authorization_path),
        "parent_physical": {
            "known_subtotal": reference["summary"]["known_subtotal"],
            "POST": len(starts),
            "unknown_reservation_not_actual": 0,
        },
        "initial_reuse_cases": sorted(parent["parent_run"]["cases"]),
        "fatal_known_cases": fatal,
        "registry": str(ROOT / ".cache/e2-hotpotqa-s500-recoveries.json"),
    }
    return fresh


def admit_unattempted(plan_path, output, registry_path):
    """One final admission; retain the common ledger and all former claims."""
    import os
    from scripts import e2_evaluation as e2

    plan_path, output, registry_path = map(Path, (plan_path, output, registry_path))
    plan = dense.read_json(plan_path)
    verify(plan)
    spec = plan["s500"]["continuation"]
    shared.require(not output.exists(), "Hot_child_output_exists")
    with registry_path.with_suffix(".lock").open("x", encoding="utf-8") as stream:
        stream.write(str(os.getpid()))
        stream.flush()
        os.fsync(stream.fileno())
        state = dense.read_json(registry_path)
        shared.require(
            state["automatic_resumes"] == 1
            and state["plan_sha256"] == dense.sha256_file(Path(spec["parent_plan"])),
            "Hot_final_admission_counter_or_parent_changed",
        )
        state.setdefault("admissions", []).append(
            {
                "kind": "explicit_unattempted_known_failure",
                "old_plan_sha256": state["plan_sha256"],
                "new_plan_sha256": dense.sha256_file(plan_path),
                "parent_known": spec["parent_physical"],
                "remaining_cases": len(plan["remaining_cases"]),
            }
        )
        state.update(
            automatic_resumes=2,
            plan_sha256=dense.sha256_file(plan_path),
            plan_digest=e2.target.digest(plan),
            output=str(output.resolve()),
            further_restarts_forbidden=True,
        )
        dense.write_json_atomic(registry_path, state)
    registry_path.with_suffix(".lock").unlink()
    return state
