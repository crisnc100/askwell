"""The Anthropic API, called directly with the official SDK, using structured output.

What each request sends, and why:
- `output_config.format`: the JSON schema the answer must follow (the SDK's
  `transform_schema` moves the keywords the API does not take into descriptions; the
  gateway still validates the answer with Pydantic).
- `output_config.effort` (`LEDGERLINE_ANTHROPIC_EFFORT`, default `low`) with adaptive
  thinking: the model decides how much to think, and a short form needs little.
- No `temperature`, `top_p` or `top_k`: the API refuses non-default values for this
  model with a 400.

An answer that stopped at `max_tokens` (or at the context window) or that the model
refused comes back with its usage and a `finish_reason`, so the gateway charges it and
then raises ParseError, as it does for OpenRouter.

Rate limits (429), server errors (5xx, including 529 overloaded) and connection errors
are retried here with exponential backoff; any other error, a 400 above all, is raised
at once. The SDK's own retries are off, so nothing is retried twice.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any, cast

import anthropic
import httpx2
from anthropic import transform_schema
from anthropic.types import Message, MessageParam

from ledgerline.config import Settings
from ledgerline.llm.errors import ProviderUnavailableError
from ledgerline.llm.types import ChatMessage, RawResponse

_FINISH = {
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "refusal": "refusal",
}


class AnthropicTransport:
    RETRIES = 4
    BASE_DELAY_S = 1.0
    MAX_DELAY_S = 20.0

    def __init__(
        self,
        settings: Settings,
        http_client: httpx2.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if settings.anthropic_api_key is None:
            raise ValueError("ANTHROPIC_API_KEY is not set; it is needed for anthropic: models")
        self._effort = settings.anthropic_effort
        self._sleep = sleep
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            base_url=settings.anthropic_base_url,
            max_retries=0,
            http_client=http_client,
        )

    def __call__(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        schema_name: str,
        schema: dict[str, Any],
        max_tokens: int,
    ) -> RawResponse:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [
            cast(MessageParam, {"role": m.role, "content": m.content})
            for m in messages
            if m.role != "system"
        ]
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": turns,
            "output_config": {
                "effort": self._effort,
                "format": {"type": "json_schema", "schema": transform_schema(schema)},
            },
            "thinking": {"type": "adaptive"},
        }
        if system:
            request["system"] = system
        return _raw(self._with_retries(request), model)

    def _with_retries(self, request: dict[str, Any]) -> Message:
        for attempt in range(self.RETRIES + 1):
            try:
                return self._client.messages.create(**request)
            except (
                anthropic.RateLimitError,
                anthropic.InternalServerError,
                anthropic.APIConnectionError,
            ) as exc:
                if attempt == self.RETRIES:
                    raise ProviderUnavailableError(
                        f"the Anthropic API still failed after {self.RETRIES} retries: "
                        f"{type(exc).__name__}"
                    ) from exc
                self._sleep(min(self.MAX_DELAY_S, self.BASE_DELAY_S * 2**attempt))
        raise AssertionError("unreachable")


def _raw(message: Message, model: str) -> RawResponse:
    text = "".join(block.text for block in message.content if block.type == "text")
    finish = _FINISH.get(message.stop_reason or "")
    parsed: dict[str, Any] | None = None
    if finish is None:
        try:
            value = json.loads(text)
        except ValueError:
            value = None
        parsed = value if isinstance(value, dict) else None
    usage = message.usage
    prompt_tokens = (
        usage.input_tokens
        + (usage.cache_creation_input_tokens or 0)
        + (usage.cache_read_input_tokens or 0)
    )
    return RawResponse(
        content=text,
        parsed=parsed,
        usage={"prompt_tokens": prompt_tokens, "completion_tokens": usage.output_tokens},
        model=message.model or model,
        finish_reason=finish,
    )
