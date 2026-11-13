"""L26: the public site's global daily spending cap and kill switch."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr
from sqlalchemy import Engine

from askwell.api import create_app
from askwell.config import Settings
from askwell.core.audit import AuditLog
from askwell.llm.budget import BudgetGuard
from askwell.llm.daily import CAP_REACHED, DailyCapReachedError, DailySpend
from askwell.llm.errors import LIVE_ANSWERS_OFF, LiveAnswersOffError, ParseError
from askwell.llm.gateway import Gateway
from askwell.llm.pricing import ModelPrice
from askwell.llm.replay import ReplayStore
from askwell.llm.types import ChatMessage, RawResponse
from askwell.pipeline import service as service_module
from askwell.pipeline.service import AskService, SchemaConfig, build_gateway


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
    with TestClient(create_app(service, web_dir=tmp_path / "none")) as client:
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
    with TestClient(create_app(service, web_dir=tmp_path / "none")) as client:
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
    monkeypatch.setenv("ASKWELL_LIVE_ANSWERS_OFF", "1")
    monkeypatch.setenv("ASKWELL_DAILY_SPEND_CAP_USD", "2.5")
    monkeypatch.setenv("ASKWELL_SPEND_DB", str(tmp_path / "spend.sqlite"))
    settings = Settings(OPENROUTER_API_KEY=SecretStr("sk-test"))  # type: ignore[call-arg]
    gateway = build_gateway(settings, "live")
    assert gateway.live_answers_off is True
    assert gateway.daily is not None
    assert gateway.daily.cap_usd == 2.5
    assert gateway.daily.path == tmp_path / "spend.sqlite"
