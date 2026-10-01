"""Use the repository's isolated check environment from a Git hook."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    candidates = (
        ROOT / ".venv-check" / "Scripts" / "python.exe",
        ROOT / ".venv-check" / "bin" / "python",
    )
    python = next((path for path in candidates if path.is_file()), None)
    if python is None:
        print(
            "Run uv sync --locked with UV_PROJECT_ENVIRONMENT=.venv-check first.",
            file=sys.stderr,
        )
        return 1
    return subprocess.run(
        [str(python), "-m", "scripts.check"], cwd=ROOT, check=False
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
