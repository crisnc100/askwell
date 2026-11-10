"""Write evals/spider_forbidden_values.json: SHA-256 hashes of the values in every Spider
categorical column, normalised by ledgerline.bench.privacy, so a test can prove committed
files quote none of them without CI needing the Spider data.

    uv run python -m scripts.spider_forbidden_values

Values shorter than 3 characters and plain numbers are left out: "1" or "0" appear in any
text and say nothing about the data. `max_words` records the longest value, in words, so the
scan knows how long a phrase to look for.
"""

from __future__ import annotations

import json

import yaml

from ledgerline.bench.items import ROOT, spider_databases
from ledgerline.bench.privacy import digest, is_checkable, normalise
from ledgerline.bench.spider import generate

OUT = ROOT / "evals" / "spider_forbidden_values.json"


def values() -> set[str]:
    found: set[str] = set()
    for db_id in spider_databases():
        registry = yaml.safe_load(generate(db_id))
        for entity in registry["entities"].values():
            for field in entity["fields"].values():
                for value in field.get("allowed_values") or []:
                    if is_checkable(str(value)):
                        found.add(normalise(str(value)))
    return found


def main() -> int:
    found = values()
    hashes = sorted(digest(v) for v in found)
    longest = max((len(v.split()) for v in found), default=1)
    OUT.write_text(
        json.dumps({"count": len(hashes), "max_words": longest, "sha256": hashes}, indent=1) + "\n"
    )
    print(f"wrote {len(hashes)} hashes (longest value {longest} words) to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
