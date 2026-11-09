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
