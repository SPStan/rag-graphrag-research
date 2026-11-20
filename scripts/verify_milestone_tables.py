"""Compare offline replays with the published E1–E5 tables."""

import argparse
import csv
from pathlib import Path

from scripts import run_dense as dense

ROOT = Path(__file__).resolve().parents[1]


def require_equal(actual, expected, label):
    if actual != expected:
        raise ValueError(f"Rebuilt table differs: {label}")


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.reader(stream, strict=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", type=Path, required=True)
    replay = parser.parse_args().replay_dir
    published = ROOT / "results/summary"

    for name, path, keys in (
        (
            "e1-indexing",
            "e1/e1-indexing",
            (
                "batch_id",
                "plan_sha256",
                "physical_known_tokens",
                "cost_complete",
                "budget_charge_upper_bound",
            ),
        ),
        ("e3", "e3", ("datasets", "question_scores_sha256")),
        ("oracle", "oracle", ("datasets", "private_ledger_sha256")),
        ("e4-cost", "e4-cost", ("configurations", "projections")),
        ("dense-error-signal", "e5", ("analytical_digest", "private_csv_sha256")),
    ):
        original = dense.read_json(published / f"{name}.json")
        rebuilt = dense.read_json(replay / f"{path}.json")
        for key in keys:
            require_equal(rebuilt[key], original[key], f"{name}.{key}")

    for folder, name in (
        (replay / "e1", "e1-indexing.md"),
        (replay, "oracle.md"),
    ):
        require_equal(
            (folder / name).read_bytes(),
            (published / name).read_bytes(),
            name,
        )

    require_equal(
        read_csv(replay / "e4-cost.csv"),
        read_csv(published / "e4-cost.csv"),
        "e4-cost.csv",
    )

    # E3's loader recomputes E2 rows and checks their usage against journals.
    # Tie those exact E2 inputs to the public files in this checkout.
    e3 = dense.read_json(replay / "e3.json")
    for dataset in ("musique", "hotpotqa"):
        name = f"e2-{dataset}-s500.json"
        checksums = [
            sha
            for path, sha in e3["inputs"][dataset]["files"].items()
            if Path(path).name == name
        ]
        require_equal(checksums, [dense.sha256_file(published / name)], name)
    print("E1–E5 tables and oracle agree with the published results.")


if __name__ == "__main__":
    main()
