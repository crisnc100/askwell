"""HAVING and BETWEEN thresholds are bound without narrowing casts: `count > 1.5` must
keep groups of 2 on both engines (an INTEGER-typed bind rounds 1.5 to 2 on Postgres)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text

from ledgerline.core.executor import run
from ledgerline.core.intent import Intent
from ledgerline.core.registry import Registry
from ledgerline.core.sqlbuild import build
from ledgerline.core.validate import validate
from tests.core.conftest import NOW


def _work_orders_with(registry: Registry, engine: Engine, having: dict[str, Any]) -> set[int]:
    intent = Intent.model_validate(
        {
            "intent_type": "grouped_summary",
            "entity": "invoices",
            "metrics": [{"agg": "count", "alias": "n"}],
            "group_by": [{"field": "work_order_id"}],
            "having": [having],
        }
    )
    plan = validate(intent, registry, now=NOW).plan
    assert plan is not None
    return {row[0] for row in run(engine, build(plan), row_cap=10_000).rows}


@pytest.mark.parametrize("engine_name", ["postgresql", "sqlite"])
def test_fractional_having_thresholds_are_not_rounded(
    engine_name: str, registry: Registry, pg_seeded: Engine, sqlite_ro: Engine
) -> None:
    engine = pg_seeded if engine_name == "postgresql" else sqlite_ro
    with pg_seeded.connect() as conn:
        twice = {
            row[0]
            for row in conn.execute(
                text("SELECT work_order_id FROM invoices GROUP BY 1 HAVING count(*) = 2")
            )
        }
    assert twice
    assert _work_orders_with(registry, engine, {"metric": "n", "op": "gt", "value": 1.5}) == twice
    assert (
        _work_orders_with(registry, engine, {"metric": "n", "op": "between", "values": [1.5, 2.5]})
        == twice
    )
    assert _work_orders_with(registry, engine, {"metric": "n", "op": "lt", "value": 1.5}) - twice
