"""The model gateway: one structured-output call, recorded, replayed, costed, budgeted.

Modes:
- `live`: call OpenRouter; nothing is stored.
- `record`: call OpenRouter and append the response to the replay store.
- `replay`: answer only from the replay store. A miss raises `ReplayMissError`;
  replay never falls back to a live call.
- `export`: like replay, but a miss writes the request to the pending directory for a
  simulated answer (`ledgerline.llm.simulate`) and raises `PendingRequestError`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import httpx
import openai
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, ValidationError

from ledgerline.config import LLMMode, Settings
from ledgerline.llm.budget import BudgetGuard, with_backoff
from ledgerline.llm.errors import ParseError, PricingUnavailableError
from ledgerline.llm.pricing import ModelPrice, cost_from_usage, worst_case_cost
from ledgerline.llm.replay import ReplayStore, canonical_json, replay_key
from ledgerline.llm.simulate import PendingRequestError, export_request, register_response_model
from ledgerline.llm.types import ChatMessage, LLMResult, RawResponse


class Transport(Protocol):
    def __call__(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        schema_name: str,
        schema: dict[str, Any],
        max_tokens: int,
    ) -> RawResponse: ...


PriceLookup = Callable[[str], ModelPrice | None]

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def parse_output[T: BaseModel](raw: RawResponse, schema: type[T]) -> T:
    """Validate the provider's parse, or fall back to parsing the text with Pydantic."""
    if raw.finish_reason == "length":
        raise ParseError("the answer was cut off at the max_tokens limit", raw.content)
    if raw.parsed is not None:
        try:
            return schema.model_validate(raw.parsed)
        except ValidationError as exc:
            raise ParseError(f"structured output failed validation: {exc}", raw.content) from exc
    text = raw.content.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        raise ParseError(f"text did not validate: {exc.errors()[0]['msg']}", raw.content) from exc


def _parse_charged[T: BaseModel](
    raw: RawResponse, schema: type[T], cost_usd: float, provenance: dict[str, str] | None
) -> T:
    """`parse_output`, but a ParseError carries the call's cost and provenance, so a
    failed attempt's spend is never lost."""
    try:
        return parse_output(raw, schema)
    except ParseError as exc:
        exc.cost_usd = cost_usd
        exc.provenance = provenance
        raise


class Gateway:
    def __init__(
        self,
        *,
        mode: LLMMode,
        store: ReplayStore | None,
        transport: Transport | None,
        price_lookup: PriceLookup,
        guard: BudgetGuard | None,
        max_tokens: int,
        backoff_sleep: Callable[[float], None] | None = None,
        pending_dir: Path | None = None,
    ) -> None:
        if mode in ("record", "replay", "export") and store is None:
            raise ValueError(f"{mode} mode needs a replay store")
        if mode == "export" and pending_dir is None:
            raise ValueError("export mode needs a pending directory")
        if mode in ("record", "live") and (transport is None or guard is None):
            raise ValueError(f"{mode} mode needs a transport and a budget guard")
        self.mode = mode
        self.store = store
        self.transport = transport
        self.price_lookup = price_lookup
        self.guard = guard
        self.max_tokens = max_tokens
        self._backoff_sleep = backoff_sleep
        self.pending_dir = pending_dir

    def complete[T: BaseModel](
        self,
        *,
        model: str,
        prompt_version: str,
        messages: list[ChatMessage],
        schema: type[T],
        context: dict[str, Any] | None = None,
        guard: BudgetGuard | None = None,
    ) -> LLMResult[T]:
        """One structured call. `guard` overrides the gateway's own budget guard, so
        concurrent callers (one per API request) never share or replace each other's."""
        json_schema = schema.model_json_schema()
        key = replay_key(model, prompt_version, messages, json_schema)

        if self.mode in ("replay", "export"):
            assert self.store is not None
            if self.mode == "export" and key not in self.store:
                assert self.pending_dir is not None
                register_response_model(schema)
                path = export_request(
                    self.pending_dir,
                    key=key,
                    model=model,
                    prompt_version=prompt_version,
                    messages=messages,
                    schema_name=schema.__name__,
                    response_schema=json_schema,
                    context=context,
                )
                raise PendingRequestError(key, path)
            record = self.store.get(key)
            raw = RawResponse.model_validate(record["raw"])
            return LLMResult[T](
                value=_parse_charged(
                    raw, schema, float(record["cost_usd"]), record.get("provenance")
                ),
                raw=raw,
                cost_usd=float(record["cost_usd"]),
                cost_source="replay",
                replayed=True,
                key=key,
                provenance=record.get("provenance"),
            )

        assert self.transport is not None
        budget = guard or self.guard
        assert budget is not None
        transport = self.transport
        price = self.price_lookup(model)
        if price is None:
            raise PricingUnavailableError(
                f"no price for {model!r}: the worst-case budget pre-check cannot run"
            )
        prompt_bytes = len(
            canonical_json([m.model_dump() for m in messages]).encode("utf-8")
        ) + len(canonical_json(json_schema).encode("utf-8"))
        budget.precheck(worst_case_cost(price, prompt_bytes, self.max_tokens))

        def call() -> RawResponse:
            return transport(
                model=model,
                messages=messages,
                schema_name=schema.__name__,
                schema=json_schema,
                max_tokens=self.max_tokens,
            )

        if self._backoff_sleep is None:
            raw = with_backoff(call)
        else:
            raw = with_backoff(call, sleep=self._backoff_sleep)
        cost, source = cost_from_usage(raw.usage, price)
        budget.charge(cost)
        if self.mode == "record":
            assert self.store is not None
            # Stored before parsing, so a replay reproduces a ParseError too.
            self.store.put(key, {"raw": raw.model_dump(), "cost_usd": cost, "model": model})
        return LLMResult[T](
            value=_parse_charged(raw, schema, cost, None),
            raw=raw,
            cost_usd=cost,
            cost_source=source,
            replayed=False,
            key=key,
        )


class OpenRouterTransport:
    """OpenRouter through LangChain's `ChatOpenAI`, using json_schema structured output.

    Provider routing sets `require_parameters`, so OpenRouter only routes to
    upstream providers that support `response_format` json_schema; `order` pins
    preferred providers when given. `usage.include` asks OpenRouter to report the
    call's cost. `max_tokens` goes in the body under OpenRouter's documented name
    (ChatOpenAI would send `max_completion_tokens`). Retries are off here: the
    gateway owns 429 backoff.
    """

    def __init__(
        self,
        settings: Settings,
        providers: list[str] | None = None,
        strict: bool = False,
        http_client: httpx.Client | None = None,
    ) -> None:
        if settings.openrouter_api_key is None:
            raise ValueError("OPENROUTER_API_KEY is not set; use replay mode without a key")
        self._settings = settings
        self._providers = providers
        self._strict = strict
        self._http_client = http_client

    def __call__(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        schema_name: str,
        schema: dict[str, Any],
        max_tokens: int,
    ) -> RawResponse:
        from langchain_openai import ChatOpenAI

        provider: dict[str, Any] = {"require_parameters": True}
        if self._providers:
            provider["order"] = self._providers
            provider["allow_fallbacks"] = False
        key = self._settings.openrouter_api_key
        assert key is not None
        llm = ChatOpenAI(
            model=model,
            base_url=self._settings.openrouter_base_url,
            api_key=key,
            temperature=0,
            max_retries=0,
            http_client=self._http_client,
            extra_body={
                "provider": provider,
                "usage": {"include": True},
                "max_tokens": max_tokens,
            },
        )
        structured = llm.with_structured_output(
            {**schema, "title": schema_name},
            method="json_schema",
            include_raw=True,
            strict=self._strict,
        )
        try:
            out: Any = structured.invoke([(m.role, m.content) for m in messages])
        except openai.LengthFinishReasonError as exc:
            # The SDK raises this when the answer stops at max_tokens. The call was
            # still billed, so its usage goes back to the gateway to be charged; the
            # gateway's parse then turns it into a ParseError.
            return _cut_off_response(exc.completion, model)
        message = out["raw"]
        content = (
            message.content if isinstance(message.content, str) else json.dumps(message.content)
        )
        metadata: dict[str, Any] = dict(message.response_metadata or {})
        usage: dict[str, Any] = dict(metadata.get("token_usage") or {})
        parsed = out.get("parsed")
        return RawResponse(
            content=content,
            parsed=parsed if isinstance(parsed, dict) else None,
            usage=usage,
            model=str(metadata.get("model_name") or model),
        )


def _cut_off_response(completion: ChatCompletion, model: str) -> RawResponse:
    choice = completion.choices[0] if completion.choices else None
    content = (choice.message.content if choice else None) or ""
    usage: dict[str, Any] = completion.usage.model_dump() if completion.usage else {}
    return RawResponse(
        content=content,
        parsed=None,
        usage=usage,
        model=completion.model or model,
        finish_reason="length",
    )
