"""Fixes for the PR2 full review (builds/v01/pr2-review-findings.md)."""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text

from ledgerline.bench import report as report_module
from ledgerline.bench import run as run_module
from ledgerline.bench.items import EvalItem
from ledgerline.bench.systems import OneShotSystem
from ledgerline.config import get_settings
from ledgerline.core.executor import readonly_engine
from ledgerline.core.registry import load_registry
from ledgerline.fieldservice.seed import content_hash
from ledgerline.llm.budget import BudgetGuard
from ledgerline.llm.gateway import Gateway
from ledgerline.llm.pricing import ModelPrice
from ledgerline.llm.replay import ReplayStore
from ledgerline.llm.types import RawResponse
from tests.core.conftest import FIELDSERVICE_REGISTRY

ITEM = EvalItem("fs-x", "fieldservice", "in_schema", "q", "SELECT 1", False, "easy")


class SqlTransport:
    def __init__(self, sql: str) -> None:
        self.sql = sql

    def __call__(self, **_: Any) -> RawResponse:
        body = {"sql": self.sql, "refusal_reason": None}
        return RawResponse(content="", parsed=body, usage={"cost": 0.0}, model="m")


def _oneshot(engine: Engine, sql: str, tmp_path: Path) -> OneShotSystem:
    gateway = Gateway(
        mode="live",
        store=ReplayStore(tmp_path / "s.jsonl"),
        transport=SqlTransport(sql),
        price_lookup=lambda _m: ModelPrice(1e-12, 1e-12),
        guard=BudgetGuard(1.0),
        max_tokens=10,
    )
    return OneShotSystem(
        gateway, engine, load_registry(FIELDSERVICE_REGISTRY), "m", "2026-06-30", 1000, 5.0
    )


# --- s1 (HIGH): model SQL is one read-only SELECT, never a batch ---

ESCAPE = "ROLLBACK; BEGIN READ WRITE; ALTER ROLE CURRENT_USER PASSWORD NULL; COMMIT; SELECT 1"


def test_a_multi_statement_batch_is_refused_and_changes_nothing(
    pg_seeded: Engine, pg_owner: Engine, tmp_path: Path
) -> None:
    before = content_hash(pg_owner)
    answer = _oneshot(pg_seeded, ESCAPE, tmp_path).answer(ITEM, 1, None)
    assert answer.rows == []
    assert answer.error is not None
    assert "single" in answer.error
    assert content_hash(pg_owner) == before
    # The read-only login still works with its password.
    fresh = create_engine(get_settings().database_ro_url)
    try:
        with fresh.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        fresh.dispose()


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE invoices SET amount = 0",
        "SELECT 1; DELETE FROM parts",
        "WITH x AS (SELECT 1) SELECT * FROM x; DROP TABLE parts",
        "/* hi */ ROLLBACK",
        "SET default_transaction_read_only = off",
    ],
)
def test_anything_but_one_select_is_refused(pg_seeded: Engine, tmp_path: Path, sql: str) -> None:
    answer = _oneshot(pg_seeded, sql, tmp_path).answer(ITEM, 1, None)
    assert answer.error is not None
    assert answer.rows == []


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM parts;",
        "  -- the parts\n  SELECT count(*) FROM parts",
        "WITH p AS (SELECT id FROM parts) SELECT count(*) FROM p",
        "SELECT count(*) FROM parts WHERE name <> 'a;b' /* ; */",
    ],
)
def test_one_select_still_runs(pg_seeded: Engine, tmp_path: Path, sql: str) -> None:
    answer = _oneshot(pg_seeded, sql, tmp_path).answer(ITEM, 1, None)
    assert answer.error is None, answer.error
    assert answer.rows == [(120,)]


# --- f1 (systems): comment-only SQL is an item error, not a crashed eval ---


def test_comment_only_sql_is_an_execution_error(
    sqlite_fieldservice: Engine, tmp_path: Path
) -> None:
    engine = readonly_engine(str(sqlite_fieldservice.url))
    try:
        answer = _oneshot(engine, "-- no query can answer this question", tmp_path).answer(
            ITEM, 1, None
        )
    finally:
        engine.dispose()
    assert answer.error is not None
    assert answer.rows == []


# --- f1 (service): each ask has its own budget guard ---


def test_concurrent_asks_do_not_share_a_budget_guard(
    sqlite_fieldservice: Engine, tmp_path: Path
) -> None:
    from ledgerline.pipeline.service import AskService, SchemaConfig

    valid = '{"intent_type": "summary", "entity": "invoices", "metrics": [{"agg": "count"}]}'
    b_waiting = threading.Event()
    a_done = threading.Event()

    class Transport:
        def __init__(self) -> None:
            self.calls: dict[str, int] = {"A": 0, "B": 0}

        def __call__(self, *, messages: Any, **_: Any) -> RawResponse:
            who = messages[1].content
            self.calls[who] += 1
            if who == "B" and self.calls["B"] == 1:
                b_waiting.set()
                a_done.wait(5)
                content = "not an intent"  # B's first answer fails, so B retries
            else:
                content = valid
            return RawResponse(content=content, usage={"cost": 0.015}, model="m")

    settings = get_settings().model_copy(update={"ask_budget_usd": 0.035})
    gateway = Gateway(
        mode="live",
        store=ReplayStore(tmp_path / "s.jsonl"),
        transport=Transport(),
        price_lookup=lambda _m: ModelPrice(1e-12, 0.015 / 1024),
        guard=BudgetGuard(1.0),
        max_tokens=1024,
    )
    schemas = {
        "fieldservice": SchemaConfig(
            "fieldservice", "fs", FIELDSERVICE_REGISTRY, str(sqlite_fieldservice.url)
        )
    }
    service = AskService(settings, schemas, gateway, audit=None, model="m")
    results: dict[str, Any] = {}

    def ask(who: str) -> None:
        try:
            results[who] = service.ask("fieldservice", who)
        except Exception as exc:
            results[who] = exc

    b = threading.Thread(target=ask, args=("B",))
    b.start()
    assert b_waiting.wait(5)
    ask("A")  # runs while B is mid-call
    a_done.set()
    b.join(5)
    service.close()
    # Each ask spent 0.015 or 0.03 of its own 0.035 cap; B's retry fits its own budget.
    assert not isinstance(results["A"], Exception), results["A"]
    assert not isinstance(results["B"], Exception), results["B"]
    assert results["A"].cost_usd == pytest.approx(0.015)
    assert results["B"].cost_usd == pytest.approx(0.03)


# --- f2 (run): checkpoint identity includes the question and gold SQL ---


def test_a_changed_gold_item_is_scored_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pg_seeded: Engine
) -> None:
    from tests.bench.test_run import _answer_all

    monkeypatch.setattr(run_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(run_module, "EVAL_RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(run_module, "EVAL_PENDING", tmp_path / "pending")

    def go(mode: str):
        return run_module.run_eval(
            get_settings(),
            run_id="g",
            schema_ids=["fieldservice"],
            systems=["oneshot"],
            mode=mode,
            models=["m"],
            trials=1,
            budget_usd=1.0,
        )

    go("export")
    _answer_all(
        tmp_path / "pending" / "fieldservice" / "oneshot",
        {},
        {"sql": "SELECT 1", "refusal_reason": None},
    )
    from ledgerline.llm.simulate import import_answers

    import_answers(
        tmp_path / "pending" / "fieldservice" / "oneshot",
        ReplayStore(tmp_path / "recordings" / "fieldservice" / "oneshot.jsonl"),
    )
    assert len(go("replay").records) == 67
    real_items = run_module.items_for

    def corrected(schema_id: str) -> list[EvalItem]:
        items = real_items(schema_id)
        return [replace(i, gold_sql="SELECT 1") if i.id == "fs-001" else i for i in items]

    monkeypatch.setattr(run_module, "items_for", corrected)
    again = go("replay")
    fs001 = next(r for r in again.records if r["item_id"] == "fs-001")
    assert fs001["outcome"] == "correct"  # re-scored against the corrected gold


# --- f3 (report): the floor uses the configured default model's row ---


def test_floor_checks_use_the_default_model(tmp_path: Path) -> None:
    floors = tmp_path / "floors.yaml"
    floors.write_text("fieldservice:\n  floors:\n    execution_accuracy: {min: 0.80}\n")

    def row(model: str, n: int) -> dict[str, Any]:
        return {
            "schema": "fieldservice",
            "system": "ledgerline",
            "model": model,
            "execution_accuracy": {"n": n, "of": 10, "rate": n / 10, "ci95": [0, 1]},
        }

    table = [row("a/secondary", 9), row("z/default", 5)]
    checks = report_module.floor_checks(table, floors, default_model="z/default")
    assert checks[0]["met"] is False
    assert checks[0]["model"] == "z/default"


# --- f4 (run): a configured Spider schema is still regenerated and hash-checked ---


def test_configured_spider_schema_is_regenerated_and_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ledgerline.pipeline.service import SchemaConfig

    stale = tmp_path / "car_1.yaml"
    stale.write_text("not the generated registry")

    def configured(_settings: object) -> dict[str, SchemaConfig]:
        return {"spider_car_1": SchemaConfig("spider_car_1", "car", stale, "sqlite://")}

    monkeypatch.setattr(run_module, "load_schemas", configured)
    schemas, hashes = run_module._schemas(get_settings(), ["spider_car_1"])
    assert schemas["spider_car_1"].registry_path != stale
    assert "spider_car_1" in hashes
