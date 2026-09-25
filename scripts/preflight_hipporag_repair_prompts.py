"""Read-only prompt rendering audit for the pinned HippoRAG OpenIE templates.

Run with the isolated HippoRAG environment. This script never calls Ollama and
does not persist prompt text or passage IDs.
"""

import argparse
import hashlib
from importlib import metadata as importlib_metadata
import json
from pathlib import Path
import statistics

try:
    from scripts.plan_hipporag_repair import SOURCE_RUN_ID, build_plan_report, load_source_inputs
except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
    from plan_hipporag_repair import SOURCE_RUN_ID, build_plan_report, load_source_inputs

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "1438aba3fc44ff10573e5a5e1e7cc3c7f9794aff"
PROPOSED_RETRY_CAPS = {"openie_ner": 1024, "openie_triples": 3072}


def validate_upstream_pin(version, direct_url_text):
    """Require the isolated prompt library to match the recorded source pin."""
    if version != "2.0.0a5":
        raise ValueError("Installed HippoRAG version does not match the pinned package")
    try:
        direct_url = json.loads(direct_url_text)
        commit = direct_url["vcs_info"]["commit_id"]
    except (TypeError, ValueError, KeyError):
        raise ValueError("Installed HippoRAG package has no verifiable VCS commit") from None
    if commit != UPSTREAM_COMMIT:
        raise ValueError("Installed HippoRAG commit differs from the pinned prompt source")
    return commit


def summarize_prompts(rows, *, model_digest, num_ctx, output_caps):
    """Summarize rendered prompt byte lengths; deliberately do not call them tokens."""
    if set(output_caps) != {"openie_ner", "openie_triples"}:
        raise ValueError("Both frozen stage output caps are required")
    by_stage = {}
    for stage in output_caps:
        selected = sorted((row for row in rows if row["stage"] == stage),
                          key=lambda row: row["order"])
        lengths = [row["utf8_bytes"] for row in selected]
        by_stage[stage] = {
            "rendered_count": len(lengths),
            "max_rendered_prompt_utf8_bytes": max(lengths) if lengths else None,
            "median_rendered_prompt_utf8_bytes": (
                statistics.median(lengths) if lengths else None),
            "max_output_tokens": output_caps[stage],
            "prompt_sha256_set": hashlib.sha256("\n".join(
                row["prompt_sha256"] for row in selected).encode("ascii")).hexdigest(),
        }
    return {
        "schema_version": 1,
        "status": "rendered_no_model_requests",
        "preflight_status": "not_ready_for_model_calls",
        "upstream_commit": UPSTREAM_COMMIT,
        "model_digest": model_digest,
        "num_ctx": num_ctx,
        "exact_prompt_token_counts": None,
        "by_stage": by_stage,
        "not_renderable_yet": {
            "stage": "openie_triples",
            "count": None,
            "reason": "Prompts for NER repairs depend on entity outputs not yet generated.",
        },
        "blocker": (
            "UTF-8 byte lengths are diagnostics, not tokenizer counts. Exact input-token "
            "fit against num_ctx cannot be verified by this no-model-call preflight."
        ),
        "model_requests_made": 0,
    }


def render_source_prompts(manifest, expected_ids, attempts):
    """Render exact prompts for stages whose input data is already known."""
    from hipporag.prompts import PromptTemplateManager

    # Only the private in-memory target list is needed here; it is never saved.
    try:
        from scripts.hipporag_repair import plan_openie_repairs
    except ModuleNotFoundError:
        from hipporag_repair import plan_openie_repairs
    targets = plan_openie_repairs(expected_ids, attempts)["targets"]

    corpus = json.loads(Path(manifest["inputs"]["corpus_path"]).read_text(encoding="utf-8"))
    passage_by_id = {}
    try:
        from scripts.run_hipporag import canonical_key, passage_id
    except ModuleNotFoundError:
        from run_hipporag import canonical_key, passage_id
    for item in corpus:
        title, text = canonical_key(item["title"], item["text"])
        pid = item.get("id")
        if not pid:
            pid = passage_id(title, text)
        passage_by_id[pid] = title + "\n" + text

    state_files = list(Path(manifest["storage_dir"]).rglob("openie_state.json"))
    if len(state_files) != 1:
        raise ValueError("Expected exactly one source OpenIE state")
    state = json.loads(state_files[0].read_text(encoding="utf-8"))
    state_by_passage = {doc["passage"]: doc for doc in state["docs"]}
    latest = {}
    for row in attempts:
        key = (row["passage_id"], row["stage"])
        if key not in latest or row["attempt"] > latest[key]["attempt"]:
            latest[key] = row
    failed_ner_ids = {
        pid for pid in expected_ids
        if latest[(pid, "openie_ner")]["status"] not in {"valid_empty", "valid_nonempty"}
    }
    manager = PromptTemplateManager(role_mapping={
        "system": "system", "user": "user", "assistant": "assistant",
    })
    rows = []
    pending_triples = 0
    for order, target in enumerate(targets):
        pid, stage = target["passage_id"], target["stage"]
        if stage == "openie_triples" and pid in failed_ner_ids:
            pending_triples += 1
            continue
        passage = passage_by_id[pid]
        if passage not in state_by_passage:
            raise ValueError("Source passage does not match persisted OpenIE state")
        if stage == "openie_ner":
            messages = manager.render(name="ner", passage=passage)
        else:
            entities = state_by_passage[passage].get("extracted_entities", [])
            messages = manager.render(
                name="triple_extraction", passage=passage,
                named_entity_json=json.dumps({"named_entities": entities}),
            )
        serialized = json.dumps(messages, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), default=str).encode("utf-8")
        rows.append({"order": order, "stage": stage,
                     "utf8_bytes": len(serialized),
                     "prompt_sha256": hashlib.sha256(serialized).hexdigest()})

    return rows, pending_triples


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=ROOT / "results" / "raw" /
        f"hipporag2-musique-{SOURCE_RUN_ID}.manifest.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "results" / "summary" /
        "hipporag-repair-prompt-preflight.json",
    )
    args = parser.parse_args(argv)
    manifest, expected_ids, attempts, manifest_sha, corpus_sha = load_source_inputs(
        args.manifest)
    distribution = importlib_metadata.distribution("hipporag")
    upstream_commit = validate_upstream_pin(
        distribution.version, distribution.read_text("direct_url.json"))
    rows, pending = render_source_prompts(manifest, expected_ids, attempts)
    plan_report = build_plan_report(
        manifest["run_id"], expected_ids, attempts,
        manifest_sha256=manifest_sha, corpus_sha256=corpus_sha)
    report = summarize_prompts(
        rows, model_digest=manifest["generation"]["model"]["digest"],
        num_ctx=manifest["generation"]["options"]["num_ctx"],
        output_caps=PROPOSED_RETRY_CAPS,
    )
    report["output_caps_source"] = "ADR-0008 retry-cap proposal; must be frozen before execution"
    report.update({
        "source_run_id": manifest["run_id"],
        "hipporag_package_version": distribution.version,
        "installed_upstream_commit": upstream_commit,
        "source_manifest_sha256": manifest_sha,
        "source_corpus_sha256": corpus_sha,
        "plan_sha256": plan_report["plan_sha256"],
        "not_renderable_yet": {"stage": "openie_triples", "count": pending,
                                "reason": "Triple prompts depend on new NER repair outputs."},
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": report["status"],
        "preflight_status": report["preflight_status"],
        "rendered_prompts": sum(item["rendered_count"]
                                 for item in report["by_stage"].values()),
        "pending_triple_prompts": pending,
        "exact_prompt_token_counts": None,
        "model_requests_made": 0,
        "report": args.output.name,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
