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


def test_verify_sh_gives_the_same_chromium_install_command_as_the_readme() -> None:
    command = "(cd web && npm ci && npx playwright install chromium)"
    assert command in (ROOT / "README.md").read_text()
    assert command in (ROOT / "verify.sh").read_text()
