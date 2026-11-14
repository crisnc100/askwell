"""Gold manifest: hashes of every frozen gold file, and the change rule.

    uv run python -m evals.gold.manifest --check
    uv run python -m evals.gold.manifest --update --reason "why the gold had to change"
    uv run python -m evals.gold.manifest --promote <file> --reason "why it is revealed now"

Every revision after the first needs a reason. `--update` bumps the revision, rewrites
the hashes and appends the reason to CHANGELOG.md; the manifest test fails if a gold
file's hash, the revision count or the changelog disagree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GOLD_DIR = Path(__file__).resolve().parent
MANIFEST = GOLD_DIR / "MANIFEST.json"
CHANGELOG = GOLD_DIR / "CHANGELOG.md"
GOLD_FILES = (
    "fieldservice.jsonl",
    "spider_ids.json",
    "spider_selection.py",
    "holdout-v02.jsonl",
    "spider_selection_v03.py",
    "spider_ids_v03.json",
)
REVISION_HEADING = re.compile(r"^## Revision (\d+) — (\d{4}-\d{2}-\d{2})$", re.MULTILINE)


def file_hashes(gold_dir: Path = GOLD_DIR) -> dict[str, str]:
    return {name: hashlib.sha256((gold_dir / name).read_bytes()).hexdigest() for name in GOLD_FILES}


def changelog_revisions(text: str) -> list[tuple[int, str, str]]:
    """(revision, date, reason) for every entry, in file order."""
    matches = list(REVISION_HEADING.finditer(text))
    entries: list[tuple[int, str, str]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        entries.append((int(match.group(1)), match.group(2), text[match.end() : end].strip()))
    return entries


def problems(gold_dir: Path = GOLD_DIR) -> list[str]:
    manifest: dict[str, Any] = json.loads((gold_dir / "MANIFEST.json").read_text())
    found: list[str] = []
    actual = file_hashes(gold_dir)
    for name, digest in actual.items():
        if manifest["files"].get(name) != digest:
            found.append(f"{name}: hash {digest} != manifest {manifest['files'].get(name)}")
    extra = set(manifest["files"]) - set(GOLD_FILES)
    if extra:
        found.append(f"manifest lists unknown files: {sorted(extra)}")
    entries = changelog_revisions((gold_dir / "CHANGELOG.md").read_text())
    numbers = [number for number, _, _ in entries]
    if numbers != list(range(1, manifest["revision"] + 1)):
        found.append(
            f"CHANGELOG revisions {numbers} do not run 1..{manifest['revision']} (manifest)"
        )
    for number, _, reason in entries:
        if not reason:
            found.append(f"CHANGELOG revision {number} has no reason")
    return found


def update(reason: str, gold_dir: Path = GOLD_DIR, today: str | None = None) -> int:
    if not reason.strip():
        raise ValueError("a reason is required to change the gold")
    manifest: dict[str, Any] = json.loads((gold_dir / "MANIFEST.json").read_text())
    revision = int(manifest["revision"]) + 1
    manifest["revision"] = revision
    manifest["files"] = file_hashes(gold_dir)
    (gold_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    date = today or datetime.now(UTC).strftime("%Y-%m-%d")
    with (gold_dir / "CHANGELOG.md").open("a", encoding="utf-8") as fh:
        fh.write(f"\n## Revision {revision} — {date}\n\n{reason.strip()}\n")
    return revision


def promote(name: str, reason: str, gold_dir: Path = GOLD_DIR, today: str | None = None) -> int:
    """Move a file from `pending` into the frozen files, as a new revision. Refused
    unless the file's hash equals the one committed under `pending`: that hash is the
    proof the file did not change after it was recorded."""
    manifest: dict[str, Any] = json.loads((gold_dir / "MANIFEST.json").read_text())
    pending: dict[str, str] = manifest.get("pending", {})
    if name not in pending:
        raise ValueError(f"{name} is not pending")
    actual = hashlib.sha256((gold_dir / name).read_bytes()).hexdigest()
    if actual != pending[name]:
        raise ValueError(f"{name}: hash {actual} does not match the pending {pending[name]}")
    del pending[name]
    if not pending:
        manifest.pop("pending", None)
    (gold_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return update(reason, gold_dir, today)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gold manifest check and update.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--update", action="store_true")
    mode.add_argument("--promote", metavar="FILE", help="move a pending file into the gold")
    parser.add_argument("--reason", default="")
    args = parser.parse_args(argv)
    if args.promote:
        print(f"gold revision {promote(args.promote, args.reason)}")
        return 0
    if args.update:
        print(f"gold revision {update(args.reason)}")
        return 0
    found = problems()
    for problem in found:
        print(problem, file=sys.stderr)
    if not found:
        print("gold manifest OK")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
