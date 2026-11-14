"""Confirm's name column: drafted from the files, changeable and clearable, saved with the
other edits, and used when an answer groups by it (a fake model; never a live call)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from askwell.api import create_app
from askwell.config import Settings, get_settings
from askwell.core.registry import load_registry
from askwell.workspace.api import HEADER, WorkspaceApp
from askwell.workspace.store import WorkspaceStore
from tests.workspace.conftest import upload_sample
from tests.workspace.fake_model import FakeModel, fake_service

BY_CUSTOMER = {
    "intent_type": "grouped_summary",
    "entity": "orders",
    "metrics": [{"agg": "count", "alias": "n"}],
    "group_by": [{"field": "customers.name"}],
    "order_by": [{"target": "n", "direction": "desc"}],
    "limit": 3,
}


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def client(store: WorkspaceStore, settings: Settings) -> Iterator[TestClient]:
    model = FakeModel({"Top customers?": BY_CUSTOMER})
    app = create_app(service=fake_service(settings, model), workspaces=WorkspaceApp(store))
    with TestClient(app) as c:
        yield c


def checked(client: TestClient) -> dict[str, str]:
    headers = {HEADER: client.post("/api/workspaces", json={}).json()["id"]}
    upload_sample(client, headers)
    assert client.post("/api/workspace/check", headers=headers).json()["state"] == "checked"
    return headers


def tables(client: TestClient, headers: dict[str, str]) -> dict[str, dict[str, Any]]:
    body = client.get("/api/workspace/fields", headers=headers).json()
    return {t["name"]: t for t in body["tables"]}


def confirm(client: TestClient, headers: dict[str, str], edits: dict[str, Any]) -> None:
    response = client.post("/api/workspace/confirm", json=edits, headers=headers)
    assert response.status_code == 200, response.text


def top_customers(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/workspace/ask", json={"question": "Top customers?"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_draft_names_each_table_by_its_name_column(client: TestClient) -> None:
    found = tables(client, checked(client))
    assert found["customers"]["label"] == "name"
    assert found["products"]["label"] == "name"
    assert found["orders"]["label"] is None
    assert found["customers"]["label_options"] == ["name", "city", "segment"]
    # A table with no single ID column cannot name its rows.
    assert found["order_items"]["label_options"] == []


def test_grouping_by_the_name_column_shows_the_id(client: TestClient) -> None:
    headers = checked(client)
    confirm(client, headers, {"fields": {}})
    answer = top_customers(client, headers)
    assert answer["columns"] == ["customers__id", "customers__name", "n"]
    assert "tied_at_cutoff" in answer


def test_clearing_the_name_column_groups_by_the_value(
    client: TestClient, store: WorkspaceStore
) -> None:
    headers = checked(client)
    confirm(client, headers, {"fields": {}, "labels": {"customers": None}})
    assert tables(client, headers)["customers"]["label"] is None
    saved = client.get("/api/workspace/fields", headers=headers).json()["edits"]
    assert saved["labels"] == {"customers": None}
    assert top_customers(client, headers)["columns"] == ["customers__name", "n"]


def test_the_name_column_can_be_changed(client: TestClient, store: WorkspaceStore) -> None:
    headers = checked(client)
    confirm(client, headers, {"fields": {}, "labels": {"customers": "city"}})
    assert tables(client, headers)["customers"]["label"] == "city"
    registry = load_registry(store.open(headers[HEADER]).registry_path)
    assert registry.entities["customers"].label == "city"


def test_hiding_the_name_column_leaves_the_table_without_one(client: TestClient) -> None:
    headers = checked(client)
    confirm(client, headers, {"fields": {"customers.name": {"hidden": True}}})
    found = tables(client, headers)["customers"]
    assert found["label"] is None
    assert "name" not in found["label_options"]


@pytest.mark.parametrize(
    ("labels", "detail"),
    [
        ({"nope": "name"}, "There is no table 'nope'"),
        ({"customers": "signup_date"}, "cannot name a row"),
        ({"customers": "id"}, "cannot name a row"),
        ({"orders": "customer_id"}, "cannot name a row"),
    ],
)
def test_a_bad_name_column_is_refused(
    client: TestClient, labels: dict[str, str], detail: str
) -> None:
    headers = checked(client)
    response = client.post(
        "/api/workspace/preview", json={"fields": {}, "labels": labels}, headers=headers
    )
    assert response.status_code == 400
    assert detail in response.json()["detail"]
