"""Create a compact, no-model-call plan for a bounded HippoRAG OpenIE repair."""

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts.hipporag_repair import plan_openie_repairs
    from scripts.run_hipporag import canonical_key, passage_id, sha256_file
except ModuleNotFoundError:  # Direct script execution puts scripts/ on sys.path.
    from hipporag_repair import plan_openie_repairs
    from run_hipporag import canonical_key, passage_id, sha256_file

ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN_ID = "e78eff08-532a-40b3-a359-49a6b08b32a7"


def build_plan_report(run_id, expected_passage_ids, attempts, *,
                      manifest_sha256, corpus_sha256):
    """Summarize exact scheduled stage work without persisting passage IDs."""
    plan = plan_openie_repairs(expected_passage_ids, attempts)
    targets_bytes = json.dumps(
        plan["targets"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "source_run_id": run_id,
        "source_manifest_sha256": manifest_sha256,
        "source_corpus_sha256": corpus_sha256,
        "plan_sha256": hashlib.sha256(targets_bytes).hexdigest(),
        "status": "planned_no_model_requests",
        "preflight_status": "not_ready_for_model_calls",
        "plan": plan["summary"],
        "interpretation": [
            "Counts are the exact first scheduled repair pass, not an upper bound on future retries.",
            "NER repairs are scheduled before triple extraction and dependent triple refreshes.",
            "This report contains no passage IDs, text, prompts, responses, local paths, or secrets.",
        ],
    }


def load_source_inputs(manifest_path):
    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_id = manifest.get("run_id")
    if (not run_id or not manifest_path.name.endswith(f"{run_id}.manifest.json")
            or run_id != SOURCE_RUN_ID):
        raise ValueError("Manifest filename or run_id does not match the approved diagnostic source")
    corpus_path = Path(manifest["inputs"]["corpus_path"])
    corpus_sha256 = manifest["inputs"]["corpus_sha256"]
    if not corpus_path.is_file() or sha256_file(corpus_path) != corpus_sha256:
        raise ValueError("Source corpus is missing or differs from the source manifest")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    expected_ids = []
    seen_content = set()
    for item in corpus:
        title, text = canonical_key(item["title"], item["text"])
        if (title, text) in seen_content:
            continue
        seen_content.add((title, text))
        pid = item.get("id") or passage_id(title, text)
        if not isinstance(pid, str) or not pid:
            raise ValueError("Source corpus contains an invalid passage ID")
        expected_ids.append(pid)
    expected_count = manifest.get("index", {}).get(
        "openie_acceptance_gate", {}).get("expected_passages")
    if len(expected_ids) != expected_count:
        raise ValueError("Source corpus passage count differs from the failed index gate")
    attempts = manifest.get("index", {}).get("openie_attempts")
    if not isinstance(attempts, list):
        raise ValueError("Source manifest has no OpenIE attempt ledger")
    return (manifest, expected_ids, attempts, sha256_file(manifest_path), corpus_sha256)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path,
        default=ROOT / "results" / "raw" /
        f"hipporag2-musique-{SOURCE_RUN_ID}.manifest.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "results" / "summary" / "hipporag-repair-plan.json",
    )
    args = parser.parse_args(argv)
    manifest, expected_ids, attempts, manifest_hash, corpus_hash = load_source_inputs(
        args.manifest)
    report = build_plan_report(
        manifest["run_id"], expected_ids, attempts,
        manifest_sha256=manifest_hash, corpus_sha256=corpus_hash)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({
        "status": report["status"],
        "preflight_status": report["preflight_status"],
        "source_run_id": report["source_run_id"],
        **report["plan"],
        "plan_sha256": report["plan_sha256"],
        "report": args.output.name,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
