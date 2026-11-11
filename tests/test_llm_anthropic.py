"""The direct Anthropic API transport, against a mocked HTTP server: the request it sends,
how it reads each kind of answer, which errors it retries, and that every billed call
reaches the run budget and the beta's daily cap.

A model is routed to this transport by its configured name: `anthropic:<model id>`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest
from ledgerline.llm.anthropic_transport import AnthropicTransport
from ledgerline.llm.providers import ProviderRouter, split_model
from pydantic import BaseModel, SecretStr

from ledgerline.config import Settings
from ledgerline.llm.budget import BudgetGuard
from ledgerline.llm.daily import DailySpend
from ledgerline.llm.errors import ParseError, ProviderUnavailableError
from ledgerline.llm.gateway import Gateway
from ledgerline.llm.replay import ReplayStore
from ledgerline.llm.types import ChatMessage

MODEL = "anthropic:claude-haiku-5-5"
MESSAGES = [
    ChatMessage(role="system", content="Fill in the form."),
    ChatMessage(role="user", content="label it"),
]
# 1,000 input tokens x $0.10/M + 200 output tokens x $0.50/M.
COST = 1000 * 0.10e-6 + 200 * 0.50e-6


class Answer(BaseModel):
    label: str
    score: int


def _message(
    text: str = '{"label": "a", "score": 2}',
    stop_reason: str = "end_turn",
    thinking: bool = False,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if thinking:
        content.append({"type": "thinking", "thinking": "hmm", "signature": "sig"})
    if text:
        content.append({"type": "text", "text": text})
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1000, "output_tokens": 200},
    }


class Server:
    """Answers each request with the next scripted reply and keeps every request body."""

    def __init__(self, replies: list[httpx2.Response | Exception]) -> None:
        self.replies = list(replies)
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.bodies.append(json.loads(request.content))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def ok(**kw: Any) -> httpx2.Response:
    return httpx2.Response(200, json=_message(**kw))


def error(status: int) -> httpx2.Response:
    body = {"type": "error", "error": {"type": "api_error", "message": f"status {status}"}}
    return httpx2.Response(status, json=body)


def _settings(**overrides: Any) -> Settings:
    return Settings(  # type: ignore[call-arg]
        ANTHROPIC_API_KEY=SecretStr("sk-ant-test"), OPENROUTER_API_KEY=None, **overrides
    )


def _transport(server: Server, sleeps: list[float] | None = None) -> AnthropicTransport:
    client = httpx2.Client(transport=httpx2.MockTransport(server))
    record = sleeps if sleeps is not None else []
    return AnthropicTransport(_settings(), http_client=client, sleep=record.append)


def _gateway(server: Server, daily: DailySpend | None = None, tmp: Path | None = None) -> Gateway:
    router = ProviderRouter(_settings(), anthropic=_transport(server), openrouter_prices=None)
    return Gateway(
        mode="live",
        store=ReplayStore((tmp or Path("/nonexistent")) / "replay.jsonl"),
        transport=router,
        price_lookup=router.price,
        guard=BudgetGuard(1.0),
        max_tokens=1024,
        backoff_sleep=lambda _s: None,
        daily=daily,
    )


def _complete(gw: Gateway) -> Any:
    return gw.complete(model=MODEL, prompt_version="v1", messages=MESSAGES, schema=Answer)


# --- routing ---


def test_the_provider_comes_from_the_configured_name() -> None:
    assert split_model("anthropic:claude-haiku-5-5") == ("anthropic", "claude-haiku-5-5")
    assert split_model("google/gemma-4-26b-a4b-it") == ("openrouter", "google/gemma-4-26b-a4b-it")
    # OpenRouter's own variants use a colon after the vendor; they stay on OpenRouter.
    assert split_model("openai/gpt-4o-mini:batch") == ("openrouter", "openai/gpt-4o-mini:batch")


def test_anthropic_models_are_priced_from_config() -> None:
    router = ProviderRouter(
        _settings(ANTHROPIC_INPUT_USD_PER_MTOK=0.2, ANTHROPIC_OUTPUT_USD_PER_MTOK=1.0),
        anthropic=None,
        openrouter_prices=None,
    )
    price = router.price(MODEL)
    assert price is not None
    assert price.prompt_per_token == pytest.approx(0.2e-6)
    assert price.completion_per_token == pytest.approx(1.0e-6)


# --- the request ---


def test_the_request_uses_structured_output_low_effort_and_no_sampling_settings() -> None:
    server = Server([ok()])
    raw = _transport(server)(
        model="claude-haiku-5-5",
        messages=MESSAGES,
        schema_name="Answer",
        schema=Answer.model_json_schema(),
        max_tokens=1024,
    )
    body = server.bodies[0]
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == 1024
    assert body["system"] == "Fill in the form."
    assert body["messages"] == [{"role": "user", "content": "label it"}]
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["format"]["schema"]["properties"].keys() == {"label", "score"}
    assert body["thinking"] == {"type": "adaptive"}
    for absent in ("temperature", "top_p", "top_k", "output_format"):
        assert absent not in body, absent
    assert raw.parsed == {"label": "a", "score": 2}
    assert raw.usage == {"prompt_tokens": 1000, "completion_tokens": 200}


def test_the_router_sends_the_bare_model_id(tmp_path: Path) -> None:
    server = Server([ok()])
    result = _complete(_gateway(server, tmp=tmp_path))
    assert server.bodies[0]["model"] == "claude-haiku-5-5"
    assert result.value == Answer(label="a", score=2)


# --- answers ---


def test_thinking_blocks_are_skipped_when_reading_the_answer(tmp_path: Path) -> None:
    result = _complete(_gateway(Server([ok(thinking=True)]), tmp=tmp_path))
    assert result.value == Answer(label="a", score=2)


def test_a_parsed_answer_is_charged_from_usage(tmp_path: Path) -> None:
    gw = _gateway(Server([ok()]), tmp=tmp_path)
    result = _complete(gw)
    assert result.cost_usd == pytest.approx(COST)
    assert gw.guard is not None
    assert gw.guard.spent_usd == pytest.approx(COST)


@pytest.mark.parametrize(
    ("stop_reason", "text", "reason"),
    [
        ("max_tokens", '{"label": "a", "sco', "max_tokens"),
        ("refusal", "", "refused"),
    ],
)
def test_max_tokens_and_refusal_are_charged_then_parse_errors(
    tmp_path: Path, stop_reason: str, text: str, reason: str
) -> None:
    gw = _gateway(Server([ok(text=text, stop_reason=stop_reason)]), tmp=tmp_path)
    with pytest.raises(ParseError) as info:
        _complete(gw)
    assert reason in info.value.reason
    assert info.value.cost_usd == pytest.approx(COST)
    assert gw.guard is not None
    assert gw.guard.spent_usd == pytest.approx(COST)


def test_a_cut_off_answer_never_parses_even_if_its_text_is_valid(tmp_path: Path) -> None:
    gw = _gateway(Server([ok(stop_reason="max_tokens")]), tmp=tmp_path)
    with pytest.raises(ParseError):
        _complete(gw)


def test_every_billed_call_reaches_the_daily_cap(tmp_path: Path) -> None:
    daily = DailySpend(
        tmp_path / "spend.sqlite", cap_usd=1.0, clock=lambda: datetime(2026, 11, 11, tzinfo=UTC)
    )
    server = Server([ok(), ok(stop_reason="max_tokens"), ok(text="", stop_reason="refusal")])
    gw = _gateway(server, daily=daily, tmp=tmp_path)
    _complete(gw)
    for _ in range(2):
        with pytest.raises(ParseError):
            _complete(gw)
    assert daily.spent_today() == pytest.approx(3 * COST)


# --- retries ---


@pytest.mark.parametrize(
    "failure",
    [error(429), error(500), error(529), httpx2.ConnectError("refused")],
    ids=["429", "500", "529-overloaded", "connection"],
)
def test_rate_limits_server_errors_and_connection_errors_are_retried(failure: Any) -> None:
    sleeps: list[float] = []
    server = Server([failure, ok()])
    raw = _transport(server, sleeps)(
        model="claude-haiku-5-5",
        messages=MESSAGES,
        schema_name="Answer",
        schema=Answer.model_json_schema(),
        max_tokens=1024,
    )
    assert raw.parsed == {"label": "a", "score": 2}
    assert len(server.bodies) == 2
    assert len(sleeps) == 1


def test_a_400_is_never_retried() -> None:
    import anthropic

    server = Server([error(400), ok()])
    with pytest.raises(anthropic.BadRequestError):
        _transport(server)(
            model="claude-haiku-5-5",
            messages=MESSAGES,
            schema_name="Answer",
            schema=Answer.model_json_schema(),
            max_tokens=1024,
        )
    assert len(server.bodies) == 1


def test_giving_up_is_one_typed_error_the_gateway_does_not_retry_again(tmp_path: Path) -> None:
    server = Server([error(429)] * 10)
    gw = _gateway(server, tmp=tmp_path)
    with pytest.raises(ProviderUnavailableError):
        _complete(gw)
    retries = AnthropicTransport.RETRIES
    assert len(server.bodies) == retries + 1
    assert gw.guard is not None
    assert gw.guard.spent_usd == 0.0


def test_the_transport_refuses_without_a_key() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicTransport(Settings(ANTHROPIC_API_KEY=None))  # type: ignore[call-arg]


# --- wiring ---


def test_the_kill_switch_stops_anthropic_calls_too(tmp_path: Path) -> None:
    from ledgerline.llm.errors import LiveAnswersOffError

    server = Server([ok()])
    gw = _gateway(server, tmp=tmp_path)
    gw.live_answers_off = True
    with pytest.raises(LiveAnswersOffError):
        _complete(gw)
    assert server.bodies == []


def test_build_gateway_routes_by_provider_without_an_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ledgerline.pipeline import service as service_module

    monkeypatch.setattr(
        service_module.PriceBook, "fetch", lambda *_a, **_k: service_module.PriceBook({})
    )
    gateway = service_module.build_gateway(_settings(), "live")
    assert isinstance(gateway.transport, ProviderRouter)
    assert gateway.price_lookup(MODEL) is not None
    assert gateway.price_lookup("google/gemma-4-26b-a4b-it") is None  # not in the empty book
