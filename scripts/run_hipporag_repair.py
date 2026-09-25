"""Run the explicitly bounded first OpenIE repair pass using native Ollama chat."""

import argparse
import hashlib
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from scripts.hipporag_repair import plan_openie_repairs
from scripts.hipporag_repair_executor import (
    make_native_ollama_request, make_pinned_openie_parser,
    measure_then_execute_openie_task, render_openie_messages,
)
from scripts.hipporag_repair_journal import RepairJournal
from scripts.plan_hipporag_repair import (
    ROOT, SOURCE_RUN_ID, build_plan_report, load_source_inputs,
)
from scripts.preflight_hipporag_repair_prompts import validate_upstream_pin
from scripts.run_hipporag import model_info, sha256_file

MAX_TASKS = 196
MAX_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT = 300
EXPECTED_PLAN_SHA = "f6ea09286136724f67621e24c4efc64913051a5fea1456d808a88ea1a6ec6d7e"
EXPECTED_DIGEST = "357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b"
STOPPED_CHECKPOINT_SHA = "83f61962940c06c912ff0c595a8617be298698b802151bc50d8136d2ef331d13"
REMEDIAL_CAP = 2048
EXPECTED_SOURCE_HASHES = {
    "openie_state": "728b93a078a28eee94267a9da0522c6460d535a66aa8cf55527ab69f12754f85",
    "graph": "cc7d53101cd7fc53e95beaece956ed5ec6cc9e19cdb30b1ecf84221567d0fbe6",
    "chunk_metadata": "7e8b519b809923a54483ec5377077332068f36d0e57c4206fc4cf886ffbd05d0",
    "chunk_embeddings": "b9435c1b72271555cd1da3c91ad082f6b5ca167514e38d626c71bf6765260f84",
    "entity_embeddings": "90ebde2437bed03a487aa95625025aaeb897fd32448e99d17c13b15a691ebf2c",
    "fact_embeddings": "7fe8f81c07ce51aa915b6ae25333a6dd5ec9eb1c1e58114d3407c5bc2cbe85b6",
    "index_manifest": "696eca0444d8818c9c62c1ab9c6855de8ecd86130431d3730eb4cd95ede2c79d",
}


def _post_json(endpoint, deadline, *, model):
    gpu_checked = False

    def post(payload):
        nonlocal gpu_checked
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Six-hour repair deadline reached")
        request = Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=min(REQUEST_TIMEOUT, remaining)) as response:
            result = json.load(response)
        if payload.get("options", {}).get("num_predict") == 1 and not gpu_checked:
            ps_url = endpoint.removesuffix("/api/chat") + "/api/ps"
            with urlopen(ps_url, timeout=min(20, max(1, deadline - time.monotonic()))) as response:
                running = json.load(response).get("models", [])
            loaded = next((row for row in running
                           if row.get("name") == model or row.get("model") == model), None)
            if not loaded or not isinstance(loaded.get("size_vram"), int) or loaded["size_vram"] <= 0:
                raise RuntimeError("Ollama did not confirm GPU VRAM allocation; stopping")
            gpu_checked = True
            print(json.dumps({"gpu_vram_bytes": loaded["size_vram"],
                              "gpu_verified": True}), flush=True)
        return result
    return post


def _source_artifacts(storage_dir):
    storage = Path(storage_dir)
    candidates = {
        "openie_state": list(storage.rglob("openie_state.json")),
        "graph": list(storage.rglob("graph.pickle")),
        "chunk_metadata": list(storage.rglob("chunk_metadata.json")),
        "chunk_embeddings": list(storage.rglob("vdb_chunk.parquet")),
        "entity_embeddings": list(storage.rglob("vdb_entity.parquet")),
        "fact_embeddings": list(storage.rglob("vdb_fact.parquet")),
        "index_manifest": list(storage.rglob("index_manifest.json")),
    }
    paths = {}
    for key, matches in candidates.items():
        if len(matches) != 1:
            raise ValueError(f"Expected one source artifact for {key}, found {len(matches)}")
        paths[key] = matches[0]
        if sha256_file(matches[0]) != EXPECTED_SOURCE_HASHES[key]:
            raise ValueError(f"Source artifact hash changed: {key}")
    return paths


def _source_state(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    return state


def run_remedial_ner(args, *, dry_run=False):
    """One new attempt-3 NER task; never reopen the stopped 196-task writer."""
    manifest, passage_ids, source_attempts, manifest_sha, corpus_sha = load_source_inputs(args.manifest)
    plan = build_plan_report(manifest["run_id"], passage_ids, source_attempts,
                             manifest_sha256=manifest_sha, corpus_sha256=corpus_sha)
    if plan["plan_sha256"] != EXPECTED_PLAN_SHA:
        raise ValueError("Frozen first-pass plan changed")
    distribution = importlib.metadata.distribution("hipporag")
    validate_upstream_pin(distribution.version, distribution.read_text("direct_url.json"))
    artifacts = _source_artifacts(manifest["storage_dir"])
    original = ROOT / "storage" / "hipporag2-independent-s500-200-299-repair-f6ea0928" / "openie-repair-checkpoint.json"
    if sha256_file(original) != STOPPED_CHECKPOINT_SHA:
        raise ValueError("Stopped checkpoint SHA changed")
    old = json.loads(original.read_text(encoding="utf-8"))
    rows = old.get("attempts", [])
    if (old.get("status") != "stopped"
            or old.get("stop_reason") != "unresolved_extraction"
            or old.get("in_flight") is not None
            or old.get("next_task_index") != 2
            or old.get("identity", {}).get("plan_sha256") != EXPECTED_PLAN_SHA
            or old.get("identity", {}).get("schedule_size") != MAX_TASKS
            or len(rows) != 2
            or rows[0]["attempt"].get("status") not in ("valid_empty", "valid_nonempty")
            or rows[1]["attempt"].get("stage") != "openie_ner"
            or rows[1]["attempt"].get("attempt") != 2
            or rows[1]["attempt"].get("status") != "truncated"
            or rows[1]["attempt"].get("finish_reason") != "length"
            or rows[1]["attempt"].get("retry_of_attempt") != 1):
        raise ValueError("Stopped checkpoint is not the approved two-task result")
    for row in rows:
        RepairJournal._validate_output(row)
    old_protocol = old["identity"]["protocol"]
    generation = manifest["generation"]
    model, digest = generation["model"]["name"], generation["model"]["digest"]
    if (digest != EXPECTED_DIGEST or old_protocol != {
            "model": model, "model_digest": digest, "num_ctx": 4096,
            "seed": 42, "temperature": 0.0,
            "ner_max_new_tokens": 1024, "triples_max_new_tokens": 3072}):
        raise ValueError("Frozen model or stopped protocol changed")
    source_task = rows[1]["task"]
    task = {"passage_id": source_task["passage_id"], "stage": "openie_ner",
            "attempt": 3, "retry_of_attempt": 2, "remedial_retry": True}
    if task["passage_id"] not in passage_ids:
        raise ValueError("Remedial passage ID is absent from source corpus")
    task_bytes = json.dumps(task, sort_keys=True, separators=(",", ":")).encode("utf-8")
    plan_sha = hashlib.sha256(task_bytes).hexdigest()
    namespace = ROOT / "storage" / f"hipporag2-remedial-ner3-cap2048-{plan_sha[:8]}"
    if dry_run:
        if namespace.exists():
            raise ValueError("Remedial namespace already exists")
        print(json.dumps({"status": "remedial_offline_preflight_passed",
                          "tasks": 1, "max_model_requests": 2,
                          "output_cap": REMEDIAL_CAP, "num_ctx": 4096,
                          "source_checkpoint_sha256": STOPPED_CHECKPOINT_SHA,
                          "source_hashes_verified": len(artifacts),
                          "plan_sha256": plan_sha,
                          "proposed_namespace": str(namespace)}), flush=True)
        return
    if namespace.exists():
        raise ValueError("Remedial namespace already exists; no automatic replay")
    if model_info(model, generation["endpoint"])["digest"] != digest:
        raise ValueError("Installed model digest changed")
    from scripts.run_hipporag import canonical_key, passage_id as make_passage_id
    corpus = json.loads(Path(manifest["inputs"]["corpus_path"]).read_text(encoding="utf-8"))
    matches = []
    for item in corpus:
        title, text = canonical_key(item["title"], item["text"])
        if (item.get("id") or make_passage_id(title, text)) == task["passage_id"]:
            matches.append(title + "\n" + text)
    if len(matches) != 1:
        raise ValueError("Remedial passage is not unique in source corpus")
    protocol = {**old_protocol, "ner_max_new_tokens": REMEDIAL_CAP}
    source_hashes = {"manifest": manifest_sha, "corpus": corpus_sha,
                     "stopped_checkpoint": STOPPED_CHECKPOINT_SHA,
                     **EXPECTED_SOURCE_HASHES}
    endpoint = generation["endpoint"].removesuffix("/v1").rstrip("/") + "/api/chat"
    deadline = time.monotonic() + 600
    request_fn = make_native_ollama_request(
        endpoint, protocol=protocol, model_digest=digest,
        post_json=_post_json(endpoint, deadline, model=model))
    namespace.mkdir(parents=True)
    path = namespace / "openie-repair-checkpoint.json"
    with RepairJournal(path, plan_sha256=plan_sha, source_hashes=source_hashes,
                       protocol=protocol,
                       expected_task_keys=[RepairJournal.task_key(task)]) as journal:
        journal.begin(task)
        result = measure_then_execute_openie_task(
            task, matches[0], None, request_fn=request_fn,
            parse_fn=make_pinned_openie_parser(), run_id=manifest["run_id"],
            model_digest=digest, model_requests_enabled=True)
        journal.complete(task, result["attempt"], result["values"])
        if result["attempt"]["status"] in ("valid_empty", "valid_nonempty"):
            journal.finish(expected_task_keys=[RepairJournal.task_key(task)])
        else:
            journal.stop("unresolved_extraction")
    if sha256_file(original) != STOPPED_CHECKPOINT_SHA:
        raise RuntimeError("Original stopped checkpoint changed")
    print(json.dumps({"status": result["attempt"]["status"],
                      "requests": 2, "checkpoint_sha256": sha256_file(path),
                      "original_checkpoint_unchanged": True,
                      "embeddings_rebuild_qa": "not run"}), flush=True)


def run(args, *, dry_run=False):
    manifest, passage_ids, source_attempts, manifest_sha, corpus_sha = load_source_inputs(args.manifest)
    plan_report = build_plan_report(manifest["run_id"], passage_ids, source_attempts,
                                    manifest_sha256=manifest_sha, corpus_sha256=corpus_sha)
    if plan_report["plan_sha256"] != EXPECTED_PLAN_SHA:
        raise ValueError("Frozen plan SHA changed")
    targets = plan_openie_repairs(passage_ids, source_attempts)["targets"]
    if len(targets) != MAX_TASKS:
        raise ValueError("Frozen schedule is not exactly 196 tasks")
    if (sum(t["stage"] == "openie_ner" for t in targets) != 38
            or sum(t["stage"] == "openie_triples" for t in targets) != 158):
        raise ValueError("Frozen stage counts differ from approved schedule")

    distribution = importlib.metadata.distribution("hipporag")
    validate_upstream_pin(distribution.version, distribution.read_text("direct_url.json"))
    artifacts = _source_artifacts(manifest["storage_dir"])
    namespace = ROOT / "storage" / "hipporag2-independent-s500-200-299-repair-f6ea0928"
    if dry_run:
        if namespace.exists():
            raise ValueError("Fresh repair namespace already exists; refusing to reuse it")
        print(json.dumps({"status": "offline_preflight_passed",
                          "tasks": len(targets), "ner": 38, "triples": 158,
                          "plan_sha256": EXPECTED_PLAN_SHA,
                          "source_hashes_verified": len(artifacts),
                          "model_requests": 0,
                          "proposed_namespace": str(namespace)}, ensure_ascii=False))
        return
    state = _source_state(artifacts["openie_state"])
    corpus = json.loads(Path(manifest["inputs"]["corpus_path"]).read_text(encoding="utf-8"))
    passage_by_id = {}
    from scripts.run_hipporag import canonical_key, passage_id as make_passage_id
    for item in corpus:
        title, text = canonical_key(item["title"], item["text"])
        passage_by_id[item.get("id") or make_passage_id(title, text)] = title + "\n" + text
    state_by_passage = {doc["passage"]: doc for doc in state["docs"]}
    generation = manifest["generation"]
    model, digest = generation["model"]["name"], generation["model"]["digest"]
    if digest != EXPECTED_DIGEST or model_info(model, generation["endpoint"])["digest"] != digest:
        raise ValueError("Installed model digest differs from the frozen Qwen2.5 digest")
    protocol = {"model": model, "model_digest": digest,
                "num_ctx": 4096, "seed": 42, "temperature": 0.0,
                "ner_max_new_tokens": 1024, "triples_max_new_tokens": 3072}

    namespace.mkdir(parents=True, exist_ok=True)
    journal_path = namespace / "openie-repair-checkpoint.json"
    task_keys = [RepairJournal.task_key(task) for task in targets]
    source_hashes = {"manifest": manifest_sha, "corpus": corpus_sha, **EXPECTED_SOURCE_HASHES}
    state_by_passage = {doc["passage"]: doc for doc in state["docs"]}
    endpoint = generation["endpoint"].removesuffix("/v1").rstrip("/") + "/api/chat"
    deadline = time.monotonic() + MAX_SECONDS
    request_fn = make_native_ollama_request(endpoint, protocol=protocol,
                                            model_digest=digest,
                                            post_json=_post_json(endpoint, deadline, model=model))
    parse_fn = make_pinned_openie_parser()
    completed_this_run = 0
    started = datetime.now(timezone.utc).isoformat()
    with RepairJournal(journal_path, plan_sha256=EXPECTED_PLAN_SHA,
                       source_hashes=source_hashes, protocol=protocol,
                       expected_task_keys=task_keys) as journal:
        if journal.data.get("status") == "stopped":
            raise RuntimeError("Checkpoint is explicitly stopped; manual reconciliation required")
        if any(row["attempt"].get("status") not in ("valid_empty", "valid_nonempty")
               for row in journal.data["attempts"]):
            journal.stop("unresolved_extraction")
            raise RuntimeError("Checkpoint contains unresolved extraction; refusing auto-resume")
        for index in range(len(journal.data["completed_task_keys"]), len(targets)):
            if time.monotonic() >= deadline:
                raise TimeoutError("Six-hour repair deadline reached; checkpoint retained")
            task = dict(targets[index])
            entities = None
            if task["stage"] == "openie_triples":
                if task.get("operation") == "dependency_refresh":
                    ners = [r for r in journal.data["attempts"]
                            if r["task"]["passage_id"] == task["passage_id"]
                            and r["task"]["stage"] == "openie_ner"]
                    if len(ners) != 1 or ners[0]["attempt"]["status"] not in ("valid_empty", "valid_nonempty"):
                        raise RuntimeError("NER repair failed; stopping before dependent triples")
                    task.pop("dependency_attempt_pending", None)
                    task["dependency_attempt"] = ners[0]["task"]["attempt"]
                    entities = ners[0]["values"]
                else:
                    doc = state_by_passage[passage_by_id[task["passage_id"]]]
                    entities = doc["extracted_entities"]
            passage = passage_by_id[task["passage_id"]]
            journal.begin(task)
            result = measure_then_execute_openie_task(
                task, passage, entities, request_fn=request_fn, parse_fn=parse_fn,
                run_id=manifest["run_id"], model_digest=digest,
                model_requests_enabled=True)
            journal.complete(task, result["attempt"], result["values"])
            completed_this_run += 1
            print(json.dumps({"completed": len(journal.data["completed_task_keys"]),
                              "total": MAX_TASKS,
                              "stage": task["stage"],
                              "status": result["attempt"]["status"]}), flush=True)
            if result["attempt"]["status"] not in ("valid_empty", "valid_nonempty"):
                journal.stop("unresolved_extraction")
                raise RuntimeError("Unresolved extraction; stopped with checkpoint")
        journal.finish(expected_task_keys=task_keys)
    print(json.dumps({"status": "repair_complete", "started_at": started,
                      "ended_at": datetime.now(timezone.utc).isoformat(),
                      "tasks_completed_this_run": completed_this_run,
                      "checkpoint": str(journal_path),
                      "embeddings_rebuild_qa": "not run"}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="explicitly enable bounded local model requests")
    parser.add_argument("--dry-run", action="store_true",
                        help="verify the frozen plan and source hashes without network calls")
    parser.add_argument("--remedial-ner", action="store_true",
                        help="run only the approved one-task attempt-3 NER revision")
    parser.add_argument("--manifest", type=Path, default=ROOT / "results" / "raw" /
                        f"hipporag2-musique-{SOURCE_RUN_ID}.manifest.json")
    args = parser.parse_args()
    if args.remedial_ner:
        if not args.dry_run and not args.execute:
            raise SystemExit("Refusing: remedial model requests require --execute")
        run_remedial_ner(args, dry_run=args.dry_run)
        return
    if args.dry_run:
        run(args, dry_run=True)
        return
    if not args.execute:
        raise SystemExit("Refusing: pass --execute after explicit user authorization")
    run(args)


if __name__ == "__main__":
    main()
