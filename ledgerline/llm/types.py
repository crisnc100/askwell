"""Plain data passed through the gateway."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class RawResponse(BaseModel):
    """What a transport returns: the model's text, its parse if any, and raw usage."""

    content: str
    parsed: dict[str, Any] | None = None
    usage: dict[str, Any] = {}
    model: str
    # "length" (cut off at `max_tokens`) or "content_filter" (blocked by the provider):
    # either way there is no usable answer, but the call is still billed.
    finish_reason: str | None = None


class LLMResult[T: BaseModel](BaseModel):
    """A parsed, costed model call."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    value: T
    raw: RawResponse
    cost_usd: float
    cost_source: Literal["openrouter", "estimated", "replay"]
    replayed: bool
    key: str
    # Set for simulated answers: {"simulated_by": ..., "standing_in_for": ...}.
    provenance: dict[str, str] | None = None
