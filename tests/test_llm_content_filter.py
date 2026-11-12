"""An answer the provider's content filter blocked is still billed, so its cost must
reach the run budget and the beta's daily cap.

The OpenAI SDK raises `ContentFilterFinishReasonError` for such an answer. These tests
drive the real transport against a mocked HTTP server and check that the gateway
charges the call and turns it into a `ParseError`, which the pipeline already treats
as one failed attempt.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from askwell.config import Settings
from askwell.llm.budget import BudgetGuard
from askwell.llm.daily import DailySpend
from askwell.llm.errors import ParseError
from askwell.llm.gateway import Gateway, OpenRouterTransport
from askwell.llm.pricing import ModelPrice
from askwell.llm.replay import ReplayStore
from askwell.llm.types import ChatMessage

MODEL = "test/model-a"
MESSAGES = [ChatMessage(role="user", content="label it")]
COST = 0.0042


class Answer(BaseModel):
    label: str
    score: int


def _filtered(request: httpx.Request) -> httpx.Response:
    body = {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": "content_filter",
                "message": {"role": "assistant", "content": ""},
            }
        ],
        "usage": {"prompt_tokens": 40, "completion_tokens": 3, "total_tokens": 43, "cost": COST},
    }
    return httpx.Response(200, json=body)


def _gateway(tmp_path: Path, daily: DailySpend | None = None) -> Gateway:
    settings = Settings(OPENROUTER_API_KEY=SecretStr("sk-test"))  # type: ignore[call-arg]
    client = httpx.Client(transport=httpx.MockTransport(_filtered))
    return Gateway(
        mode="live",
        store=ReplayStore(tmp_path / "replay.jsonl"),
        transport=OpenRouterTransport(settings, http_client=client),
        price_lookup=lambda _m: ModelPrice(1e-6, 1e-6),
        guard=BudgetGuard(1.0),
        max_tokens=64,
        backoff_sleep=lambda _s: None,
        daily=daily,
    )


def _complete(gw: Gateway) -> None:
    gw.complete(model=MODEL, prompt_version="v1", messages=MESSAGES, schema=Answer)


def test_transport_returns_a_filtered_answer_with_its_usage(tmp_path: Path) -> None:
    gw = _gateway(tmp_path)
    assert gw.transport is not None
    raw = gw.transport(
        model=MODEL,
        messages=MESSAGES,
        schema_name="Answer",
        schema=Answer.model_json_schema(),
        max_tokens=64,
    )
    assert raw.finish_reason == "content_filter"
    assert raw.parsed is None
    assert raw.usage["cost"] == pytest.approx(COST)


def test_a_filtered_answer_is_charged_and_raises_parse_error(tmp_path: Path) -> None:
    gw = _gateway(tmp_path)
    with pytest.raises(ParseError) as info:
        _complete(gw)
    assert "content filter" in info.value.reason
    assert info.value.cost_usd == pytest.approx(COST)
    assert gw.guard is not None
    assert gw.guard.spent_usd == pytest.approx(COST)


def test_a_filtered_answer_counts_against_the_daily_cap(tmp_path: Path) -> None:
    daily = DailySpend(
        tmp_path / "spend.sqlite", cap_usd=1.0, clock=lambda: datetime(2026, 11, 11, tzinfo=UTC)
    )
    with pytest.raises(ParseError):
        _complete(_gateway(tmp_path, daily=daily))
    assert daily.spent_today() == pytest.approx(COST)
