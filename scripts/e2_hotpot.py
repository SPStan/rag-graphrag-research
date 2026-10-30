"""Explicit HotpotQA S500 binding of the shared planner and transport."""

from pathlib import Path
from scripts import e2_s500 as shared, run_dense as dense

VERSION = "e2-hotpotqa-s500-v1"
TOKEN_CAP = 4982220
EXPECTED_IDS = 500
ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "results/summary/e2-hotpotqa-s500-authorization.json"
CODE_FILES = (*shared.CODE_FILES, "scripts/e2_hotpot.py")


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
    shared.require(
        prepare(plan["s500"]["worklist"], plan["s500"]["authorization"]) == plan,
        "Hot_execution_plan_changed",
    )
    return True


def guard(calls, payload, method, dataset, qid, operation):
    shared.require(
        dense.sha256_file(Path(calls.plan["s500"]["authorization"]))
        == calls.plan["s500"]["authorization_sha256"],
        "Hot_authorization_changed",
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
