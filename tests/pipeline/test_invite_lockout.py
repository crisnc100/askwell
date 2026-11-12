"""The invite limit counts only wrong codes. A right code never spends a try, so many
people logging in from one office address are never locked out. Once an address has
used up its tries, only credentials already accepted from it keep working; anything
new from it, right or wrong, is refused until the hour has passed."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from ledgerline import invite
from ledgerline.api import create_app
from ledgerline.config import Settings
from ledgerline.core.audit import AuditLog
from ledgerline.llm.gateway import Gateway
from ledgerline.pipeline.service import AskService, SchemaConfig
from tests.pipeline.conftest import ScriptedGateway

CODES = [b"alpha-123", b"beta-456"]


@pytest.fixture
def client(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> TestClient:
    gateway = cast(Gateway, ScriptedGateway([]))
    service = AskService(settings, fieldservice_config, gateway, AuditLog(audit_engine), "m")
    app = create_app(service, web_dir=tmp_path / "none", invite_codes=CODES)
    return TestClient(app, base_url="https://testserver")


def _guess_wrong(client: TestClient, times: int) -> None:
    for _ in range(times):
        client.get("/schemas", headers={invite.HEADER: "guess"})


def test_right_codes_never_spend_tries(client: TestClient) -> None:
    with client:
        for _ in range(invite.ATTEMPTS_PER_HOUR * 2):
            ok = client.post("/invite", data={"code": "alpha-123"}, follow_redirects=False)
            assert ok.status_code == 303
            assert client.get("/schemas").status_code == 200
        for _ in range(invite.ATTEMPTS_PER_HOUR * 2):
            assert client.get("/schemas", headers={invite.HEADER: "beta-456"}).status_code == 200


def test_a_locked_address_keeps_credentials_it_already_used(client: TestClient) -> None:
    with client:
        assert client.post("/invite", data={"code": "alpha-123"}).status_code == 200
        _guess_wrong(client, invite.ATTEMPTS_PER_HOUR)
        assert client.get("/schemas").status_code == 200  # the cookie it already had


def test_a_locked_address_cannot_try_anything_new(client: TestClient) -> None:
    with client:
        _guess_wrong(client, invite.ATTEMPTS_PER_HOUR)
        new_right = client.get("/schemas", headers={invite.HEADER: "beta-456"})
        assert new_right.status_code == 429
        login = client.post("/invite", data={"code": "beta-456"}, follow_redirects=False)
        assert login.status_code == 429
        assert client.get("/schemas", headers={invite.HEADER: "guess"}).status_code == 429


def test_a_locked_browser_gets_the_gate_page(client: TestClient) -> None:
    with client:
        _guess_wrong(client, invite.ATTEMPTS_PER_HOUR)
        client.cookies.set(invite.COOKIE, "0" * 64)
        page = client.get("/", headers={"accept": "text/html"})
    assert page.status_code == 429
    assert page.headers["content-type"].startswith("text/html")
    assert "Too many tries" in page.text
