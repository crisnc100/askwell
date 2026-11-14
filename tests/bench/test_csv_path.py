"""P2.4: the CSV path (`askwell_csv`) end to end on a small fixture, in replay mode: the
tables exported to CSV, checked, loaded, drafted and confirmed as drafted, the questions
exported, answered, imported and replayed, and the answers scored against gold SQL run
on the original database. A table whose file fails the check scores its questions as
refused, and the report lists it."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from askwell.bench.csv_path import (
    FAILED_TABLE,
    AskwellCsvSystem,
    build_workspace,
    export_csv,
    tables_in,
)
from askwell.bench.items import EvalItem
from askwell.bench.report import build, render_markdown
from askwell.bench.run import RunResult, _Gold, score
from askwell.config import get_settings
from askwell.core.executor import readonly_engine
from askwell.llm.replay import ReplayStore
from askwell.llm.simulate import PendingRequestError, answer_path, import_answers, pending_requests
from askwell.pipeline.service import AskService, build_gateway

STATEMENTS = [
    "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)",
    "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount TEXT)",
    # A spreadsheet shortened one ID: the upload check refuses this file.
    "CREATE TABLE notes (id TEXT PRIMARY KEY, body TEXT)",
    "INSERT INTO customers VALUES (1, 'Ash'), (2, 'Birch'), (3, 'Cedar')",
    "INSERT INTO orders VALUES (1, 1, '10.5'), (2, 1, 'null'), (3, 2, '4'), (4, 3, ' 6 ')",
    "INSERT INTO notes VALUES ('1', 'a'), ('2', 'b'), ('1.23457E+11', 'c')",
]

ITEMS = {
    "csv-1": ("How many orders are there?", "SELECT count(*) FROM orders"),
    "csv-2": ("What is the total order amount?", "SELECT sum(amount) FROM orders"),
    "csv-3": (
        "How many orders did Ash place?",
        "SELECT count(*) FROM orders AS o JOIN customers AS c ON o.customer_id = c.id "
        "WHERE c.name = 'Ash'",
    ),
    "csv-4": ("How many notes are there?", "SELECT count(*) FROM notes"),
}

INTENTS: dict[str, dict[str, Any]] = {
    "csv-1": {"intent_type": "summary", "entity": "orders", "metrics": [{"agg": "count"}]},
    "csv-2": {
        "intent_type": "summary",
        "entity": "orders",
        "metrics": [{"agg": "sum", "field": "amount"}],
    },
    "csv-3": {
        "intent_type": "summary",
        "entity": "orders",
        "metrics": [{"agg": "count"}],
        "filters": [{"field": "customers.name", "op": "eq", "value": "Ash"}],
    },
}


def _items() -> list[EvalItem]:
    return [
        EvalItem(
            id=item_id,
            schema_id="csv_fixture",
            category="in_schema",
            question=question,
            gold_sql=sql,
            ordered=False,
            difficulty="easy",
        )
        for item_id, (question, sql) in ITEMS.items()
    ]


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "source.sqlite"
    with sqlite3.connect(path) as conn:
        for statement in STATEMENTS:
            conn.execute(statement)
    return path


def test_tables_in_reads_from_and_join() -> None:
    sql = 'SELECT * FROM Orders AS o JOIN "Customers" c ON 1 = 1 WHERE x IN (SELECT 1 FROM t2)'
    assert tables_in(sql) == {"orders", "customers", "t2"}


def test_a_failing_file_is_dropped_and_the_rest_load(source: Path, tmp_path: Path) -> None:
    files = export_csv(source, tmp_path / "files")
    assert sorted(p.name for p in files) == ["customers.csv", "notes.csv", "orders.csv"]
    workspace = build_workspace(files, tmp_path / "ws")
    assert workspace.failed == {"notes": ["bad_value"]}
    assert workspace.registry is not None
    assert sorted(workspace.registry.entities) == ["customers", "orders"]
    assert not workspace.registry.draft
    amount = workspace.registry.entities["orders"].fields["amount"]
    assert amount.type == "number"
    assert amount.text_number


def test_text_is_exported_byte_for_byte(tmp_path: Path) -> None:
    path = tmp_path / "bytes.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO t VALUES (1, CAST(X'47C3BC6CFF' AS TEXT)), (2, NULL)")
    [out] = export_csv(path, tmp_path / "files")
    assert out.read_bytes() == b"id,name\n1,G\xc3\xbcl\xff\n2,\n"


def test_end_to_end_in_replay_mode(source: Path, tmp_path: Path) -> None:
    settings = get_settings()
    model = settings.default_model
    assert model is not None
    workspace = build_workspace(export_csv(source, tmp_path / "files"), tmp_path / "ws")
    store_path, pending = tmp_path / "recordings.jsonl", tmp_path / "pending"

    def system(mode: str) -> AskwellCsvSystem:
        gateway = build_gateway(settings, mode, store_path=store_path, pending_dir=pending)
        service = AskService(settings, {}, gateway, audit=None, model=model)
        return AskwellCsvSystem(service, "csv_fixture", workspace, settings.now)

    exporter = system("export")
    for item in _items():
        if item.id in INTENTS:
            with pytest.raises(PendingRequestError):
                exporter.answer(item, 1, None)
    exporter.close()
    requests = pending_requests(pending)
    assert len(requests) == len(INTENTS)
    for request_file in requests:
        request = json.loads(request_file.read_text(encoding="utf-8"))
        item_id = request["context"]["item_id"]
        answer = {"key": request["key"], "simulated_by": "test", "response": INTENTS[item_id]}
        answer_path(pending, request["key"]).write_text(json.dumps(answer), encoding="utf-8")
    assert len(import_answers(pending, ReplayStore(store_path))) == len(INTENTS)

    replayer = system("replay")
    engine = readonly_engine(f"sqlite:///{source}")
    gold = _Gold(engine, settings.row_cap, settings.query_timeout_s)
    records: list[dict[str, Any]] = []
    try:
        for item in _items():
            answer = replayer.answer(item, 1, None)
            outcome = score(item, answer.rows, answer.refused, answer.error, gold, settings.row_cap)
            records.append(_record(item, outcome, answer.detail))
    finally:
        replayer.close()
        engine.dispose()
    assert [r["outcome"] for r in records] == ["correct", "correct", "correct", "refused"]
    assert records[3]["detail"]["issue_codes"] == [FAILED_TABLE]

    report = build(
        RunResult(run_id="csv-fixture", records=records, systems=["askwell_csv"], models=[model])
    )
    assert report["csv_load_failures"] == {"csv_fixture": {"notes": ["bad_value"]}}
    assert "- csv_fixture: `notes`: bad_value" in render_markdown(report)


def _record(item: EvalItem, outcome: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": item.id,
        "schema_id": item.schema_id,
        "model": "m",
        "trial": 1,
        "system": "askwell_csv",
        "item_id": item.id,
        "gold": "",
        "category": item.category,
        "difficulty": item.difficulty,
        "outcome": outcome,
        "cost_usd": 0.0,
        "latency_ms": 0.0,
        "error": None,
        "sql": None,
        "detail": detail,
        "provenance": None,
    }


def test_an_eval_run_exports_every_question_of_a_spider_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from askwell.bench import run as run_module
    from askwell.bench.items import spider_items

    for name in ("RUNS_DIR", "EVAL_RECORDINGS", "EVAL_PENDING", "CSV_DIR"):
        monkeypatch.setattr(run_module, name, tmp_path / name.lower())
    result = run_module.run_eval(
        get_settings(),
        run_id="t",
        schema_ids=["spider_network_1"],
        systems=["askwell_csv"],
        mode="export",
        models=["target/model"],
        trials=1,
        budget_usd=1.0,
    )
    # Every question is either sent to the model or refused for a table that did not load.
    refused = [r for r in result.records if r["outcome"] == "refused"]
    assert all(r["detail"]["issue_codes"] == [FAILED_TABLE] for r in refused)
    assert len(result.records) == len(refused)
    sent = result.deferred["spider_network_1/askwell_csv"]
    assert sent > 0
    assert sent + len(refused) == len(spider_items("network_1"))


def test_when_no_file_loads_every_question_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "noid.sqlite"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE pairs (a_code TEXT, b_code TEXT)")
        conn.execute("INSERT INTO pairs VALUES ('x', 'y')")
    workspace = build_workspace(export_csv(path, tmp_path / "files"), tmp_path / "ws")
    assert workspace.registry is None
    assert workspace.failed == {"pairs": ["no_id_column"]}
    service = AskService(get_settings(), {}, None, audit=None, model="m")  # type: ignore[arg-type]
    system = AskwellCsvSystem(service, "noid", workspace, get_settings().now)
    [item] = _items()[:1]
    answer = system.answer(item, 1, None)
    assert answer.refused
    assert answer.detail["failed_tables"] == {"pairs": ["no_id_column"]}
