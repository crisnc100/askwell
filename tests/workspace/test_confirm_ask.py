"""Confirm and Ask on a workspace, with a fake model (never a live call).

L19: hidden fields and unshared category values never reach the model.
L23: relative dates use the wall clock in the workspace's time zone.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ledgerline.api import create_app
from ledgerline.config import Settings, get_settings
from ledgerline.llm.simulate import PendingRequestError
from ledgerline.pipeline.service import build_gateway
from ledgerline.workspace.api import HEADER, WorkspaceApp
from ledgerline.workspace.ask import NEEDS_KEY, explain, workspace_target
from ledgerline.workspace.limits import Limits
from ledgerline.workspace.store import DEFAULT_TIME_ZONE, WorkspaceStore
from tests.workspace.conftest import SAMPLE, FakeClock, upload_sample
from tests.workspace.fake_model import FakeModel, fake_service

COUNT_ORDERS = {"intent_type": "summary", "entity": "orders", "metrics": [{"agg": "count"}]}


def _city_values() -> list[str]:
    with (SAMPLE / "customers.csv").open(newline="") as fh:
        return sorted({row["city"] for row in csv.DictReader(fh)})


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def model() -> FakeModel:
    return FakeModel({"How many orders?": COUNT_ORDERS})


@pytest.fixture
def client(store: WorkspaceStore, settings: Settings, model: FakeModel) -> Iterator[TestClient]:
    app = create_app(service=fake_service(settings, model), workspaces=WorkspaceApp(store))
    with TestClient(app) as c:
        yield c


def checked(client: TestClient, time_zone: str = DEFAULT_TIME_ZONE) -> dict[str, str]:
    response = client.post("/api/workspaces", json={"time_zone": time_zone})
    headers = {HEADER: response.json()["id"]}
    upload_sample(client, headers)
    assert client.post("/api/workspace/check", headers=headers).json()["state"] == "checked"
    return headers


def confirm(client: TestClient, headers: dict[str, str], edits: dict[str, Any]) -> None:
    response = client.post("/api/workspace/confirm", json={"fields": edits}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "confirmed"


def ask(client: TestClient, headers: dict[str, str], question: str) -> dict[str, Any]:
    response = client.post("/api/workspace/ask", json={"question": question}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def field(tables: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return next(f for t in tables for f in t["fields"] if f["key"] == key)


def test_draft_lists_fields_links_and_auto_hidden(client: TestClient) -> None:
    headers = checked(client)
    tables = client.get("/api/workspace/fields", headers=headers).json()["tables"]
    assert [t["name"] for t in tables] == ["customers", "order_items", "orders", "products"]
    email = field(tables, "customers.contact_email")
    assert email["hidden"] is True
    assert email["auto_hidden"] is True
    city = field(tables, "customers.city")
    assert city["values"] == _city_values()
    assert city["share_values"] is False
    assert field(tables, "orders.customer_id")["link"] == "customers.id"
    assert field(tables, "order_items.product_id")["link"] == "products.id"
    assert field(tables, "orders.order_date")["type"] == "date"


def test_preview_is_exactly_the_prompt_the_model_gets(client: TestClient, model: FakeModel) -> None:
    headers = checked(client)
    edits = {
        "customers.name": {"hidden": True},
        "orders.status": {"description": "Where the order is: paid, shipped or refunded."},
        "customers.segment": {"share_values": True},
    }
    preview = client.post("/api/workspace/preview", json={"fields": edits}, headers=headers)
    confirm(client, headers, edits)
    assert ask(client, headers, "How many orders?")["rows"] == [[60]]
    assert model.system_prompts == [preview.json()["prompt"]]


def test_edits_change_what_the_model_sees(client: TestClient) -> None:
    headers = checked(client)

    def prompt(edits: dict[str, Any]) -> str:
        body = {"fields": edits}
        return client.post("/api/workspace/preview", json=body, headers=headers).json()["prompt"]

    plain = prompt({})
    assert "- contact_email" not in plain
    assert "- name: text" in plain
    assert not any(city in plain for city in _city_values())
    edited = prompt(
        {
            "products.name": {"hidden": True},
            "customers.contact_email": {"hidden": False},
            "customers.city": {"share_values": True},
            "orders.status": {"description": "Where the order is."},
        }
    )
    assert "- contact_email: text" in edited
    assert all(city in edited for city in _city_values())
    assert "- status: text — Where the order is." in edited
    products = edited.split("## products")[1].split("## ")[0]
    assert "- name" not in products


def test_hidden_fields_and_unshared_values_never_reach_the_model(
    client: TestClient, store: WorkspaceStore, settings: Settings, tmp_path: Path
) -> None:
    """L19, on the exported request: the file the export gateway writes is exactly what
    would be sent to the model."""
    headers = checked(client)
    confirm(
        client,
        headers,
        {"customers.segment": {"share_values": True}, "orders.shipping_cost": {"hidden": True}},
    )
    pending = tmp_path / "pending"
    gateway = build_gateway(
        settings, "export", store_path=tmp_path / "rec.jsonl", pending_dir=pending
    )
    service = fake_service(settings, gateway)  # type: ignore[arg-type]
    workspace = store.open(headers[HEADER])
    with workspace_target(workspace, store.clock) as target, pytest.raises(PendingRequestError):
        service.ask_target(target, "Which city orders most?")
    [exported] = list(pending.glob("*.json"))
    request = exported.read_text(encoding="utf-8")
    assert "contact_email" not in request
    assert "shipping_cost" not in request
    for city in _city_values():
        assert city not in request
    for status in ("refunded", "shipped"):
        assert status not in request
    assert "online" in request  # the shared segment values
    assert "Which city orders most?" in json.loads(request)["messages"][-1]["content"]


def test_an_unshared_value_typed_by_the_person_still_answers(
    client: TestClient, model: FakeModel
) -> None:
    city = _city_values()[0]
    model.answers = {
        "How many customers in that city?": {
            "intent_type": "summary",
            "entity": "customers",
            "metrics": [{"agg": "count"}],
            "filters": [{"field": "city", "op": "eq", "value": city}],
        }
    }
    headers = checked(client)
    confirm(client, headers, {})
    with (SAMPLE / "customers.csv").open(newline="") as fh:
        expected = sum(1 for row in csv.DictReader(fh) if row["city"] == city)
    assert ask(client, headers, "How many customers in that city?")["rows"] == [[expected]]


def test_a_hidden_field_is_refused_in_plain_english(client: TestClient, model: FakeModel) -> None:
    model.answers = {
        "List customer emails": {
            "intent_type": "row_list",
            "entity": "customers",
            "select": ["contact_email"],
        }
    }
    headers = checked(client)
    confirm(client, headers, {})
    body = ask(client, headers, "List customer emails")
    assert body["sql"] is None
    assert body["explanation"] == {
        "message": "The question needs a field you hid.",
        "suggestion": "Unhide it on the Confirm page if the model may use it.",
    }


def test_fan_out_is_refused_in_plain_english(client: TestClient, model: FakeModel) -> None:
    model.answers = {
        "Total shipping per customer": {
            "intent_type": "grouped_summary",
            "entity": "customers",
            "metrics": [{"agg": "sum", "field": "orders.shipping_cost", "alias": "shipping"}],
            "group_by": [{"field": "name"}],
        }
    }
    headers = checked(client)
    confirm(client, headers, {})
    body = ask(client, headers, "Total shipping per customer")
    assert body["explanation"]["message"].startswith("Adding up across a one-to-many link")
    assert "fan_out" not in json.dumps(body["explanation"])


def test_unanswerable_is_explained(client: TestClient) -> None:
    headers = checked(client)
    confirm(client, headers, {})
    body = ask(client, headers, "What will sales be next year?")
    assert body["explanation"]["message"] == (
        "The model found no way to answer this from your data: not in the data"
    )


def test_ask_before_confirm_says_confirm_first(client: TestClient) -> None:
    headers = checked(client)
    response = client.post("/api/workspace/ask", json={"question": "q"}, headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Confirm your fields first."}


def test_without_a_key_workspace_asks_say_so_never_500(
    store: WorkspaceStore, settings: Settings
) -> None:
    replay = build_gateway(settings, "replay")
    app = create_app(service=fake_service(settings, replay), workspaces=WorkspaceApp(store))  # type: ignore[arg-type]
    with TestClient(app) as client:
        headers = checked(client)
        confirm(client, headers, {})
        response = client.post("/api/workspace/ask", json={"question": "q"}, headers=headers)
    assert response.status_code == 503
    assert response.json() == {"detail": NEEDS_KEY}
    assert NEEDS_KEY == "Live answers need a model key; see the README."


def test_a_model_failure_is_a_plain_502(client: TestClient, model: FakeModel) -> None:
    def broken(_question: str) -> dict[str, Any]:
        raise RuntimeError("provider down")

    model.answers = broken
    headers = checked(client)
    confirm(client, headers, {})
    response = client.post("/api/workspace/ask", json={"question": "q"}, headers=headers)
    assert response.status_code == 502
    assert "Try again" in response.json()["detail"]


def test_confirm_needs_a_checked_workspace(client: TestClient) -> None:
    headers = {HEADER: client.post("/api/workspaces", json={}).json()["id"]}
    response = client.post("/api/workspace/confirm", json={"fields": {}}, headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Check your files first."}
    assert client.get("/api/workspace/fields", headers=headers).status_code == 400


def test_bad_edits_are_refused(client: TestClient) -> None:
    headers = checked(client)
    for edits, detail in (
        ({"nope.field": {"hidden": True}}, "There is no field 'nope.field' in this workspace."),
        ({"orders.id": {"share_values": True}}, "The field 'orders.id' has no category values"),
    ):
        response = client.post("/api/workspace/preview", json={"fields": edits}, headers=headers)
        assert response.status_code == 400
        assert response.json()["detail"].startswith(detail)
    long = {"orders.status": {"description": "x" * 301}}
    assert (
        client.post("/api/workspace/preview", json={"fields": long}, headers=headers).status_code
        == 422
    )


def test_confirmed_edits_are_kept_and_can_be_changed(client: TestClient) -> None:
    headers = checked(client)
    confirm(client, headers, {"orders.status": {"description": "first"}})
    body = client.get("/api/workspace/fields", headers=headers).json()
    assert body["edits"]["fields"]["orders.status"]["description"] == "first"
    assert field(body["tables"], "orders.status")["description"] == "first"
    confirm(client, headers, {"orders.status": {"description": "second"}})


def test_each_workspace_has_its_own_ask_log_and_delete_removes_it(
    client: TestClient, store: WorkspaceStore
) -> None:
    a = checked(client)
    b = checked(client)
    for headers in (a, b):
        confirm(client, headers, {})
    ask(client, a, "How many orders?")
    import sqlite3

    def questions(headers: dict[str, str]) -> list[str]:
        path = store.root / headers[HEADER] / "audit.sqlite"
        if not path.exists():
            return []
        with sqlite3.connect(path) as conn:
            return [r[0] for r in conn.execute("SELECT question FROM ask_log")]

    assert questions(a) == ["How many orders?"]
    assert questions(b) == []
    client.delete("/api/workspace", headers=a)
    assert not (store.root / a[HEADER]).exists()
    assert questions(b) == []


def test_ask_rate_limit_per_ip(tmp_path: Path, settings: Settings, clock: FakeClock) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(asks_per_hour=2), clock)
    model = FakeModel({"How many orders?": COUNT_ORDERS})
    app = create_app(service=fake_service(settings, model), workspaces=WorkspaceApp(store))
    with TestClient(app) as client:
        headers = checked(client)
        confirm(client, headers, {})
        codes = [
            client.post(
                "/api/workspace/ask", json={"question": "How many orders?"}, headers=headers
            ).status_code
            for _ in range(3)
        ]
        demo = client.post("/ask", json={"schema_id": "fieldservice", "question": "q"})
    assert codes == [200, 200, 429]
    assert demo.status_code == 429  # the demo shares the same per-IP limit


LAST_MONTH = {
    "intent_type": "summary",
    "entity": "orders",
    "metrics": [{"agg": "count"}],
    "date_range": {"field": "order_date", "relative": "last_month"},
}


@pytest.mark.parametrize(
    ("utc_now", "time_zone", "local_day", "start", "end"),
    [
        # 03:00 UTC on 1 March is still 28 February in the default zone (UTC-5).
        ("2026-03-01T03:00:00", DEFAULT_TIME_ZONE, "2026-02-28", "2026-01-01", "2026-02-01"),
        # 12:00 UTC on 31 March is already 1 April in Auckland (UTC+13).
        ("2026-03-31T12:00:00", "Pacific/Auckland", "2026-04-01", "2026-03-01", "2026-04-01"),
    ],
)
def test_relative_dates_use_the_wall_clock_in_the_workspace_zone(
    store: WorkspaceStore,
    clock: FakeClock,
    model: FakeModel,
    client: TestClient,
    utc_now: str,
    time_zone: str,
    local_day: str,
    start: str,
    end: str,
) -> None:
    """L23, with a fake clock. Evals keep the pinned reference time: see
    test_configured_schemas_keep_the_pinned_reference_time."""
    clock.now = datetime.fromisoformat(utc_now).replace(tzinfo=UTC)
    model.answers = {"Orders last month?": LAST_MONTH}
    headers = checked(client, time_zone)
    confirm(client, headers, {})
    body = ask(client, headers, "Orders last month?")
    assert f"Reference date: {local_day} ({time_zone})." in model.system_prompts[-1]
    bounds = sorted(str(v) for v in body["params"].values())
    assert [b[:10] for b in bounds] == [start, end]
    assert body["rows"][0][0] == _orders_between(start, end)


def _orders_between(start: str, end: str) -> int:
    with (SAMPLE / "orders.csv").open(newline="") as fh:
        return sum(1 for row in csv.DictReader(fh) if start <= row["order_date"] < end)


def test_configured_schemas_keep_the_pinned_reference_time(settings: Settings) -> None:
    from ledgerline.pipeline.service import AskService, SchemaConfig
    from tests.core.conftest import FIELDSERVICE_REGISTRY

    schemas = {
        "fs": SchemaConfig("fs", "fs", FIELDSERVICE_REGISTRY, "sqlite:///unused.sqlite"),
    }
    service = AskService(settings, schemas, FakeModel(), None, model="m")  # type: ignore[arg-type]
    service.engine = lambda _schema_id: None  # type: ignore[assignment,method-assign,return-value]
    target = service.target("fs")
    assert target.now == settings.now
    assert target.time_zone == "UTC"


def test_explain_covers_every_refusal_path() -> None:
    def result(**parts: Any) -> dict[str, Any]:
        return {"refusal": "r", "validation": {}, "intent": None, **parts}

    assert explain({"refusal": None}) is None
    assert explain(result(validation={"stopped": "x"}))["message"].startswith("This question hit")  # type: ignore[index]
    parse = {"attempts": [{"parse_error": "bad", "issues": []}]}
    assert "could not be read" in explain(result(validation=parse))["message"]  # type: ignore[index]
    failed = result(refusal="the query failed: boom")
    assert explain(failed)["message"] == "The database could not run the query."  # type: ignore[index]
    for code, start in (
        ("ambiguous_path", "Two tables are linked"),
        ("unreachable_field", "The question needs tables"),
        ("unknown_field", "The question mentions data"),
        ("value_not_allowed", "A value in the question"),
        ("invalid_date_range", "The date range"),
        ("limit_out_of_range", "The question asks for more rows"),
        ("aggregate_type", "The question asks for a calculation"),
        ("intent_shape", "The question could not be turned"),
    ):
        issues = {"attempts": [{"parse_error": None, "issues": [{"code": code}]}]}
        assert explain(result(validation=issues))["message"].startswith(start), code  # type: ignore[index]
