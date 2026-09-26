"""Freeze a candidate MuSiQue evaluation ID view after local overlap checks."""

import argparse
import hashlib
import json
from pathlib import Path


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _ordered_ids_sha256(question_ids):
    payload = json.dumps(question_ids, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return _sha256(payload)


def build_candidate_view(ids_path, results_dir, labels_path=None,
                         start=200, stop=300):
    ids_path = Path(ids_path)
    results_dir = Path(results_dir)
    source = _read_json(ids_path)
    all_ids = source.get("question_ids")
    if not isinstance(all_ids, list) or not (0 <= start < stop <= len(all_ids)):
        raise ValueError("Invalid pinned question ID list or candidate range")
    if (start < 100 or stop > 400) and source.get("dataset") == "musique":
        raise ValueError("Candidate range must avoid used prefix and reserved holdout")
    candidate = all_ids[start:stop]
    if len(candidate) != len(set(candidate)):
        raise ValueError("Candidate IDs are not unique")
    candidate_set = set(candidate)
    artifacts = []
    manifest_run_ids = set()

    for path in sorted(results_dir.glob("*.manifest.json")):
        payload = _read_json(path)
        if payload.get("dataset") != "musique":
            continue
        run_id = payload.get("run_id")
        expected = payload.get("expected_question_ids")
        if not isinstance(run_id, str) or not isinstance(expected, list):
            raise ValueError(f"MuSiQue manifest lacks run ID or expected IDs: {path.name}")
        manifest_run_ids.add(run_id)
        overlap = sorted(candidate_set.intersection(expected))
        artifacts.append({
            "run_id": run_id,
            "artifact_sha256": _sha256(path.read_bytes()),
            "status": payload.get("status"),
            "question_count": len(expected),
            "overlap_count": len(overlap),
        })
        if overlap:
            raise ValueError(f"Candidate IDs overlap a saved manifest: {run_id}")

    raw_without_manifest = []
    for path in sorted(results_dir.glob("*.jsonl")):
        if path.with_suffix(".manifest.json").is_file():
            continue
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
        if not rows or rows[0].get("dataset") != "musique":
            continue
        ids = [row.get("question_id") for row in rows]
        if any(not isinstance(item, str) for item in ids):
            raise ValueError(f"MuSiQue raw result lacks question IDs: {path.name}")
        overlap = sorted(candidate_set.intersection(ids))
        raw_without_manifest.append({
            "artifact_sha256": _sha256(path.read_bytes()),
            "status": "raw_without_manifest",
            "question_count": len(ids),
            "overlap_count": len(overlap),
        })
        if overlap:
            raise ValueError(f"Candidate IDs overlap an unmanifested raw result: {path.name}")

    labels_sha256 = _sha256(Path(labels_path).read_bytes()) if labels_path else None
    return {
        "schema_version": 1,
        "dataset": "musique",
        "view": "independent-candidate-s500-200-299",
        "status": "frozen_candidate_not_run",
        "selection": {"source": ids_path.name, "source_revision": source.get("source_revision"),
                      "start_inclusive": start, "stop_exclusive": stop,
                      "selection_semantics": "ordered slice of pinned S500 question_ids"},
        "source_ids_sha256": _sha256(ids_path.read_bytes()),
        "ordered_question_ids_sha256": _ordered_ids_sha256(candidate),
        "labels_sha256": labels_sha256,
        "question_ids": candidate,
        "disjointness_audit": {
            "manifest_count": len(artifacts),
            "manifests": artifacts,
            "raw_without_manifest_count": len(raw_without_manifest),
            "raw_without_manifests": raw_without_manifest,
            "overlap_count": 0,
            "note": "Re-run the overlap check immediately before evaluation to include later artifacts.",
        },
        "limitations": [
            "This is a frozen candidate view, not a benchmark result.",
            "The candidate is a slice within pinned S500, not representative of the full source dataset.",
            "Generation, index construction and evaluation were not run by this utility.",
        ],
    }


def verify_candidate_view(view_path, ids_path, results_dir, labels_path=None):
    """Re-check a frozen view against newer artifacts without modifying it."""
    view_path = Path(view_path)
    frozen = _read_json(view_path)
    selection = frozen.get("selection", {})
    current = build_candidate_view(
        ids_path, results_dir, labels_path=labels_path,
        start=selection.get("start_inclusive", -1),
        stop=selection.get("stop_exclusive", -1),
    )
    if (frozen.get("question_ids") != current.get("question_ids")
            or frozen.get("ordered_question_ids_sha256")
            != current.get("ordered_question_ids_sha256")
            or frozen.get("source_ids_sha256") != current.get("source_ids_sha256")
            or selection.get("source_revision")
            != current.get("selection", {}).get("source_revision")
            or frozen.get("labels_sha256") != current.get("labels_sha256")):
        raise ValueError("Frozen candidate view no longer matches its pinned source or labels")
    return {
        "verified": True,
        "questions": len(frozen["question_ids"]),
        "ordered_question_ids_sha256": frozen["ordered_question_ids_sha256"],
        "manifest_count": current["disjointness_audit"]["manifest_count"],
        "raw_without_manifest_count": current["disjointness_audit"]["raw_without_manifest_count"],
        "overlap_count": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", type=Path, default=Path("data/ids/musique_s500.json"))
    parser.add_argument("--results-dir", type=Path, default=Path("results/raw"))
    parser.add_argument("--labels", type=Path, default=Path("data/processed/musique/labels.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true",
                        help="verify an existing frozen output without modifying it")
    args = parser.parse_args(argv)
    if args.verify_only:
        report = verify_candidate_view(args.output, args.ids, args.results_dir, args.labels)
        print(json.dumps(report, ensure_ascii=False))
        return
    view = build_candidate_view(args.ids, args.results_dir, args.labels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({"status": view["status"], "questions": len(view["question_ids"]),
                      "manifests_checked": view["disjointness_audit"]["manifest_count"],
                      "unmanifested_results_checked": view["disjointness_audit"]["raw_without_manifest_count"],
                      "ordered_question_ids_sha256": view["ordered_question_ids_sha256"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
