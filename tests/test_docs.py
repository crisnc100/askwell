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


def test_readme_walkthrough_fits_in_600_words_above_the_first_deep_dive() -> None:
    text = (ROOT / "README.md").read_text()
    above = text[: text.index("\n## Setup details\n")]
    for heading in ("## Try it", "## Results", "## Read more"):
        assert f"\n{heading}\n" in above, heading
    assert len(above.split()) <= 600


def test_product_brief_covers_each_part() -> None:
    text = (ROOT / "docs" / "product-brief.md").read_text()
    for heading in (
        "## The problem",
        "## Who it is for",
        "## What it does",
        "## What it deliberately does not do",
        "## How it is measured",
    ):
        assert heading in text, heading


def test_each_failure_names_the_question_what_happened_why_category_and_fix() -> None:
    pages = sorted((ROOT / "docs" / "failures").glob("fs-*.md"))
    assert len(pages) >= 3
    index = (ROOT / "docs" / "failures" / "README.md").read_text()
    for page in pages:
        text = page.read_text()
        assert page.name in index, page.name
        for part in (
            "**Question.**",
            "**What Ledgerline did.**",
            "**Category.**",
            "**What would fix it.**",
        ):
            assert part in text, (page.name, part)
        assert "**Why it" in text, page.name


def test_every_adr_has_a_result_and_none_is_left_pending() -> None:
    adrs = sorted((ROOT / "docs" / "adr").glob("ADR-*.md"))
    assert len(adrs) == 6
    for adr in adrs:
        text = adr.read_text()
        result = text[text.index("\n## Result\n") :]
        assert "PENDING" not in result, adr.name
        assert "## Prediction" in text, adr.name
