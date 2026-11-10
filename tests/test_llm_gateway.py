"""Model gateway: parse fallback, replay (incl. miss), cost, budget pre-check, 429 backoff."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from ledgerline.llm.budget import BudgetGuard
from ledgerline.llm.errors import (
    BudgetExceededError,
    ParseError,
    PricingUnavailableError,
    RateLimitedError,
    ReplayMissError,
)
from ledgerline.llm.gateway import Gateway, parse_output
from ledgerline.llm.pricing import ModelPrice, PriceBook, cost_from_usage, worst_case_cost
from ledgerline.llm.replay import ReplayStore, TrajectoryStore, replay_key, trajectory_key
from ledgerline.llm.types import ChatMessage, RawResponse

MODEL = "test/model-a"
PRICE = ModelPrice(prompt_per_token=1e-6, completion_per_token=2e-6)
MESSAGES = [ChatMessage(role="system", content="sys"), ChatMessage(role="user", content="q?")]


class Answer(BaseModel):
    label: str
    score: int


class FakeTransport:
    def __init__(self, responses: list[RawResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> RawResponse:
        self.calls.append(kwargs)
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class Http429Error(Exception):
    status_code = 429


def ok(parsed: dict[str, Any] | None = None, content: str = "", cost: float | None = 0.001):
    usage: dict[str, Any] = {"prompt_tokens": 100, "completion_tokens": 20}
    if cost is not None:
        usage["cost"] = cost
    return RawResponse(content=content, parsed=parsed, usage=usage, model=MODEL)


def gateway(
    mode: str,
    tmp_path: Path,
    transport: FakeTransport | None = None,
    limit: float = 1.0,
    price: ModelPrice | None = PRICE,
) -> Gateway:
    return Gateway(
        mode=mode,  # type: ignore[arg-type]
        store=ReplayStore(tmp_path / "replay.jsonl"),
        transport=transport,
        price_lookup=lambda _m: price,
        guard=BudgetGuard(limit),
        max_tokens=100,
        backoff_sleep=lambda _s: None,
    )


def complete(gw: Gateway, messages: list[ChatMessage] = MESSAGES):
    return gw.complete(model=MODEL, prompt_version="v1", messages=messages, schema=Answer)


# --- parsing ---


def test_provider_parse_is_validated() -> None:
    assert parse_output(ok({"label": "a", "score": 3}), Answer) == Answer(label="a", score=3)


def test_pydantic_fallback_parses_fenced_json_text() -> None:
    raw = ok(None, content='```json\n{"label": "b", "score": 7}\n```')
    assert parse_output(raw, Answer) == Answer(label="b", score=7)


def test_unparseable_text_is_a_typed_parse_error() -> None:
    with pytest.raises(ParseError) as info:
        parse_output(ok(None, content="Sure! The answer is b."), Answer)
    assert info.value.raw == "Sure! The answer is b."


def test_provider_parse_with_wrong_shape_is_a_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_output(ok({"label": "a"}), Answer)


# --- replay ---


def test_replay_key_changes_with_each_component() -> None:
    schema = Answer.model_json_schema()
    base = replay_key(MODEL, "v1", MESSAGES, schema)
    assert base == replay_key(MODEL, "v1", list(MESSAGES), dict(schema))
    assert base != replay_key("test/model-b", "v1", MESSAGES, schema)
    assert base != replay_key(MODEL, "v2", MESSAGES, schema)
    assert base != replay_key(
        MODEL, "v1", [*MESSAGES[:1], ChatMessage(role="user", content="x")], schema
    )
    assert base != replay_key(MODEL, "v1", MESSAGES, {**schema, "title": "Other"})


def test_record_then_replay_returns_same_value_without_a_call(tmp_path: Path) -> None:
    transport = FakeTransport([ok({"label": "a", "score": 1}, cost=0.0042)])
    recorded = complete(gateway("record", tmp_path, transport))
    assert recorded.cost_source == "openrouter"

    replayed = complete(gateway("replay", tmp_path))
    assert replayed.value == recorded.value
    assert replayed.replayed
    assert replayed.cost_usd == pytest.approx(0.0042)
    assert len(transport.calls) == 1


def test_replay_miss_raises_and_never_calls_live(tmp_path: Path) -> None:
    transport = FakeTransport([ok({"label": "a", "score": 1})])
    gw = Gateway(
        mode="replay",
        store=ReplayStore(tmp_path / "empty.jsonl"),
        transport=transport,
        price_lookup=lambda _m: PRICE,
        guard=BudgetGuard(1.0),
        max_tokens=100,
    )
    with pytest.raises(ReplayMissError):
        complete(gw)
    assert transport.calls == []


def test_replay_reproduces_a_recorded_parse_error(tmp_path: Path) -> None:
    transport = FakeTransport([ok(None, content="not json")])
    with pytest.raises(ParseError):
        complete(gateway("record", tmp_path, transport))
    with pytest.raises(ParseError):
        complete(gateway("replay", tmp_path))


def test_replay_store_persists_across_instances(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "r.jsonl")
    store.put("k1", {"x": 1})
    store.put("k1", {"x": 2})
    reopened = ReplayStore(tmp_path / "r.jsonl")
    assert reopened.get("k1") == {"x": 2}
    assert len(reopened) == 1


def test_live_mode_does_not_record(tmp_path: Path) -> None:
    transport = FakeTransport([ok({"label": "a", "score": 1})])
    complete(gateway("live", tmp_path, transport))
    assert not (tmp_path / "replay.jsonl").exists()


def test_trajectory_replay_is_keyed_by_question_not_messages(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path / "traj.jsonl")
    store.put_trajectory("sql_agent", "fs-001", MODEL, "v1", {"steps": [{"sql": "SELECT 1"}]})
    again = TrajectoryStore(tmp_path / "traj.jsonl")
    assert again.get_trajectory("sql_agent", "fs-001", MODEL, "v1")["steps"][0]["sql"] == "SELECT 1"
    assert trajectory_key("sql_agent", "fs-001", MODEL, "v1") == "sql_agent|fs-001|test/model-a|v1"


def test_trajectory_miss_raises(tmp_path: Path) -> None:
    store = TrajectoryStore(tmp_path / "traj.jsonl")
    store.put_trajectory("sql_agent", "fs-001", MODEL, "v1", {"steps": []})
    with pytest.raises(ReplayMissError):
        store.get_trajectory("sql_agent", "fs-002", MODEL, "v1")
    with pytest.raises(ReplayMissError):
        store.get_trajectory("sql_agent", "fs-001", MODEL, "v2")


def test_trajectory_key_rejects_ambiguous_parts() -> None:
    with pytest.raises(ValueError, match="trajectory key"):
        trajectory_key("sql|agent", "fs-001", MODEL, "v1")


def test_modes_require_their_dependencies(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="replay store"):
        Gateway(
            mode="replay",
            store=None,
            transport=None,
            price_lookup=lambda _m: None,
            guard=None,
            max_tokens=1,
        )
    with pytest.raises(ValueError, match="transport"):
        Gateway(
            mode="live",
            store=None,
            transport=None,
            price_lookup=lambda _m: None,
            guard=BudgetGuard(1),
            max_tokens=1,
        )


# --- cost ---


def test_cost_prefers_openrouter_reported_cost() -> None:
    assert cost_from_usage({"cost": 0.0123, "prompt_tokens": 9}, PRICE) == (0.0123, "openrouter")


def test_cost_is_estimated_from_pricing_without_reported_cost() -> None:
    cost, source = cost_from_usage({"prompt_tokens": 1000, "completion_tokens": 500}, PRICE)
    assert source == "estimated"
    assert cost == pytest.approx(1000 * 1e-6 + 500 * 2e-6)


def test_cost_without_report_or_price_is_an_error() -> None:
    with pytest.raises(PricingUnavailableError):
        cost_from_usage({"prompt_tokens": 1}, None)


def test_price_book_parses_models_endpoint_payload() -> None:
    book = PriceBook.from_models_payload(
        {
            "data": [
                {"id": "a/one", "pricing": {"prompt": "0.0000002", "completion": "0.0000008"}},
                {"id": "a/broken", "pricing": {"prompt": "n/a"}},
            ]
        }
    )
    assert book.require("a/one") == ModelPrice(2e-7, 8e-7)
    assert book.get("a/broken") is None
    with pytest.raises(PricingUnavailableError):
        book.require("a/missing")


def test_gateway_charges_the_guard(tmp_path: Path) -> None:
    transport = FakeTransport([ok({"label": "a", "score": 1}, cost=0.25)])
    gw = gateway("live", tmp_path, transport)
    complete(gw)
    assert gw.guard is not None
    assert gw.guard.spent_usd == pytest.approx(0.25)


# --- budget pre-check ---


def test_worst_case_is_prompt_chars_plus_max_tokens() -> None:
    assert worst_case_cost(PRICE, 1000, 100) == pytest.approx(1000 * 1e-6 + 100 * 2e-6)


def test_precheck_refuses_before_calling_when_worst_case_exceeds_budget(tmp_path: Path) -> None:
    transport = FakeTransport([ok({"label": "a", "score": 1})])
    expensive = ModelPrice(prompt_per_token=1.0, completion_per_token=1.0)
    gw = gateway("live", tmp_path, transport, limit=5.0, price=expensive)
    with pytest.raises(BudgetExceededError):
        complete(gw)
    assert transport.calls == []


def test_precheck_counts_spend_so_far(tmp_path: Path) -> None:
    transport = FakeTransport([ok({"label": "a", "score": 1}, cost=0.0009)] * 2)
    # Worst case per call is under 0.001 at PRICE: the limit fits one call, not two.
    gw = gateway("live", tmp_path, transport, limit=0.0012)
    complete(gw)
    with pytest.raises(BudgetExceededError):
        complete(gw)
    assert len(transport.calls) == 1


def test_unknown_price_refuses_live_call(tmp_path: Path) -> None:
    transport = FakeTransport([ok({"label": "a", "score": 1})])
    with pytest.raises(PricingUnavailableError):
        complete(gateway("live", tmp_path, transport, price=None))
    assert transport.calls == []


# --- 429 backoff ---


def test_rate_limit_is_retried_with_backoff(tmp_path: Path) -> None:
    transport = FakeTransport([Http429Error(), Http429Error(), ok({"label": "a", "score": 1})])
    result = complete(gateway("live", tmp_path, transport))
    assert result.value.label == "a"
    assert len(transport.calls) == 3


def test_rate_limit_gives_up_after_retries(tmp_path: Path) -> None:
    transport = FakeTransport([Http429Error() for _ in range(6)])
    with pytest.raises(RateLimitedError):
        complete(gateway("live", tmp_path, transport))
    assert len(transport.calls) == 6


def test_other_errors_are_not_retried(tmp_path: Path) -> None:
    transport = FakeTransport([RuntimeError("boom"), ok({"label": "a", "score": 1})])
    with pytest.raises(RuntimeError, match="boom"):
        complete(gateway("live", tmp_path, transport))
    assert len(transport.calls) == 1
