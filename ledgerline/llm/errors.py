"""Typed errors for the model gateway."""

from __future__ import annotations


class LLMError(Exception):
    """Base class for every gateway error."""


class ParseError(LLMError):
    """The model's output could not be parsed into the requested schema."""

    def __init__(self, reason: str, raw: str) -> None:
        super().__init__(f"unparseable model output: {reason}")
        self.reason = reason
        self.raw = raw
        # Set by the gateway: an unparseable answer was still paid for.
        self.cost_usd = 0.0
        self.provenance: dict[str, str] | None = None


class ReplayMissError(LLMError):
    """Replay mode found no recording for this key. Replay never falls back to live."""

    def __init__(self, key: str, what: str = "call") -> None:
        super().__init__(f"no recorded {what} for replay key {key}; re-record to add it")
        self.key = key


class BudgetExceededError(LLMError):
    """A call would take, or has taken, spend past the run's hard budget."""

    def __init__(self, spent: float, needed: float, limit: float) -> None:
        super().__init__(
            f"budget stop: spent ${spent:.6f} + worst case ${needed:.6f} > limit ${limit:.6f}"
        )
        self.spent = spent
        self.needed = needed
        self.limit = limit


class PricingUnavailableError(LLMError):
    """No price is known for a model, so the worst-case pre-check cannot run."""


class RateLimitedError(LLMError):
    """Still rate limited (HTTP 429) after every backoff retry."""
