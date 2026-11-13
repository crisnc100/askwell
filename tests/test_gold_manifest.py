"""Gold manifest: the committed hashes match, and any change needs a changelog reason."""

from __future__ import annotations

import hashlib
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


# Gold revision 5: presentation-only edits, made before any held-out result. Each is
# (item id, text in revision 4, text now). No question, filter or join changes.
REVISION_5 = [
    (
        "ho-001",
        "ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'cancelled') / COUNT(*), 2)",
        "100.0 * COUNT(*) FILTER (WHERE status = 'cancelled') / COUNT(*)",
    ),
    (
        "ho-002",
        "ROUND(100.0 * SUM(amount) FILTER (WHERE status = 'overdue') / SUM(amount), 2)",
        "100.0 * SUM(amount) FILTER (WHERE status = 'overdue') / SUM(amount)",
    ),
    (
        "ho-003",
        "ROUND(100.0 * COUNT(*) FILTER (WHERE priority = 'urgent') / COUNT(*), 2) AS pct_urgent",
        "1.0 * COUNT(*) FILTER (WHERE priority = 'urgent') / COUNT(*) AS share_urgent",
    ),
    (
        "ho-004",
        "ROUND(100.0 * COUNT(*) FILTER (WHERE w.job_type = 'repair') / COUNT(*), 2)",
        "100.0 * COUNT(*) FILTER (WHERE w.job_type = 'repair') / COUNT(*)",
    ),
    (
        "ho-005",
        "ROUND(100.0 * COUNT(*) FILTER (WHERE paid_at <= due_at) / COUNT(*), 2)",
        "100.0 * COUNT(*) FILTER (WHERE paid_at <= due_at) / COUNT(*)",
    ),
    (
        "ho-006",
        "ROUND(100.0 * COUNT(*) FILTER (WHERE segment = 'commercial') / COUNT(*), 2)",
        "100.0 * COUNT(*) FILTER (WHERE segment = 'commercial') / COUNT(*)",
    ),
    ("ho-007", "to_char(m.month, 'YYYY-MM')", "date_trunc('month', m.month)::date"),
    ("ho-008", "to_char(m.month, 'YYYY-MM')", "date_trunc('month', m.month)::date"),
    ("ho-009", "to_char(q.quarter, 'YYYY-\"Q\"Q')", "date_trunc('quarter', q.quarter)::date"),
    ("ho-010", "to_char(m.month, 'YYYY-MM')", "date_trunc('month', m.month)::date"),
    (
        "ho-011",
        "ROUND(AVG(EXTRACT(EPOCH FROM completed_at - opened_at) / 86400)::numeric, 2)",
        "AVG(EXTRACT(EPOCH FROM completed_at - opened_at) / 86400)",
    ),
    ("ho-012", "ROUND(AVG(i.paid_at - i.issued_at), 2)", "AVG(i.paid_at - i.issued_at)"),
    (
        "ho-019",
        "ROUND((EXTRACT(EPOCH FROM timestamp '2026-06-30 00:00:00' - opened_at) / 86400)"
        "::numeric, 1)",
        "EXTRACT(EPOCH FROM timestamp '2026-06-30 00:00:00' - opened_at) / 86400",
    ),
    (
        "ho-027",
        "to_char(date_trunc('month', created_at), 'YYYY-MM')",
        "date_trunc('month', created_at)::date",
    ),
]


# The committed revision 5 file, byte for byte. Any change to it, even whitespace or
# key order, needs a new revision and a new hash here.
REVISION_5_HASH = "7792130d82402cebf7e38dafd5352190afcf04b68c5772460486a40a5d5dc8b2"


def _as_revision_4(raw: str) -> str:
    """Undo the revision 5 edits on the raw text, each exactly once in its own item's
    line. The JSON is never re-serialised, so no other byte can change unnoticed."""
    edits: dict[str, list[tuple[str, str]]] = {}
    for item_id, before, after in REVISION_5:
        edits.setdefault(item_id, []).append((before, after))
    lines = []
    for line in raw.split("\n"):
        if line:
            for before, after in edits.get(json.loads(line)["id"], []):
                encoded_after = json.dumps(after, ensure_ascii=False)[1:-1]
                encoded_before = json.dumps(before, ensure_ascii=False)[1:-1]
                assert line.count(encoded_after) == 1, line[:20]
                line = line.replace(encoded_after, encoded_before)
        lines.append(line)
    return "\n".join(lines)


def test_the_committed_holdout_is_revision_5_byte_for_byte() -> None:
    manifest = json.loads((GOLD_DIR / "MANIFEST.json").read_text())
    assert "holdout-v02.jsonl" not in manifest.get("pending", {})
    assert "holdout-v02.jsonl" in manifest["files"]
    raw = (GOLD_DIR / "holdout-v02.jsonl").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == REVISION_5_HASH


def test_undoing_the_revision_5_edits_gives_the_hash_committed_before_the_code() -> None:
    """Revision 5 is the file hashed before any v0.2 code plus only the listed
    presentation edits: undoing them on the raw text gives the pending hash back."""
    raw = (GOLD_DIR / "holdout-v02.jsonl").read_bytes().decode("utf-8")
    assert hashlib.sha256(raw.encode()).hexdigest() != HOLDOUT_HASH
    assert hashlib.sha256(_as_revision_4(raw).encode()).hexdigest() == HOLDOUT_HASH


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
