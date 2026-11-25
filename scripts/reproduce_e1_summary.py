"""Rebuild the terminal E1 summary in a separate output directory."""

import argparse
from pathlib import Path
from unittest.mock import patch

from scripts import run_dense as dense, run_e1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    plan_path = (root / args.plan).resolve()
    output = args.output_dir.resolve()
    if output.is_relative_to(root):
        parser.error("Use a new output directory outside the E1 artifact root.")

    with (
        patch.object(run_e1, "ROOT", root),
        patch("socket.socket.connect", side_effect=RuntimeError("HTTP forbidden")),
        patch("socket.socket.connect_ex", side_effect=RuntimeError("HTTP forbidden")),
        patch("sys.argv", ["run_e1", "verify", "--plan", str(plan_path)]),
    ):
        run_e1.main()
        plan = dense.read_json(plan_path)
        output.mkdir(parents=True, exist_ok=False)
        run_e1.export(plan, plan_path, report_dir=output)


if __name__ == "__main__":
    main()
