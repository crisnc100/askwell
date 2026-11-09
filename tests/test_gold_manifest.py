"""Gold manifest: the committed hashes match, and any change needs a changelog reason."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from evals.gold.manifest import GOLD_DIR, GOLD_FILES, problems, update


def test_committed_gold_matches_manifest() -> None:
    assert problems() == []


@pytest.fixture
def gold_copy(tmp_path: Path) -> Path:
    for name in (*GOLD_FILES, "MANIFEST.json", "CHANGELOG.md"):
        shutil.copy(GOLD_DIR / name, tmp_path / name)
    assert problems(tmp_path) == []
    return tmp_path


def test_an_edited_gold_file_is_detected(gold_copy: Path) -> None:
    path = gold_copy / "fieldservice.jsonl"
    path.write_text(path.read_text().replace("last month", "last week", 1))
    found = problems(gold_copy)
    assert len(found) == 1
    assert found[0].startswith("fieldservice.jsonl: hash")


def test_an_edited_selection_rule_is_detected(gold_copy: Path) -> None:
    path = gold_copy / "spider_selection.py"
    path.write_text(path.read_text().replace("SEED = 20261109", "SEED = 1"))
    assert any(p.startswith("spider_selection.py") for p in problems(gold_copy))


def test_changing_gold_needs_a_reason(gold_copy: Path) -> None:
    (gold_copy / "fieldservice.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="reason"):
        update("  ", gold_copy)
    assert problems(gold_copy)


def test_update_with_reason_bumps_revision_and_logs_it(gold_copy: Path) -> None:
    (gold_copy / "fieldservice.jsonl").write_text("{}\n")
    assert update("fs-007 gold used the wrong status", gold_copy, today="2026-12-01") == 2
    assert problems(gold_copy) == []
    changelog = (gold_copy / "CHANGELOG.md").read_text()
    assert "## Revision 2 — 2026-12-01\n\nfs-007 gold used the wrong status" in changelog


def test_manifest_bump_without_changelog_entry_is_detected(gold_copy: Path) -> None:
    update("a reason", gold_copy, today="2026-12-01")
    changelog = gold_copy / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().split("\n## Revision 2")[0] + "\n")
    assert any("CHANGELOG revisions [1]" in p for p in problems(gold_copy))


def test_changelog_entry_without_reason_is_detected(gold_copy: Path) -> None:
    update("a reason", gold_copy, today="2026-12-01")
    changelog = gold_copy / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().replace("a reason", ""))
    assert any("has no reason" in p for p in problems(gold_copy))
