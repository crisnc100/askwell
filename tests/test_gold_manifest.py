"""Gold manifest: the committed hashes match, and any change needs a changelog reason."""

from __future__ import annotations

import json
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


def _revision(gold_dir: Path) -> int:
    return int(json.loads((gold_dir / "MANIFEST.json").read_text())["revision"])


def test_update_with_reason_bumps_revision_and_logs_it(gold_copy: Path) -> None:
    before = _revision(gold_copy)
    (gold_copy / "fieldservice.jsonl").write_text("{}\n")
    assert update("fs-007 gold used the wrong status", gold_copy, today="2026-12-01") == before + 1
    assert problems(gold_copy) == []
    changelog = (gold_copy / "CHANGELOG.md").read_text()
    assert (
        f"## Revision {before + 1} — 2026-12-01\n\nfs-007 gold used the wrong status" in changelog
    )


def test_manifest_bump_without_changelog_entry_is_detected(gold_copy: Path) -> None:
    before = _revision(gold_copy)
    update("a reason", gold_copy, today="2026-12-01")
    changelog = gold_copy / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().split(f"\n## Revision {before + 1}")[0] + "\n")
    expected = list(range(1, before + 1))
    assert any(f"CHANGELOG revisions {expected}" in p for p in problems(gold_copy))


def test_changelog_entry_without_reason_is_detected(gold_copy: Path) -> None:
    update("a reason", gold_copy, today="2026-12-01")
    changelog = gold_copy / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().replace("a reason", ""))
    assert any("has no reason" in p for p in problems(gold_copy))


# --- the v0.2 held-out set ---

# Committed under `pending` in f2e6191, before any v0.2 code (G1).
HOLDOUT_HASH = "09451c630ca1036df761ec9ee08c5357198c4b13308aa1ab0d9128ddb75d4448"


def test_the_revealed_holdout_matches_the_hash_committed_before_the_code() -> None:
    manifest = json.loads((GOLD_DIR / "MANIFEST.json").read_text())
    assert manifest["files"]["holdout-v02.jsonl"] == HOLDOUT_HASH
    assert "pending" not in manifest


def test_a_pending_file_is_promoted_only_if_its_hash_matches(tmp_path: Path) -> None:
    from evals.gold.manifest import promote

    for name in (*GOLD_FILES, "MANIFEST.json", "CHANGELOG.md"):
        shutil.copy(GOLD_DIR / name, tmp_path / name)
    manifest = json.loads((tmp_path / "MANIFEST.json").read_text())
    real = manifest["files"].pop("holdout-v02.jsonl")
    manifest["pending"] = {"holdout-v02.jsonl": real}
    (tmp_path / "MANIFEST.json").write_text(json.dumps(manifest))
    tampered = tmp_path / "holdout-v02.jsonl"
    original = tampered.read_text()
    tampered.write_text(original.replace("ho-001", "ho-901", 1))
    with pytest.raises(ValueError, match="does not match"):
        promote("holdout-v02.jsonl", "reveal", tmp_path, today="2026-12-01")
    tampered.write_text(original)
    promote("holdout-v02.jsonl", "reveal", tmp_path, today="2026-12-01")
    after = json.loads((tmp_path / "MANIFEST.json").read_text())
    assert after["files"]["holdout-v02.jsonl"] == real
    assert "pending" not in after
    assert problems(tmp_path) == []
