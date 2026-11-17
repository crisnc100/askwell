"""The front page's carbon copy claims to show the table and column names the AI is
given for the demo database, and which columns are kept from it. That copy lives in
web/src/demo-schema.json; this keeps it equal to the registry the prompt is built from."""

from __future__ import annotations

import json
from pathlib import Path

from askwell.core.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]


def test_the_front_page_carbon_matches_the_demo_registry() -> None:
    registry = load_registry(ROOT / "registries" / "fieldservice.yaml")
    expected = [
        {
            "table": name,
            "shown": [f for f, d in entity.fields.items() if not d.hidden],
            "hidden": [f for f, d in entity.fields.items() if d.hidden],
        }
        for name, entity in registry.entities.items()
    ]
    carbon = json.loads((ROOT / "web" / "src" / "demo-schema.json").read_text(encoding="utf-8"))
    assert carbon == expected
    assert any(table["hidden"] for table in carbon)
