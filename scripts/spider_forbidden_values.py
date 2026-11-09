"""Write evals/spider_forbidden_values.json: SHA-256 hashes of the values in every Spider
categorical column (lowercased), so a test can prove committed files quote none of them
without CI needing the Spider data.

    uv run python -m scripts.spider_forbidden_values

Values shorter than 3 characters and plain numbers are left out: "1" or "0" appear in any
text and say nothing about the data.
"""

from __future__ import annotations

import hashlib
import json

import yaml

from ledgerline.bench.items import ROOT, spider_databases
from ledgerline.bench.spider import generate

OUT = ROOT / "evals" / "spider_forbidden_values.json"


def values() -> set[str]:
    found: set[str] = set()
    for db_id in spider_databases():
        registry = yaml.safe_load(generate(db_id))
        for entity in registry["entities"].values():
            for field in entity["fields"].values():
                for value in field.get("allowed_values") or []:
                    text = " ".join(str(value).lower().split())
                    if len(text) >= 3 and not text.replace(".", "", 1).isdigit():
                        found.add(text)
    return found


def main() -> int:
    hashes = sorted(hashlib.sha256(v.encode()).hexdigest() for v in values())
    OUT.write_text(json.dumps({"count": len(hashes), "sha256": hashes}, indent=1) + "\n")
    print(f"wrote {len(hashes)} hashes to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
