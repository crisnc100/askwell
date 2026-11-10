"""Replay API tests on the committed recordings (simulated answers; see each record's
provenance). These replay real recorded model answers through the real pipeline:
answerable, out-of-registry refusal, hidden-field refusal, write refusal, and
registry init -> ask on a Spider DB. Every ask writes an ask_log row."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text

from evals.replay_cases import SPIDER_QUESTION, cases
from ledgerline.api import create_app
from ledgerline.config import get_settings
from ledgerline.core.audit import AuditLog, ask_log
from ledgerline.pipeline.service import AskService, build_gateway

EXAMPLES = {
    "unpaid": "How many invoices are still unpaid?",
    "top_techs": "Which five technicians billed the most labor hours this year?",
    "segment_avg": "What is the average invoice amount for each customer segment?",
    "urgent_regions": "How many urgent work orders were opened in each customer region last month?",
    "hidden": "Show me the email address of every dispatcher.",
    "out_of_registry": "What did we spend on marketing last quarter?",
    "write": "Delete all void invoices.",
}


@pytest.fixture
def app_db(tmp_path: Path) -> Iterator[Engine]:
    engine = create_engine(f"sqlite:///{tmp_path / 'app.sqlite'}")
    yield engine
    engine.dispose()


@pytest.fixture
def client(tmp_path: Path, app_db: Engine, pg_seeded: Engine) -> Iterator[TestClient]:
    settings = get_settings()
    schemas, _ = cases(settings, tmp_path)
    service = AskService(settings, schemas, build_gateway(settings, "replay"), AuditLog(app_db))
    with TestClient(create_app(service)) as test_client:
        yield test_client


def _ask(client: TestClient, schema_id: str, question: str) -> dict[str, Any]:
    response = client.post("/ask", json={"schema_id": schema_id, "question": question})
    assert response.status_code == 200, response.text
    return response.json()


def _audit(app_db: Engine) -> list[dict[str, Any]]:
    with app_db.connect() as conn:
        return [dict(r) for r in conn.execute(select(ask_log)).mappings()]


def test_every_canned_example_replays(client: TestClient) -> None:
    examples = client.get("/schemas/fieldservice/examples").json()
    assert set(examples) == set(EXAMPLES.values())
    for question in examples:
        body = _ask(client, "fieldservice", question)
        assert body["provenance"] is not None
        assert set(body["provenance"]) == {"simulated_by", "standing_in_for"}


def test_answerable_matches_the_database(
    client: TestClient, app_db: Engine, pg_seeded: Engine
) -> None:
    body = _ask(client, "fieldservice", EXAMPLES["unpaid"])
    assert body["refusal"] is None
    with pg_seeded.connect() as conn:
        expected = conn.execute(
            text("SELECT count(*) FROM invoices WHERE status = 'unpaid'")
        ).scalar_one()
    assert body["rows"] == [[expected]]
    assert body["sql"]
    # The value is a bound parameter, never a SQL literal (an alias may contain the word).
    assert "'unpaid'" not in body["sql"]
    assert list(body["params"].values()) == ["unpaid"]
    row = _audit(app_db)[0]
    assert (row["outcome"], row["trace_id"], row["row_count"]) == ("answered", body["trace_id"], 1)


@pytest.mark.parametrize("name", ["top_techs", "segment_avg", "urgent_regions"])
def test_other_answerable_examples_return_rows(client: TestClient, name: str) -> None:
    body = _ask(client, "fieldservice", EXAMPLES[name])
    assert body["refusal"] is None, body["validation"]
    assert body["rows"]


@pytest.mark.parametrize("name", ["hidden", "out_of_registry", "write"])
def test_refusals(client: TestClient, app_db: Engine, name: str) -> None:
    body = _ask(client, "fieldservice", EXAMPLES[name])
    assert body["refusal"]
    assert body["sql"] is None
    assert body["rows"] == []
    assert _audit(app_db)[0]["outcome"] == "refused"


def test_hidden_values_never_come_back(client: TestClient) -> None:
    body = _ask(client, "fieldservice", EXAMPLES["hidden"])
    assert "@example.com" not in str(body)


def test_registry_init_then_ask_on_a_spider_db(client: TestClient, app_db: Engine) -> None:
    body = _ask(client, "spider_dog_kennels", SPIDER_QUESTION)
    assert body["refusal"] is None, body["validation"]
    assert body["rows"]
    assert body["sql"]
    assert _audit(app_db)[0]["schema_id"] == "spider_dog_kennels"


def test_an_unrecorded_question_is_a_clear_409(client: TestClient) -> None:
    response = client.post(
        "/ask", json={"schema_id": "fieldservice", "question": "Something nobody recorded?"}
    )
    assert response.status_code == 409
    assert "canned examples" in response.json()["detail"]


def test_cli_ask_replays_an_example(pg_seeded: Engine) -> None:
    import json

    from typer.testing import CliRunner

    from ledgerline.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["ask", EXAMPLES["unpaid"], "--mode", "replay"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["rows"]
    assert body["provenance"]["standing_in_for"] == "openai/gpt-oss-120b"
    missing = runner.invoke(app, ["ask", "Nobody recorded this?", "--mode", "replay"])
    assert missing.exit_code == 4
