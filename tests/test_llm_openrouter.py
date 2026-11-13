"""The OpenRouter transport's request and response handling, against a mocked HTTP server."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from askwell.config import Settings
from askwell.llm.gateway import OpenRouterTransport
from askwell.llm.types import ChatMessage


class Answer(BaseModel):
    label: str
    score: int


def _completion(content: str, usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": "test/model-a",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": usage,
    }


def _transport(handler: Any, **kwargs: Any) -> OpenRouterTransport:
    settings = Settings(OPENROUTER_API_KEY=SecretStr("sk-test"))  # type: ignore[call-arg]
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterTransport(settings, http_client=client, **kwargs)


def _call(transport: OpenRouterTransport):
    return transport(
        model="test/model-a",
        messages=[ChatMessage(role="user", content="label it")],
        schema_name="Answer",
        schema=Answer.model_json_schema(),
        max_tokens=64,
    )


def test_request_pins_structured_output_providers_and_reports_cost() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        usage = {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17, "cost": 0.00042}
        return httpx.Response(200, json=_completion('{"label": "a", "score": 2}', usage))

    raw = _call(_transport(handler, providers=["prov-x"]))

    body = seen[0]
    assert body["model"] == "test/model-a"
    assert body["temperature"] == 0
    assert body["max_tokens"] == 64
    assert "max_completion_tokens" not in body
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "Answer"
    assert body["provider"] == {
        "require_parameters": True,
        "order": ["prov-x"],
        "allow_fallbacks": False,
    }
    assert body["usage"] == {"include": True}

    assert raw.parsed == {"label": "a", "score": 2}
    assert raw.usage["cost"] == pytest.approx(0.00042)
    assert raw.usage["prompt_tokens"] == 12


def test_unparseable_content_comes_back_with_parsed_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        return httpx.Response(200, json=_completion("I cannot do that", usage))

    raw = _call(_transport(handler))
    assert raw.parsed is None
    assert raw.content == "I cannot do that"


def test_rate_limit_surfaces_as_status_429_for_backoff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down", "code": 429}})

    with pytest.raises(Exception) as info:  # noqa: PT011 - the type is the SDK's
        _call(_transport(handler))
    assert getattr(info.value, "status_code", None) == 429


def test_transport_refuses_without_a_key() -> None:
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterTransport(Settings(OPENROUTER_API_KEY=None))  # type: ignore[call-arg]
