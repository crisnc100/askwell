"""The fieldservice gold set: P1.5 counts, item shape, and every in_schema gold executes
non-empty and deterministic on the seeded Postgres (as the read-only role)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, text

from askwell.gold import GOLD_DIR, GoldItem, load_gold

GOLD = load_gold(GOLD_DIR / "fieldservice.jsonl")
IN_SCHEMA = [item for item in GOLD if item.category == "in_schema"]


def test_counts_meet_p1_5() -> None:
    categories = Counter(item.category for item in GOLD)
    assert len(GOLD) >= 60
    assert categories["in_schema"] >= 35
    assert categories["out_of_schema"] >= 12
    assert categories["should_refuse"] >= 10
    difficulty = Counter(item.difficulty for item in IN_SCHEMA)
    assert difficulty["hard"] >= 10
    assert difficulty["medium"] >= 1
    assert difficulty["easy"] >= 1


def test_every_feature_is_exercised() -> None:
    used = {feature for item in IN_SCHEMA for feature in item.features}
    assert used == {"join", "group", "having", "date", "distinct", "order_limit"}


def test_ids_are_sequential() -> None:
    assert [item.id for item in GOLD] == [f"fs-{n:03d}" for n in range(1, len(GOLD) + 1)]


def test_loader_rejects_a_refusal_item_with_sql() -> None:
    with pytest.raises(ValueError, match="gold_sql null"):
        GoldItem(
            id="x",
            category="should_refuse",
            difficulty="easy",
            features=[],
            question="q",
            gold_sql="SELECT 1",
            ordered=False,
            refusal_reason="r",
        )


def test_loader_rejects_an_in_schema_item_without_sql() -> None:
    with pytest.raises(ValueError, match="need gold_sql"):
        GoldItem(
            id="x",
            category="in_schema",
            difficulty="easy",
            features=[],
            question="q",
            gold_sql=None,
            ordered=False,
            refusal_reason=None,
        )


def _canonical(rows: Sequence[Any], ordered: bool) -> list[tuple[str, ...]]:
    def cell(value: object) -> str:
        if isinstance(value, Decimal):
            return f"{float(value):.9g}"
        return repr(value)

    out = [tuple(cell(v) for v in row) for row in rows]
    return out if ordered else sorted(out)


@pytest.mark.parametrize("item", IN_SCHEMA, ids=lambda item: item.id)
def test_gold_sql_executes_non_empty_and_deterministic(item: GoldItem, pg_seeded: Engine) -> None:
    assert item.gold_sql is not None
    with pg_seeded.connect() as conn:
        first = conn.execute(text(item.gold_sql)).fetchall()
        second = conn.execute(text(item.gold_sql)).fetchall()
    assert first, f"{item.id}: gold result is empty"
    assert any(value is not None for row in first for value in row), f"{item.id}: all NULL"
    assert _canonical(first, item.ordered) == _canonical(second, item.ordered)


# --- the v0.2 held-out set (plan v0.2, Phase 0 counts; G2) ---

HOLDOUT = load_gold(GOLD_DIR / "holdout-v02.jsonl")
HOLDOUT_IN_SCHEMA = [item for item in HOLDOUT if item.category == "in_schema"]


def test_holdout_counts_meet_phase_0() -> None:
    categories = Counter(item.category for item in HOLDOUT)
    assert len(HOLDOUT) == 40
    assert categories == {"in_schema": 28, "out_of_schema": 6, "should_refuse": 6}
    assert [item.id for item in HOLDOUT] == [f"ho-{n:03d}" for n in range(1, 41)]
    assert not {item.id for item in HOLDOUT} & {item.id for item in GOLD}


@pytest.mark.parametrize("item", HOLDOUT_IN_SCHEMA, ids=lambda item: item.id)
def test_holdout_sql_executes_non_empty_and_deterministic(
    item: GoldItem, pg_seeded: Engine
) -> None:
    test_gold_sql_executes_non_empty_and_deterministic(item, pg_seeded)
