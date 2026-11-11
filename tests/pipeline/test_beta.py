"""L26: the hosted beta's invite gate, global daily spending cap and kill switch."""

from __future__ import annotations

import hmac
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr
from sqlalchemy import Engine

from ledgerline import invite
from ledgerline.api import create_app
from ledgerline.config import Settings
from ledgerline.core.audit import AuditLog
from ledgerline.llm.budget import BudgetGuard
from ledgerline.llm.daily import CAP_REACHED, DailyCapReachedError, DailySpend
from ledgerline.llm.errors import LIVE_ANSWERS_OFF, LiveAnswersOffError, ParseError
from ledgerline.llm.gateway import Gateway
from ledgerline.llm.pricing import ModelPrice
from ledgerline.llm.replay import ReplayStore
from ledgerline.llm.types import ChatMessage, RawResponse
from ledgerline.pipeline import service as service_module
from ledgerline.pipeline.service import AskService, SchemaConfig, build_gateway

CODES = [b"alpha-123", b"beta-456"]


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 11, 23, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class Counting:
    """Answers every call with an unparseable reply that costs `cost`."""

    def __init__(self, cost: float = 0.01, fail: bool = False) -> None:
        self.calls = 0
        self.cost = cost
        self.fail = fail

    def __call__(self, **_: Any) -> RawResponse:
        self.calls += 1
        if self.fail:
            raise ConnectionError("provider down")
        return RawResponse(content="not an intent", usage={"cost": self.cost}, model="m")


def _gateway(
    tmp_path: Path,
    transport: Counting,
    daily: DailySpend | None = None,
    off: bool = False,
) -> Gateway:
    return Gateway(
        mode="live",
        store=ReplayStore(tmp_path / "s.jsonl"),
        transport=transport,
        # Worst case per call: 1000 completion tokens x $0.00002 = $0.02.
        price_lookup=lambda _m: ModelPrice(0.0, 0.00002),
        guard=BudgetGuard(10.0),
        max_tokens=1000,
        daily=daily,
        live_answers_off=off,
    )


class Answer(BaseModel):
    label: str


def _complete(gw: Gateway) -> None:
    gw.complete(
        model="m",
        prompt_version="v1",
        messages=[ChatMessage(role="user", content="q")],
        schema=Answer,
    )


# --- invite gate ---


@pytest.fixture
def gated(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> TestClient:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<p>the app</p>", encoding="utf-8")
    gateway = _gateway(tmp_path, Counting())
    service = AskService(settings, fieldservice_config, gateway, AuditLog(audit_engine), "m")
    app = create_app(service, web_dir=web, invite_codes=CODES)
    return TestClient(app, base_url="https://testserver")


def test_every_page_and_api_route_needs_a_code(gated: TestClient) -> None:
    with gated as client:
        page = client.get("/", headers={"accept": "text/html"})
        assert page.status_code == 401
        assert 'action="/invite"' in page.text
        assert "the app" not in page.text
        for method, path in [
            ("GET", "/schemas"),
            ("GET", "/api/limits"),
            ("GET", "/api/results"),
            ("POST", "/api/workspaces"),
            ("POST", "/ask"),
        ]:
            response = client.request(method, path, json={})
            assert response.status_code == 401, path
            assert response.json() == {"detail": invite.NEEDS_CODE}


def test_healthz_answers_without_a_code(gated: TestClient) -> None:
    with gated as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_a_valid_code_sets_a_cookie_that_opens_the_app(gated: TestClient) -> None:
    with gated as client:
        wrong = client.post("/invite", data={"code": "nope"}, follow_redirects=False)
        assert wrong.status_code == 401
        assert invite.COOKIE not in client.cookies
        ok = client.post("/invite", data={"code": "beta-456"}, follow_redirects=False)
        assert ok.status_code == 303
        cookie = ok.headers["set-cookie"]
        for flag in ("HttpOnly", "Secure", "SameSite=lax"):
            assert flag.lower() in cookie.lower()
        assert client.get("/", headers={"accept": "text/html"}).text == "<p>the app</p>"
        assert client.get("/schemas").status_code == 200


def test_scripts_can_send_the_code_in_a_header(gated: TestClient) -> None:
    with gated as client:
        assert client.get("/schemas", headers={invite.HEADER: "alpha-123"}).status_code == 200
        assert client.get("/schemas", headers={invite.HEADER: "alpha-12"}).status_code == 401


def test_a_removed_code_no_longer_opens_the_app(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    service = AskService(
        settings, fieldservice_config, _gateway(tmp_path, Counting()), AuditLog(audit_engine), "m"
    )
    app = create_app(service, web_dir=tmp_path / "none", invite_codes=[b"beta-456"])
    with TestClient(app) as client:
        client.cookies.set(invite.COOKIE, "alpha-123")
        assert client.get("/schemas").status_code == 401


def test_codes_are_compared_in_constant_time_against_every_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(invite.hmac, "compare_digest", spy)
    assert invite.is_valid("alpha-123", CODES)
    assert len(calls) == len(CODES)  # no early exit on the first match
    calls.clear()
    assert not invite.is_valid("x" * (invite.MAX_CODE_CHARS + 1), CODES)
    assert not invite.is_valid(None, CODES)


def test_codes_come_from_a_comma_separated_setting() -> None:
    assert invite.parse_codes(" alpha-123 , ,beta-456 ") == CODES
    assert invite.parse_codes(None) == []


def test_no_codes_means_no_gate(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    service = AskService(
        settings, fieldservice_config, _gateway(tmp_path, Counting()), AuditLog(audit_engine), "m"
    )
    with TestClient(create_app(service, web_dir=tmp_path / "none", invite_codes=[])) as client:
        assert client.get("/schemas").status_code == 200


def test_wrong_codes_are_rate_limited(gated: TestClient) -> None:
    with gated as client:
        for _ in range(invite.ATTEMPTS_PER_HOUR):
            assert client.post("/invite", data={"code": "guess"}).status_code == 401
        blocked = client.post("/invite", data={"code": "alpha-123"}, follow_redirects=False)
    assert blocked.status_code == 429


# --- daily spending cap ---


def test_the_cap_is_checked_before_the_call(tmp_path: Path) -> None:
    clock = Clock()
    daily = DailySpend(tmp_path / "spend.sqlite", cap_usd=0.03, clock=clock)
    transport = Counting(cost=0.01)
    gw = _gateway(tmp_path, transport, daily=daily)
    with pytest.raises(ParseError):
        _complete(gw)  # worst case 0.02 fits; it costs 0.01
    assert daily.spent_today() == pytest.approx(0.01)
    with pytest.raises(ParseError):
        _complete(gw)  # 0.01 + 0.02 fits
    with pytest.raises(DailyCapReachedError) as info:
        _complete(gw)  # 0.02 + 0.02 does not
    assert transport.calls == 2
    assert str(info.value) == CAP_REACHED


def test_spend_survives_a_restart_and_resets_the_next_day(tmp_path: Path) -> None:
    clock = Clock()
    path = tmp_path / "spend.sqlite"
    first = DailySpend(path, cap_usd=1.0, clock=clock)
    day = first.reserve(0.5)
    first.settle(day, 0.5, 0.4)
    restarted = DailySpend(path, cap_usd=1.0, clock=clock)
    assert restarted.spent_today() == pytest.approx(0.4)
    with pytest.raises(DailyCapReachedError):
        restarted.reserve(0.7)
    clock.now += timedelta(hours=2)  # past midnight UTC
    assert restarted.spent_today() == 0.0
    restarted.reserve(0.7)


def test_a_call_that_fails_gives_its_reservation_back(tmp_path: Path) -> None:
    daily = DailySpend(tmp_path / "spend.sqlite", cap_usd=1.0, clock=Clock())
    gw = _gateway(tmp_path, Counting(fail=True), daily=daily)
    with pytest.raises(ConnectionError):
        _complete(gw)
    assert daily.spent_today() == 0.0


def test_concurrent_reservations_never_pass_the_cap(tmp_path: Path) -> None:
    daily = DailySpend(tmp_path / "spend.sqlite", cap_usd=1.0, clock=Clock())
    granted: list[float] = []
    lock = threading.Lock()

    def take() -> None:
        try:
            daily.reserve(0.3)
        except DailyCapReachedError:
            return
        with lock:
            granted.append(0.3)

    threads = [threading.Thread(target=take) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(granted) == 3
    assert daily.spent_today() == pytest.approx(0.9)


def test_an_ask_past_the_cap_gets_a_plain_503(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    daily = DailySpend(tmp_path / "spend.sqlite", cap_usd=0.01, clock=Clock())
    transport = Counting()
    gateway = _gateway(tmp_path, transport, daily=daily)
    service = AskService(settings, fieldservice_config, gateway, AuditLog(audit_engine), "m")
    with TestClient(create_app(service, web_dir=tmp_path / "none", invite_codes=[])) as client:
        response = client.post("/ask", json={"schema_id": "fieldservice", "question": "q"})
    assert response.status_code == 503
    assert response.json() == {"detail": CAP_REACHED}
    assert transport.calls == 0


# --- kill switch ---


def test_the_kill_switch_stops_every_live_call(tmp_path: Path) -> None:
    transport = Counting()
    with pytest.raises(LiveAnswersOffError):
        _complete(_gateway(tmp_path, transport, off=True))
    assert transport.calls == 0


def test_the_kill_switch_answers_with_a_plain_message(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    transport = Counting()
    gateway = _gateway(tmp_path, transport, off=True)
    service = AskService(settings, fieldservice_config, gateway, AuditLog(audit_engine), "m")
    with TestClient(create_app(service, web_dir=tmp_path / "none", invite_codes=[])) as client:
        response = client.post("/ask", json={"schema_id": "fieldservice", "question": "q"})
    assert response.status_code == 503
    assert response.json() == {"detail": LIVE_ANSWERS_OFF}
    assert transport.calls == 0


def test_settings_turn_on_the_cap_and_the_kill_switch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        service_module.PriceBook, "fetch", lambda *_a, **_k: service_module.PriceBook({})
    )
    monkeypatch.setenv("LEDGERLINE_LIVE_ANSWERS_OFF", "1")
    monkeypatch.setenv("LEDGERLINE_DAILY_SPEND_CAP_USD", "2.5")
    monkeypatch.setenv("LEDGERLINE_SPEND_DB", str(tmp_path / "spend.sqlite"))
    settings = Settings(OPENROUTER_API_KEY=SecretStr("sk-test"))  # type: ignore[call-arg]
    gateway = build_gateway(settings, "live")
    assert gateway.live_answers_off is True
    assert gateway.daily is not None
    assert gateway.daily.cap_usd == 2.5
    assert gateway.daily.path == tmp_path / "spend.sqlite"
