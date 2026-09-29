"""One offline check entry point for a clean checkout, CI and pre-commit."""

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    commands = [
        [sys.executable, "-m", "pip", "check"],
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "scripts",
            "data",
            "tests",
            ".codex/hooks",
        ],
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "--exclude",
            "scripts/resume_dense.py",
            "--exclude",
            "scripts/vendor/hipporag2_musique_template.py",
            "scripts",
            "data",
            "tests",
            ".codex/hooks",
        ],
        [sys.executable, "-m", "pytest", "-q", "tests"],
    ]
    for command in commands:
        print("+ " + " ".join(command[1:]), flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
