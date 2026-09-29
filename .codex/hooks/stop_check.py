"""Run the shared offline check once when a Codex turn finishes."""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def main():
    event = json.load(sys.stdin)
    if event.get("stop_hook_active"):
        return 0
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "precommit_check.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        print(
            "Offline check failed. Run .venv-check Python -m scripts.check and fix it.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
