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


# --- /healthz ---


def test_healthz_answers_with_no_code(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    service = AskService(
        settings, fieldservice_config, _gateway(tmp_path, Counting()), AuditLog(audit_engine), "m"
    )
    with TestClient(create_app(service, web_dir=tmp_path / "none")) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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


class Blocking:
    """Answers with a valid intent costing $0.01, holding the first call open until
    released, so a second ask can arrive while the first is mid-flight."""

    def __init__(self) -> None:
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, **_: Any) -> RawResponse:
        self.calls += 1
        self.entered.set()
        assert self.release.wait(10)
        intent = '{"intent_type": "summary", "entity": "invoices", "metrics": [{"agg": "count"}]}'
        return RawResponse(content=intent, usage={"cost": 0.01}, model="m")


def test_two_overlapping_asks_cannot_both_hold_the_last_of_the_allowance(
    settings: Settings,
    fieldservice_config: dict[str, SchemaConfig],
    tmp_path: Path,
    audit_engine: Engine,
) -> None:
    assert settings.ask_budget_usd == pytest.approx(0.05)
    daily = DailySpend(tmp_path / "spend.sqlite", cap_usd=0.06, clock=Clock())
    transport = Blocking()
    gateway = _gateway(tmp_path, transport, daily=daily)  # type: ignore[arg-type]
    service = AskService(settings, fieldservice_config, gateway, AuditLog(audit_engine), "m")
    results: list[Any] = []
    first = threading.Thread(
        target=lambda: results.append(service.ask("fieldservice", "How many invoices?"))
    )
    first.start()
    try:
        assert transport.entered.wait(10)
        # The first ask holds $0.05 of the $0.06; the second is refused before any call.
        with pytest.raises(DailyCapReachedError):
            service.ask("fieldservice", "How many invoices are there?")
        assert transport.calls == 1
    finally:
        transport.release.set()
        first.join(10)
    assert len(results) == 1
    assert results[0].refusal is None
    assert results[0].rows
    # The first ask gives back what it did not spend.
    assert daily.spent_today() == pytest.approx(0.01)


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
