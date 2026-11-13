"""The public site is open to anyone (owner's decision, 2026-11-13). What protects spend
and abuse stays, and a limit shows only when it is hit, as one plain message, and then
nothing runs: no model call and no partial work."""

from __future__ import annotations

import importlib.util
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from askwell.api import create_app
from askwell.config import get_settings
from askwell.llm.budget import BudgetGuard
from askwell.llm.daily import CAP_REACHED, DailyCapReachedError, DailySpend
from askwell.llm.gateway import Gateway
from askwell.llm.pricing import ModelPrice
from askwell.llm.replay import ReplayStore
from askwell.workspace.api import HEADER, WorkspaceApp
from askwell.workspace.limits import Limits, RateLimiter, wait_words
from askwell.workspace.store import WorkspaceStore
from tests.workspace.conftest import FakeClock, _NoService, upload, upload_sample
from tests.workspace.fake_model import FakeModel, fake_service

COUNT_ORDERS = {"intent_type": "summary", "entity": "orders", "metrics": [{"agg": "count"}]}


@pytest.fixture
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    get_settings.cache_clear()
    yield monkeypatch
    monkeypatch.undo()
    get_settings.cache_clear()


def _app(tmp_path: Path) -> Any:
    web = tmp_path / "web"
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text("<p>the app</p>", encoding="utf-8")
    store = WorkspaceStore(tmp_path / "ws", Limits(), FakeClock())
    return create_app(service=_NoService(), workspaces=WorkspaceApp(store), web_dir=web)  # type: ignore[arg-type]


# --- no invite gate ---


def test_no_page_or_route_needs_a_code(tmp_path: Path) -> None:
    assert importlib.util.find_spec("askwell.invite") is None
    with TestClient(_app(tmp_path)) as client:
        page = client.get("/", headers={"accept": "text/html"})
        assert page.status_code == 200
        assert "the app" in page.text
        assert client.get("/api/limits").status_code == 200
        assert client.post("/api/workspaces", json={}).status_code == 201
        assert client.get("/invite").status_code == 404


@pytest.mark.parametrize("name", ["ASKWELL_INVITE_CODES", "LEDGERLINE_INVITE_CODES"])
def test_an_invite_codes_setting_is_ignored_with_a_warning(
    fresh_settings: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    name: str,
) -> None:
    fresh_settings.setenv(name, "alpha-123")
    with caplog.at_level(logging.WARNING):
        app = _app(tmp_path)
    assert "ASKWELL_INVITE_CODES is set but ignored" in caplog.text
    assert "alpha-123" not in caplog.text
    with TestClient(app) as client:
        assert client.get("/api/limits").status_code == 200


def test_a_live_site_with_no_daily_cap_refuses_to_start(
    fresh_settings: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fresh_settings.chdir(tmp_path)  # away from the repository's .env
    fresh_settings.setenv("ASKWELL_LLM_MODE", "live")
    fresh_settings.delenv("ASKWELL_DAILY_SPEND_CAP_USD", raising=False)
    fresh_settings.delenv("LEDGERLINE_DAILY_SPEND_CAP_USD", raising=False)
    with pytest.raises(RuntimeError, match="ASKWELL_DAILY_SPEND_CAP_USD"):
        _app(tmp_path)
    fresh_settings.setenv("ASKWELL_DAILY_SPEND_CAP_USD", "1.00")
    get_settings.cache_clear()
    with TestClient(_app(tmp_path)) as client:
        assert client.get("/api/limits").status_code == 200


def test_a_beta_deployment_starts_without_codes(
    fresh_settings: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fresh_settings.setenv("ASKWELL_ENV", "beta")
    fresh_settings.delenv("ASKWELL_INVITE_CODES", raising=False)
    with caplog.at_level(logging.WARNING):
        app = _app(tmp_path)
    assert "INVITE_CODES" not in caplog.text
    with TestClient(app) as client:
        assert client.get("/api/limits").status_code == 200


# --- the daily cap: one plain message, refused before any call ---


def test_the_daily_cap_message() -> None:
    assert CAP_REACHED == "Askwell has hit today's limit. Try again tomorrow."
    assert str(DailyCapReachedError(1, 1, 1)) == CAP_REACHED


def _live_gateway(tmp_path: Path, daily: DailySpend) -> Gateway:
    return Gateway(
        mode="live",
        store=ReplayStore(tmp_path / "s.jsonl"),
        transport=lambda **_: None,  # type: ignore[arg-type,return-value]
        price_lookup=lambda _m: ModelPrice(0.0, 0.00002),
        guard=BudgetGuard(10.0),
        max_tokens=1000,
        daily=daily,
    )


def test_an_ask_holds_its_whole_budget_and_gives_back_what_it_did_not_spend(
    tmp_path: Path,
) -> None:
    daily = DailySpend(tmp_path / "spend.sqlite", cap_usd=1.0)
    gateway = _live_gateway(tmp_path, daily)
    guard = BudgetGuard(0.05)
    with gateway.reserve_ask(guard):
        assert daily.spent_today() == pytest.approx(0.05)
        guard.charge(0.01)
    assert daily.spent_today() == pytest.approx(0.01)

    failing = BudgetGuard(0.05)

    def fail_partway() -> None:
        with gateway.reserve_ask(failing):
            failing.charge(0.02)
            raise RuntimeError("the ask failed")

    with pytest.raises(RuntimeError):
        fail_partway()
    assert daily.spent_today() == pytest.approx(0.03)


def test_an_ask_the_cap_could_not_finish_is_refused_before_any_call(tmp_path: Path) -> None:
    daily = DailySpend(tmp_path / "spend.sqlite", cap_usd=1.0)
    day = daily.reserve(0.97)
    daily.settle(day, 0.97, 0.97)
    gateway = _live_gateway(tmp_path, daily)
    with pytest.raises(DailyCapReachedError), gateway.reserve_ask(BudgetGuard(0.05)):
        pytest.fail("the ask must not start")
    with gateway.reserve_ask(BudgetGuard(0.03)):  # exactly to the cap still fits
        pass
    assert daily.spent_today() == pytest.approx(0.97)  # nothing was spent


class _CapReached(FakeModel):
    @contextmanager
    def reserve_ask(self, guard: BudgetGuard) -> Iterator[None]:
        raise DailyCapReachedError(1.0, guard.limit_usd, 1.0)
        yield


def test_a_workspace_ask_past_the_cap_makes_no_call(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "ws", Limits(), FakeClock())
    model = _CapReached({"How many orders?": COUNT_ORDERS})
    app = create_app(service=fake_service(get_settings(), model), workspaces=WorkspaceApp(store))
    with TestClient(app) as client:
        headers = {HEADER: client.post("/api/workspaces", json={}).json()["id"]}
        upload_sample(client, headers)
        client.post("/api/workspace/check", headers=headers)
        client.post("/api/workspace/confirm", json={"fields": {}}, headers=headers)
        response = client.post(
            "/api/workspace/ask", json={"question": "How many orders?"}, headers=headers
        )
    assert response.status_code == 503
    assert response.json() == {"detail": CAP_REACHED}
    assert model.calls == []


# --- per-address limits: when to retry, never a count ---


def test_retry_after_is_when_the_oldest_event_leaves_the_window() -> None:
    now = [100.0]
    limiter = RateLimiter(2, 3600.0, clock=lambda: now[0])
    assert limiter.retry_after("a") == 0.0
    assert limiter.allow("a")
    now[0] = 400.0
    assert limiter.allow("a")
    assert not limiter.allow("a")
    assert limiter.retry_after("a") == pytest.approx(3600.0 - 300.0)


@pytest.mark.parametrize(
    ("seconds", "words"),
    [
        (5, "in a minute"),
        (60, "in a minute"),
        (61, "in 2 minutes"),
        (59 * 60, "in 59 minutes"),
        (3600, "in an hour"),
        (3601, "in 2 hours"),
        (47 * 3600, "in 47 hours"),
        (7 * 86400, "in 7 days"),
    ],
)
def test_wait_words(seconds: float, words: str) -> None:
    assert wait_words(seconds) == words


@pytest.fixture
def limited(tmp_path: Path) -> Iterator[tuple[TestClient, FakeModel]]:
    limits = Limits(asks_per_hour=1, uploads_per_hour=5, checks_per_hour=1)
    store = WorkspaceStore(tmp_path / "ws", limits, FakeClock())
    model = FakeModel({"How many orders?": COUNT_ORDERS})
    app = create_app(service=fake_service(get_settings(), model), workspaces=WorkspaceApp(store))
    with TestClient(app) as client:
        yield client, model


def _plain(detail: str) -> None:
    assert "limit" not in detail.lower()
    assert not re.search(r"\d", detail), detail
    assert re.search(r"Try again in (a minute|an hour)\.$", detail), detail


def test_the_question_limit_says_when_to_retry_and_makes_no_call(
    limited: tuple[TestClient, FakeModel],
) -> None:
    client, model = limited
    headers = {HEADER: client.post("/api/workspaces", json={}).json()["id"]}
    upload_sample(client, headers)
    client.post("/api/workspace/check", headers=headers)
    client.post("/api/workspace/confirm", json={"fields": {}}, headers=headers)
    ok = client.post("/api/workspace/ask", json={"question": "How many orders?"}, headers=headers)
    assert ok.status_code == 200
    calls = len(model.calls)
    refused = client.post(
        "/api/workspace/ask", json={"question": "How many orders?"}, headers=headers
    )
    assert refused.status_code == 429
    detail = refused.json()["detail"]
    assert detail == "You've asked a lot of questions in the last hour. Try again in an hour."
    _plain(detail)
    assert len(model.calls) == calls


def test_the_upload_and_check_limits_say_when_to_retry_and_store_nothing(
    tmp_path: Path,
) -> None:
    limits = Limits(uploads_per_hour=1, checks_per_hour=1)
    store = WorkspaceStore(tmp_path / "ws", limits, FakeClock())
    app = create_app(service=_NoService(), workspaces=WorkspaceApp(store))  # type: ignore[arg-type]
    with TestClient(app) as client:
        headers = {HEADER: client.post("/api/workspaces", json={}).json()["id"]}
        assert upload(client, headers, "a.csv", b"id,x\n1,2\n") == 200
        second = client.put(
            "/api/workspace/files",
            content=b"id,y\n1,2\n",
            headers={**headers, "X-File-Name": "b.csv"},
        )
        assert second.status_code == 429
        assert second.json()["detail"] == (
            "You've uploaded a lot of files in the last hour. Try again in an hour."
        )
        _plain(second.json()["detail"])
        names = [f["name"] for f in client.get("/api/workspace", headers=headers).json()["files"]]
        assert names == ["a.csv"]

        assert client.post("/api/workspace/check", headers=headers).status_code == 200
        again = client.post("/api/workspace/check", headers=headers)
        assert again.status_code == 429
        assert again.json()["detail"] == (
            "You've run a lot of checks in the last hour. Try again in an hour."
        )
        _plain(again.json()["detail"])


def test_the_limits_route_shows_no_quotas(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        body = client.get("/api/limits").json()
    assert not any("hour" in key or "per_ip" in key or "remaining" in key for key in body)
