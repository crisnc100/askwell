"""The API with a scripted test-double gateway (cases a recording cannot express)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from ledgerline.api import create_app
from ledgerline.config import Settings
from ledgerline.pipeline.service import SchemaConfig
from tests.pipeline.conftest import scripted_service
from tests.pipeline.test_graph import UNPAID


def test_retry_then_success_over_http(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    bad = {**UNPAID, "entity": "bills_table"}
    service, _ = scripted_service(settings, fieldservice_config, [bad, UNPAID], audit_engine)
    with TestClient(create_app(service)) as client:
        body = client.post("/ask", json={"schema_id": "fieldservice", "question": "q"}).json()
    assert body["refusal"] is None
    assert body["rows"] == [[161]]
    assert [a["issues"][0]["code"] for a in body["validation"]["attempts"][:1]] == [
        "unknown_entity"
    ]
    assert set(body) >= {
        "intent",
        "validation",
        "sql",
        "params",
        "rows",
        "columns",
        "refusal",
        "trace_id",
        "cost_usd",
    }


def test_schemas_examples_health_and_unknown_schema(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    service, _ = scripted_service(settings, fieldservice_config, [], audit_engine)
    with TestClient(create_app(service)) as client:
        assert client.get("/healthz").json() == {"status": "ok", "mode": "replay"}
        assert client.get("/schemas").json() == [
            {"id": "fieldservice", "title": "Field service", "draft": False}
        ]
        assert client.get("/schemas/fieldservice/examples").json() == []
        assert client.get("/schemas/nope/examples").status_code == 404
        assert client.post("/ask", json={"schema_id": "nope", "question": "q"}).status_code == 404
        assert (
            client.post("/ask", json={"schema_id": "fieldservice", "question": ""}).status_code
            == 422
        )


RATIO = {
    "intent_type": "summary",
    "entity": "work_orders",
    "metrics": [
        {
            "agg": "count",
            "alias": "dropped",
            "where": [{"field": "status", "op": "eq", "value": "cancelled"}],
        },
        {"agg": "count", "alias": "total"},
        {
            "agg": "ratio",
            "alias": "pct",
            "numerator": "dropped",
            "denominator": "total",
            "as_percent": True,
        },
    ],
}
SERIES = {
    "intent_type": "date_series",
    "entity": "work_orders",
    "grain": "year",
    "series": [
        {"metric": {"agg": "count"}, "date_field": "opened_at", "alias": "opened"},
        {"metric": {"agg": "count"}, "date_field": "completed_at", "alias": "done"},
    ],
}


def test_ask_returns_the_new_intent_fields_as_they_are(
    settings: Settings, fieldservice_config: dict[str, SchemaConfig], audit_engine: Engine
) -> None:
    service, _ = scripted_service(settings, fieldservice_config, [RATIO, SERIES], audit_engine)
    with TestClient(create_app(service)) as client:
        ratio = client.post("/ask", json={"schema_id": "fieldservice", "question": "a"}).json()
        series = client.post("/ask", json={"schema_id": "fieldservice", "question": "b"}).json()
    assert ratio["refusal"] is None
    assert ratio["columns"] == ["dropped", "total", "pct"]
    assert ratio["intent"]["metrics"][2] == RATIO["metrics"][2]
    assert ratio["intent"]["metrics"][0]["where"] == RATIO["metrics"][0]["where"]
    assert series["refusal"] is None
    assert series["columns"] == ["period", "opened", "done"]
    assert series["intent"]["series"] == SERIES["series"]
    assert series["intent"]["grain"] == "year"
