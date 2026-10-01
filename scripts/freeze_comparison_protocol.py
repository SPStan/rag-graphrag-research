"""Verify pinned S500 views and audit local question-ID usage without model calls."""

import argparse
import hashlib
import json
from pathlib import Path


DATASETS = ("musique", "hotpotqa")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha256(path):
    """Hash text with normalized line endings across Windows and Linux."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def referenced_run_ids(value):
    """Find provenance references, which are not proof of execution."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("run_id") and isinstance(item, str):
                found.add(item)
            else:
                found.update(referenced_run_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(referenced_run_ids(item))
    return found


def make_split(source, source_sha256):
    ids = source["question_ids"]
    views = source["views"]
    if source.get("dataset") not in DATASETS:
        raise ValueError("Unsupported dataset")
    if not isinstance(ids, list) or any(
        not isinstance(qid, str) or not qid for qid in ids
    ):
        raise ValueError("Question IDs must be non-empty strings")
    if source["seed"] != 42 or len(ids) != 500 or len(set(ids)) != 500:
        raise ValueError("S500 must contain 500 unique IDs with seed 42")
    if views["pilot200"] != ids[:200] or views["holdout100"] != ids[400:]:
        raise ValueError("Existing pilot200 or holdout100 differs from S500")
    # The old holdout at 400:500 has a documented gold-answer exposure.
    tuning, check, reserved = ids[:300], ids[300:400], ids[400:]
    if (
        set(tuning) & set(check)
        or set(tuning) & set(reserved)
        or set(check) & set(reserved)
    ):
        raise ValueError("Signal groups overlap")
    if set(tuning) | set(check) | set(reserved) != set(ids):
        raise ValueError("Signal groups do not cover S500")
    return {
        "schema_version": 1,
        "dataset": source["dataset"],
        "source": f"{source['dataset']}_s500.json",
        "source_sha256": source_sha256,
        "source_revision": source["source_revision"],
        "seed": source["seed"],
        "selection": "ordered S500 slices; no reshuffle",
        "pilot200_ids": views["pilot200"],
        "signal_tuning_ids": tuning,
        "signal_check_ids": check,
        "legacy_holdout_reserved_ids": reserved,
    }


def audit_usage(id_sources, raw_dir, summary_dir):
    """Store only ID positions, run IDs and hashes, never question/answer text."""
    if not raw_dir.is_dir() or not summary_dir.is_dir():
        raise ValueError("Audit requires existing raw and summary directories")
    positions = {
        dataset: {qid: i for i, qid in enumerate(source["question_ids"])}
        for dataset, source in id_sources.items()
    }
    runs = {}
    observed_files = set()
    for path in sorted(raw_dir.glob("*.manifest.json")):
        row = read_json(path)
        dataset = row.get("dataset")
        if dataset not in positions:
            continue
        run_id = row.get("run_id")
        expected = row.get("expected_question_ids")
        if not isinstance(run_id, str) or not isinstance(expected, list):
            raise ValueError(f"Invalid manifest metadata: {path.name}")
        if any(not isinstance(qid, str) or not qid for qid in expected):
            raise ValueError(f"Invalid planned ID: {path.name}")
        if len(expected) != len(set(expected)):
            raise ValueError(f"Duplicate planned question ID: {path.name}")
        key = (dataset, run_id)
        if key in runs:
            raise ValueError(f"Duplicate manifest run ID: {run_id}")
        runs[key] = {
            "dataset": dataset,
            "run_id": run_id,
            "planned_positions": sorted(
                {
                    positions[dataset][qid]
                    for qid in expected
                    if qid in positions[dataset]
                }
            ),
            "planned_outside_s500": sum(
                qid not in positions[dataset] for qid in expected
            ),
            "observed_positions": [],
            "observed_outside_s500": 0,
            "manifest": path.name,
            "manifest_sha256": sha256(path),
        }
    for path in sorted(raw_dir.glob("*.jsonl")):
        by_run = {}
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                row = json.loads(line)
                dataset, run_id, qid = (
                    row.get("dataset"),
                    row.get("run_id"),
                    row.get("question_id"),
                )
                if dataset not in positions:
                    continue
                if not isinstance(run_id, str) or not isinstance(qid, str):
                    raise ValueError(f"Invalid observed ID metadata: {path.name}")
                by_run.setdefault((dataset, run_id), []).append(qid)
        for key, ids in by_run.items():
            if key in observed_files:
                raise ValueError(f"Multiple result files for run ID: {key[1]}")
            observed_files.add(key)
            dataset, run_id = key
            entry = runs.setdefault(
                key,
                {
                    "dataset": dataset,
                    "run_id": run_id,
                    "planned_positions": [],
                    "planned_outside_s500": 0,
                    "observed_positions": [],
                    "observed_outside_s500": 0,
                    "manifest": None,
                    "manifest_sha256": None,
                },
            )
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate observed question ID: {run_id}")
            entry["observed_positions"] = sorted(
                positions[dataset][qid] for qid in ids if qid in positions[dataset]
            )
            entry["observed_outside_s500"] = sum(
                qid not in positions[dataset] for qid in ids
            )
            entry["results"] = path.name
            entry["results_sha256"] = sha256(path)
    summaries = []
    for path in sorted(summary_dir.glob("*.json")):
        if path.name == "question-usage-audit.json":
            continue
        row = read_json(path)
        if not isinstance(row, dict):
            continue
        # Summaries are provenance, not proof of execution for individual IDs.
        summaries.append(
            {
                "file": path.name,
                "sha256": sha256(path),
                "referenced_run_ids": sorted(referenced_run_ids(row)),
            }
        )
    observed = {dataset: set() for dataset in DATASETS}
    planned = {dataset: set() for dataset in DATASETS}
    for entry in runs.values():
        positions_in_run = entry["observed_positions"] or entry["planned_positions"]
        if not entry["observed_positions"]:
            entry["known_purpose"] = "planned_only"
        elif positions_in_run and max(positions_in_run) < 10:
            entry["known_purpose"] = "debug_prefix"
        elif positions_in_run and max(positions_in_run) < 100:
            entry["known_purpose"] = "baseline100_includes_debug"
        elif (
            positions_in_run
            and min(positions_in_run) >= 200
            and max(positions_in_run) < 300
        ):
            entry["known_purpose"] = "candidate100_diagnostic"
        else:
            entry["known_purpose"] = "other_or_partial"
        observed[entry["dataset"]].update(entry["observed_positions"])
        planned[entry["dataset"]].update(entry["planned_positions"])
    documented_exposures = []
    docs_dir = summary_dir.parent.parent / "docs"
    for path in sorted(docs_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        for dataset in DATASETS:
            for position in range(300, 500):
                qid = id_sources[dataset]["question_ids"][position]
                if qid in content:
                    kind = "exact_id_in_document"
                    if (
                        dataset == "musique"
                        and position == 482
                        and path.name == "DATA.md"
                    ):
                        kind = "manual_example_with_gold_in_DATA.md"
                    documented_exposures.append(
                        {
                            "dataset": dataset,
                            "position": position,
                            "run_id": None,
                            "kind": kind,
                            "source": f"docs/{path.name}",
                            "source_text_sha256": text_sha256(path),
                        }
                    )
    return {
        "schema_version": 1,
        "meaning": "Positions are zero-based indexes into pinned S500; planned and observed are separate. Missing local records do not prove non-use.",
        "sources": {dataset: f"data/ids/{dataset}_s500.json" for dataset in DATASETS},
        "runs": sorted(
            runs.values(), key=lambda item: (item["dataset"], item["run_id"])
        ),
        "published_summaries": summaries,
        "documented_non_run_exposures": documented_exposures,
        "totals": {
            dataset: {
                "observed_s500": len(observed[dataset]),
                "planned_s500": len(planned[dataset]),
                "signal_check_observed": len(observed[dataset] & set(range(300, 400))),
                "signal_check_planned": len(planned[dataset] & set(range(300, 400))),
            }
            for dataset in DATASETS
        },
    }


def render_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def freeze(
    ids_dir,
    raw_dir,
    summary_dir,
    verify_only=False,
    splits_only=False,
    refresh_audit=False,
):
    if splits_only and not verify_only:
        raise ValueError("Splits-only mode is read-only")
    if refresh_audit and (verify_only or splits_only):
        raise ValueError(
            "Audit refresh cannot be combined with verification or splits-only"
        )
    sources = {}
    splits = {}
    for dataset in DATASETS:
        source_path = ids_dir / f"{dataset}_s500.json"
        sources[dataset] = read_json(source_path)
        if sources[dataset].get("dataset") != dataset:
            raise ValueError(f"Dataset does not match file: {source_path.name}")
        splits[dataset] = make_split(sources[dataset], sha256(source_path))
    outputs = {
        ids_dir / f"{dataset}_comparison_split.json": split
        for dataset, split in splits.items()
    }
    audit = None
    if not splits_only:
        audit = audit_usage(sources, raw_dir, summary_dir)
        if not audit["runs"]:
            raise ValueError(
                "No local run metadata found; cannot freeze an empty history"
            )
        audit["source_sha256"] = {
            dataset: sha256(ids_dir / f"{dataset}_s500.json") for dataset in DATASETS
        }
        if any(
            item["signal_check_observed"] or item["signal_check_planned"]
            for item in audit["totals"].values()
        ):
            raise ValueError("Signal check IDs occur in local planned/observed runs")
        if any(
            300 <= item["position"] < 400
            for item in audit["documented_non_run_exposures"]
        ):
            raise ValueError("Signal check IDs occur in tracked docs")
        outputs[summary_dir / "question-usage-audit.json"] = audit
    # Validate every destination before writing any file. Existing splits are immutable.
    for path, value in outputs.items():
        expected = render_json(value)
        if verify_only:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                raise ValueError(f"Frozen file differs: {path.name}")
        elif path.is_file() and path.read_text(encoding="utf-8") != expected:
            if not (refresh_audit and path.name == "question-usage-audit.json"):
                raise ValueError(f"Refusing to overwrite frozen file: {path.name}")
    if not verify_only:
        for path, value in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_json(value), encoding="utf-8", newline="\n")
    return audit["totals"] if audit is not None else "S500 splits verified"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids-dir", type=Path, default=Path("data/ids"))
    parser.add_argument("--raw-dir", type=Path, default=Path("results/raw"))
    parser.add_argument("--summary-dir", type=Path, default=Path("results/summary"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--verify-only", action="store_true", help="Default: read-only verification"
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="Create missing files; never replace different frozen files",
    )
    mode.add_argument(
        "--refresh-audit",
        action="store_true",
        help="Explicitly update audit, preserving frozen splits",
    )
    parser.add_argument("--splits-only", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            freeze(
                args.ids_dir,
                args.raw_dir,
                args.summary_dir,
                not (args.write or args.refresh_audit),
                args.splits_only,
                args.refresh_audit,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
