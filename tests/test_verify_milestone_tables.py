"""Cross-platform Markdown comparison in the milestone replay command."""

import shutil
import sys
from pathlib import Path

import pytest

from scripts import verify_milestone_tables

PUBLISHED = Path(__file__).resolve().parents[1] / "results" / "summary"


@pytest.mark.parametrize("changed", ["e1/e1-indexing.md", "oracle.md"])
def test_milestone_replay_accepts_crlf_and_rejects_changed_markdown(
    tmp_path, monkeypatch, changed
):
    for source, target in (
        ("e1-indexing.json", "e1/e1-indexing.json"),
        ("e3.json", "e3.json"),
        ("oracle.json", "oracle.json"),
        ("e4-cost.json", "e4-cost.json"),
        ("dense-error-signal.json", "e5.json"),
        ("e4-cost.csv", "e4-cost.csv"),
        ("e1-indexing.md", "e1/e1-indexing.md"),
        ("oracle.md", "oracle.md"),
    ):
        destination = tmp_path / target
        destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(PUBLISHED / source, destination)
        if destination.suffix == ".md":
            text = destination.read_text(encoding="utf-8")
            destination.write_text(text, encoding="utf-8", newline="\r\n")

    monkeypatch.setattr(
        sys, "argv", ["verify_milestone_tables", "--replay-dir", str(tmp_path)]
    )
    verify_milestone_tables.main()

    modified = tmp_path / changed
    text = modified.read_text(encoding="utf-8")
    modified.write_text("Changed heading\n" + text, encoding="utf-8", newline="\r\n")
    with pytest.raises(ValueError, match=f"Rebuilt table differs: {modified.name}"):
        verify_milestone_tables.main()
