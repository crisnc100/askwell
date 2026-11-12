"""PR5 review fixes on the model side: a lost response may have been billed, startup
must not depend on OpenRouter for an Anthropic default, the spike honours the beta's
controls, and a deeply nested answer is a charged ParseError."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx2
import pytest
from pydantic import BaseModel, SecretStr
from typer.testing import CliRunner

from askwell.config import Settings
from askwell.llm.anthropic_transport import AnthropicTransport
from askwell.llm.budget import BudgetGuard
from askwell.llm.daily import DailySpend
from askwell.llm.errors import ParseError
from askwell.llm.gateway import Gateway
from askwell.llm.pricing import worst_case_cost
from askwell.llm.providers import ProviderRouter
from askwell.llm.replay import ReplayStore, canonical_json
from askwell.llm.types import ChatMessage

MODEL = "anthropic:claude-haiku-5-5"
MESSAGES = [ChatMessage(role="user", content="label it")]


class Answer(BaseModel):
    label: str


def _settings(**extra: Any) -> Settings:
    keys: dict[str, Any] = {"ANTHROPIC_API_KEY": SecretStr("sk-ant-test")}
    return Settings(**keys, **extra)


def _ok(text: str = '{"label": "a"}') -> httpx2.Response:
    return httpx2.Response(
        200,
        json={
            "id": "m",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 100, "output_tokens": 10},
        },
    )


class Server:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.calls = 0

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _gateway(tmp_path: Path, server: Server, daily: DailySpend | None = None) -> Gateway:
    client = httpx2.Client(transport=httpx2.MockTransport(server))
    transport = AnthropicTransport(_settings(), http_client=client, sleep=lambda _s: None)
    router = ProviderRouter(_settings(), anthropic=transport, openrouter_prices=None)
    return Gateway(
        mode="live",
        store=ReplayStore(tmp_path / "r.jsonl"),
        transport=router,
        price_lookup=router.price,
        guard=BudgetGuard(1.0),
        max_tokens=1024,
        backoff_sleep=lambda _s: None,
        daily=daily,
    )


def _worst(gw: Gateway) -> float:
    price = gw.price_lookup(MODEL)
    assert price is not None
    prompt_bytes = len(canonical_json([m.model_dump() for m in MESSAGES]).encode("utf-8")) + len(
        canonical_json(Answer.model_json_schema()).encode("utf-8")
    )
    return worst_case_cost(price, prompt_bytes, gw.max_tokens)


def _complete(gw: Gateway) -> Any:
    return gw.complete(model=MODEL, prompt_version="v1", messages=MESSAGES, schema=Answer)


# --- f1: a lost response may have been billed ---


@pytest.mark.parametrize(
    "lost",
    [httpx2.ReadTimeout("read timed out"), httpx2.RemoteProtocolError("connection dropped")],
    ids=["read-timeout", "dropped"],
)
def test_a_lost_response_is_not_retried_and_is_charged_at_its_worst_case(
    tmp_path: Path, lost: Exception
) -> None:
    daily = DailySpend(
        tmp_path / "spend.sqlite", cap_usd=1.0, clock=lambda: datetime(2026, 11, 11, tzinfo=UTC)
    )
    server = Server([lost, _ok()])
    gw = _gateway(tmp_path, server, daily)
    with pytest.raises(Exception):  # noqa: B017, PT011 - the SDK's own type
        _complete(gw)
    assert server.calls == 1
    worst = _worst(gw)
    assert daily.spent_today() == pytest.approx(worst)
    assert gw.guard is not None
    assert gw.guard.spent_usd == pytest.approx(worst)


def test_a_refused_connection_was_never_sent_so_it_is_retried_and_free(tmp_path: Path) -> None:
    daily = DailySpend(
        tmp_path / "spend.sqlite", cap_usd=1.0, clock=lambda: datetime(2026, 11, 11, tzinfo=UTC)
    )
    server = Server([httpx2.ConnectError("refused"), _ok()])
    gw = _gateway(tmp_path, server, daily)
    result = _complete(gw)
    assert server.calls == 2
    assert daily.spent_today() == pytest.approx(result.cost_usd)


# --- f2: startup does not need OpenRouter for an Anthropic default ---


def test_an_anthropic_default_starts_while_openrouter_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from askwell.pipeline import service as service_module

    calls: list[str] = []

    def down(*_a: Any, **_k: Any) -> Any:
        calls.append("fetch")
        raise httpx2.ConnectError("openrouter is down")

    monkeypatch.setattr(service_module.PriceBook, "fetch", down)
    gateway = service_module.build_gateway(_settings(), "live")
    assert gateway.price_lookup(MODEL) is not None
    assert calls == []


# --- f3: the spike honours the kill switch and the daily cap ---


@pytest.mark.parametrize(
    "control",
    [{"live_answers_off": True}, {"daily_spend_cap_usd": 0.0}],
    ids=["kill-switch", "daily-cap"],
)
def test_the_spike_command_honours_the_beta_controls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, control: dict[str, Any]
) -> None:
    import askwell.cli as cli
    import askwell.llm.gateway as gateway_module
    import askwell.llm.spike as spike_module

    calls: list[str] = []

    class Counting:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        def __call__(self, **_k: Any) -> Any:
            calls.append("call")
            raise AssertionError("no call may be made with the kill switch on")

    payload = {"data": [{"id": "x/y", "pricing": {"prompt": "0.000001", "completion": "0.000001"}}]}
    monkeypatch.setattr(spike_module, "fetch_models_payload", lambda _url: payload)
    monkeypatch.setattr(gateway_module, "OpenRouterTransport", Counting)
    values: dict[str, Any] = {
        "OPENROUTER_API_KEY": SecretStr("sk-test"),
        "spend_db": str(tmp_path / "spend.sqlite"),
        **control,
    }
    settings = Settings(**values)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    result = CliRunner().invoke(
        cli.app, ["spike", "--models", "x/y", "--out-dir", str(tmp_path / "out")]
    )
    assert calls == []
    assert result.exit_code == 0, result.output


def test_the_spike_gateway_takes_the_daily_cap(tmp_path: Path) -> None:
    from askwell.llm.spike import make_live_gateway

    daily = DailySpend(tmp_path / "spend.sqlite", cap_usd=0.0)
    options: dict[str, Any] = {"daily": daily, "live_answers_off": True}
    never = cast(Any, lambda **_k: None)
    gateway = make_live_gateway(never, lambda _m: None, 1.0, 100, **options)
    assert gateway.daily is daily
    assert gateway.live_answers_off is True


# --- s1: a deeply nested answer ---


def test_a_deeply_nested_answer_is_a_charged_parse_error(tmp_path: Path) -> None:
    nested = "[" * 200_000 + "]" * 200_000
    gw = _gateway(tmp_path, Server([_ok(text=nested)]))
    with pytest.raises(ParseError) as info:
        _complete(gw)
    assert info.value.cost_usd > 0
    assert json.dumps(info.value.reason)
