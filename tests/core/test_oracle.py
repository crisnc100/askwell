"""Differential oracle: 30 hand-written intents; the builder's rows on Postgres AND on
SQLite must equal the rows of a hand-written reference query (run on Postgres)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text

from askwell.core.executor import run
from askwell.core.intent import Intent
from askwell.core.registry import Registry
from askwell.core.sqlbuild import build
from askwell.core.validate import validate
from tests.core.conftest import NOW
from tests.core.oracle_cases import CASES
from tests.core.rows import normalise, same_rows

IDS = [case[0] for case in CASES]


def test_there_are_thirty_cases() -> None:
    assert len(CASES) == 30
    assert len(set(IDS)) == 30


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
@pytest.mark.parametrize(("case_id", "intent", "reference"), CASES, ids=IDS)
def test_builder_matches_reference(
    case_id: str,
    intent: dict[str, Any],
    reference: str,
    engine_name: str,
    registry: Registry,
    pg_seeded: Engine,
    sqlite_ro: Engine,
) -> None:
    parsed = Intent.model_validate(intent)
    result = validate(parsed, registry, now=NOW)
    assert result.plan is not None, result.issues
    with pg_seeded.connect() as conn:
        expected = conn.execute(text(reference)).fetchall()
    assert expected, f"{case_id}: reference returned no rows"
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    got = run(engine, build(result.plan)).rows
    ordered = bool(parsed.order_by)
    assert same_rows(got, expected, ordered), (
        f"{case_id} on {engine_name}\n got: {normalise(got, ordered)[:5]}\n"
        f"want: {normalise(expected, ordered)[:5]}"
    )
