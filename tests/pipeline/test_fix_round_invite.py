"""PR5 review fixes on the invite gate: wrong codes in a header or cookie count as tries,
the cookie holds a hash rather than the code (so any code works, Latin-1 or not), the
login form's body is bounded and the limit is checked before it is read, and a beta or
production deployment without codes refuses to start."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from ledgerline import invite
from ledgerline.api import create_app
from ledgerline.config import Settings, get_settings
from ledgerline.core.audit import AuditLog
from ledgerline.llm.gateway import Gateway
from ledgerline.pipeline.service import AskService, SchemaConfig
from tests.pipeline.conftest import ScriptedGateway

CODES = ["alpha-123", "招待コード-7"]


@pytest.fixture
def client(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> TestClient:
    gateway = cast(Gateway, ScriptedGateway([]))
    service = AskService(settings, fieldservice_config, gateway, AuditLog(audit_engine), "m")
    app = create_app(service, web_dir=tmp_path / "none", invite_codes=[c.encode() for c in CODES])
    return TestClient(app, base_url="https://testserver")


def test_wrong_codes_in_a_header_are_rate_limited(client: TestClient) -> None:
    with client:
        for _ in range(invite.ATTEMPTS_PER_HOUR):
            assert client.get("/schemas", headers={invite.HEADER: "guess"}).status_code == 401
        blocked = client.get("/schemas", headers={invite.HEADER: "alpha-123"})
    assert blocked.status_code == 429


def test_wrong_cookies_are_rate_limited_and_cleared(client: TestClient) -> None:
    with client:
        client.cookies.set(invite.COOKIE, "guess")
        first = client.get("/schemas")
        assert first.status_code == 401
        assert invite.COOKIE in first.headers.get("set-cookie", "")
        for _ in range(invite.ATTEMPTS_PER_HOUR):
            client.cookies.set(invite.COOKIE, "guess")
            client.get("/schemas")
        client.cookies.set(invite.COOKIE, "guess")
        assert client.get("/schemas").status_code == 429


def test_requests_with_no_code_do_not_use_up_tries(client: TestClient) -> None:
    with client:
        for _ in range(invite.ATTEMPTS_PER_HOUR * 2):
            assert client.get("/schemas").status_code == 401
        ok = client.post("/invite", data={"code": "alpha-123"}, follow_redirects=False)
    assert ok.status_code == 303


def test_a_non_latin1_code_logs_in_and_the_cookie_never_holds_the_code(
    client: TestClient,
) -> None:
    with client:
        ok = client.post("/invite", data={"code": "招待コード-7"}, follow_redirects=False)
        assert ok.status_code == 303
        value = client.cookies.get(invite.COOKIE)
        assert value is not None
        assert "招待" not in value
        assert value != "alpha-123"
        assert value == hashlib.sha256("招待コード-7".encode()).hexdigest()
        assert client.get("/schemas").status_code == 200


def test_a_large_login_body_is_refused_unread(client: TestClient) -> None:
    with client:
        big = client.post("/invite", content=b"code=" + b"x" * 100_000)
    assert big.status_code == 413


def test_the_limit_is_checked_before_the_body_is_read(client: TestClient) -> None:
    with client:
        for _ in range(invite.ATTEMPTS_PER_HOUR):
            client.post("/invite", data={"code": "guess"})
        big = client.post("/invite", content=b"code=" + b"x" * 100_000)
    assert big.status_code == 429


@pytest.mark.parametrize("env", ["beta", "prod"])
def test_a_beta_or_production_deployment_without_codes_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env: str
) -> None:
    monkeypatch.setenv("LEDGERLINE_ENV", env)
    monkeypatch.delenv("LEDGERLINE_INVITE_CODES", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="LEDGERLINE_INVITE_CODES"):
            create_app(service=object(), web_dir=tmp_path / "none")  # type: ignore[arg-type]
    finally:
        get_settings.cache_clear()
