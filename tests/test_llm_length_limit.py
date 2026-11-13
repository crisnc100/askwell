"""An answer cut off at max_tokens is billed, so its cost must reach the budget.

The OpenAI SDK raises `LengthFinishReasonError` for such an answer. These tests drive
the real transport against a mocked HTTP server and check that the gateway charges the
call and turns it into a `ParseError`, which the pipeline already treats as one failed
attempt.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from askwell.config import Settings
from askwell.llm.budget import BudgetGuard, Checkpoint, ItemResult, run_checkpointed
from askwell.llm.errors import ParseError
from askwell.llm.gateway import Gateway, OpenRouterTransport, parse_output
from askwell.llm.pricing import ModelPrice
from askwell.llm.replay import ReplayStore
from askwell.llm.types import ChatMessage, RawResponse

MODEL = "test/model-a"
MESSAGES = [ChatMessage(role="user", content="label it")]


class Answer(BaseModel):
    label: str
    score: int


def _cut_off(request: httpx.Request) -> httpx.Response:
    body = {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": "length",
                "message": {"role": "assistant", "content": '{"label": "a", "sco'},
            }
        ],
        "usage": {
            "prompt_tokens": 40,
            "completion_tokens": 64,
            "total_tokens": 104,
            "cost": 0.0123,
        },
    }
    return httpx.Response(200, json=body)


def _gateway(tmp_path: Path, mode: str = "live", guard: BudgetGuard | None = None) -> Gateway:
    settings = Settings(OPENROUTER_API_KEY=SecretStr("sk-test"))  # type: ignore[call-arg]
    client = httpx.Client(transport=httpx.MockTransport(_cut_off))
    return Gateway(
        mode=mode,  # type: ignore[arg-type]
        store=ReplayStore(tmp_path / "replay.jsonl"),
        transport=OpenRouterTransport(settings, http_client=client),
        price_lookup=lambda _m: ModelPrice(1e-6, 1e-6),
        guard=guard or BudgetGuard(1.0),
        max_tokens=64,
        backoff_sleep=lambda _s: None,
    )


def _complete(gw: Gateway, guard: BudgetGuard | None = None):
    return gw.complete(
        model=MODEL, prompt_version="v1", messages=MESSAGES, schema=Answer, guard=guard
    )


def test_transport_returns_a_cut_off_answer_with_its_usage(tmp_path: Path) -> None:
    gw = _gateway(tmp_path)
    assert gw.transport is not None
    raw = gw.transport(
        model=MODEL,
        messages=MESSAGES,
        schema_name="Answer",
        schema=Answer.model_json_schema(),
        max_tokens=64,
    )
    assert raw.finish_reason == "length"
    assert raw.parsed is None
    assert raw.content == '{"label": "a", "sco'
    assert raw.usage["completion_tokens"] == 64
    assert raw.usage["cost"] == pytest.approx(0.0123)


def test_a_cut_off_answer_is_charged_and_raises_parse_error(tmp_path: Path) -> None:
    gw = _gateway(tmp_path)
    with pytest.raises(ParseError) as info:
        _complete(gw)
    assert "max_tokens" in info.value.reason
    assert info.value.cost_usd == pytest.approx(0.0123)
    assert gw.guard is not None
    assert gw.guard.spent_usd == pytest.approx(0.0123)


def test_a_recorded_cut_off_answer_replays_as_the_same_parse_error(tmp_path: Path) -> None:
    with pytest.raises(ParseError):
        _complete(_gateway(tmp_path, mode="record"))
    record = json.loads((tmp_path / "replay.jsonl").read_text().splitlines()[0])["record"]
    replayer = Gateway(
        mode="replay",
        store=ReplayStore(tmp_path / "replay.jsonl"),
        transport=None,
        price_lookup=lambda _m: None,
        guard=None,
        max_tokens=64,
    )
    with pytest.raises(ParseError) as info:
        _complete(replayer)
    assert "max_tokens" in info.value.reason
    assert record["cost_usd"] == pytest.approx(0.0123)


def test_spend_from_a_cut_off_call_reaches_the_run_budget(tmp_path: Path) -> None:
    gw = _gateway(tmp_path)
    checkpoint = Checkpoint(tmp_path / "run.jsonl")

    def work(item: str, guard: BudgetGuard) -> ItemResult:
        try:
            _complete(gw, guard=guard)
        except ParseError as exc:
            return ItemResult(record={"item": item, "outcome": "refused"}, cost_usd=exc.cost_usd)
        raise AssertionError("a cut-off answer must not parse")

    outcome = run_checkpointed(["q1", "q2"], str, work, checkpoint, budget_usd=1.0)

    assert not outcome.aborted
    assert outcome.newly_completed == 2
    assert outcome.spent_usd == pytest.approx(2 * 0.0123)
    _, recorded = checkpoint.load()
    assert recorded == pytest.approx(2 * 0.0123)


def test_cut_off_answers_are_never_parsed_even_if_the_text_is_valid() -> None:
    raw = RawResponse(
        content='{"label": "a", "score": 1}', usage={}, model=MODEL, finish_reason="length"
    )
    with pytest.raises(ParseError):
        parse_output(raw, Answer)
