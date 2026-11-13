"""Model prices and cost accounting.

Cost comes from OpenRouter's reported usage cost when present, otherwise it is
estimated from the models-endpoint pricing (USD per token).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

from askwell.llm.errors import PricingUnavailableError


@dataclass(frozen=True)
class ModelPrice:
    prompt_per_token: float
    completion_per_token: float


class PriceBook:
    def __init__(self, prices: dict[str, ModelPrice]) -> None:
        self._prices = dict(prices)

    @classmethod
    def from_models_payload(cls, payload: dict[str, Any]) -> PriceBook:
        """Parse OpenRouter's `GET /models` body (`{"data": [{"id", "pricing"}]}`)."""
        prices: dict[str, ModelPrice] = {}
        for entry in payload.get("data", []):
            pricing = entry.get("pricing") or {}
            try:
                prices[entry["id"]] = ModelPrice(
                    prompt_per_token=float(pricing["prompt"]),
                    completion_per_token=float(pricing["completion"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return cls(prices)

    @classmethod
    def fetch(cls, base_url: str, client: httpx.Client | None = None) -> PriceBook:
        own = client is None
        http = client or httpx.Client(timeout=30)
        try:
            response = http.get(f"{base_url.rstrip('/')}/models")
            response.raise_for_status()
            return cls.from_models_payload(response.json())
        finally:
            if own:
                http.close()

    def get(self, model: str) -> ModelPrice | None:
        return self._prices.get(model)

    def require(self, model: str) -> ModelPrice:
        price = self.get(model)
        if price is None:
            raise PricingUnavailableError(f"no price for model {model!r}")
        return price


def worst_case_cost(price: ModelPrice, prompt_bytes: int, max_tokens: int) -> float:
    """An upper bound on a call's cost before it is made.

    `prompt_bytes` is the UTF-8 size of the messages and the response schema, serialised
    as JSON. Every token covers at least one byte of the text, so this bounds the
    prompt's tokens. A character count would not: '日' is one character but three bytes,
    and can be up to three tokens. The JSON keys and quotes also outweigh the few tokens
    a chat template adds. The completion is bounded by `max_tokens`.
    """
    return prompt_bytes * price.prompt_per_token + max_tokens * price.completion_per_token


def cost_from_usage(
    usage: dict[str, Any], price: ModelPrice | None
) -> tuple[float, Literal["openrouter", "estimated"]]:
    reported = usage.get("cost")
    if isinstance(reported, int | float) and not isinstance(reported, bool):
        return float(reported), "openrouter"
    if price is None:
        raise PricingUnavailableError("usage has no cost and no price is known")
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    return (
        prompt * price.prompt_per_token + completion * price.completion_per_token,
        "estimated",
    )
