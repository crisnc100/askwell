"""Docs the acceptance criteria require."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_rerecord_guide_covers_the_whole_loop() -> None:
    text = (ROOT / "docs" / "rerecord.md").read_text()
    for command in (
        "--mode export",
        "--mode import",
        "--mode replay",
        "scripts.check_replay_report --write",
        "evals.replay_cases export",
        "ledgerline replay import",
    ):
        assert command in text, command
