"""Which provider serves a model, decided by the model's configured name.

A name of the form `anthropic:<model id>` (for example `anthropic:claude-haiku-5-5`) is
sent to the Anthropic API directly; any other name is an OpenRouter model id. The prefix
lives only in configuration (`LEDGERLINE_DEFAULT_MODEL`, an eval's `--models`), so no
model id appears in the code. It is part of the replay key, so a model's recordings
through each provider stay apart.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from ledgerline.config import Settings
from ledgerline.llm.pricing import ModelPrice, PriceBook
from ledgerline.llm.types import ChatMessage, RawResponse

Provider = Literal["anthropic", "openrouter"]
ANTHROPIC_PREFIX = "anthropic:"


def split_model(name: str) -> tuple[Provider, str]:
    """(provider, the id that provider knows the model by)."""
    if name.startswith(ANTHROPIC_PREFIX):
        return "anthropic", name.removeprefix(ANTHROPIC_PREFIX)
    return "openrouter", name


class ProviderRouter:
    """A gateway transport that sends each call to its model's provider. Each provider's
    transport, and OpenRouter's price list, is fetched on first use, so a deployment
    needs only the keys and services its models use: an Anthropic-only beta starts while
    OpenRouter is down."""

    def __init__(
        self,
        settings: Settings,
        *,
        anthropic: Any = None,
        openrouter: Any = None,
        openrouter_prices: PriceBook | None = None,
        load_openrouter_prices: Callable[[], PriceBook] | None = None,
    ) -> None:
        self._settings = settings
        self._anthropic = anthropic
        self._openrouter = openrouter
        self._prices = openrouter_prices
        self._load_prices = load_openrouter_prices

    def price(self, name: str) -> ModelPrice | None:
        provider, model_id = split_model(name)
        if provider == "anthropic":
            return ModelPrice(
                prompt_per_token=self._settings.anthropic_input_usd_per_mtok / 1e6,
                completion_per_token=self._settings.anthropic_output_usd_per_mtok / 1e6,
            )
        if self._prices is None and self._load_prices is not None:
            self._prices = self._load_prices()
        return self._prices.get(model_id) if self._prices is not None else None

    def __call__(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        schema_name: str,
        schema: dict[str, Any],
        max_tokens: int,
    ) -> RawResponse:
        provider, model_id = split_model(model)
        if provider == "anthropic":
            if self._anthropic is None:
                from ledgerline.llm.anthropic_transport import AnthropicTransport

                self._anthropic = AnthropicTransport(self._settings)
            transport = self._anthropic
        else:
            if self._openrouter is None:
                from ledgerline.llm.gateway import OpenRouterTransport

                self._openrouter = OpenRouterTransport(self._settings)
            transport = self._openrouter
        return transport(
            model=model_id,
            messages=messages,
            schema_name=schema_name,
            schema=schema,
            max_tokens=max_tokens,
        )
