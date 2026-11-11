"""Model spike: which cheap OpenRouter models honour json_schema structured output?

Each candidate gets the same fixed probes through the real gateway (live mode,
temperature 0, one shared hard budget). A probe counts as "honoured" only when
the provider returned a parse that validates; a text fallback that validates is
counted separately, because the product must not depend on it. The report is
written to `evals/spike/` and the choice is recorded in ADR-004.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from ledgerline.llm.budget import BudgetGuard
from ledgerline.llm.errors import BudgetExceededError, LLMError, ParseError
from ledgerline.llm.gateway import Gateway, Transport
from ledgerline.llm.types import ChatMessage

PROMPT_VERSION = "spike-v1"


class Triage(BaseModel):
    """A generic nested extraction, unrelated to Ledgerline's intent grammar."""

    model_config = ConfigDict(extra="forbid")

    category: Literal["billing", "outage", "scheduling", "other"]
    urgency: Literal["low", "normal", "high"]
    customer: str | None
    amounts_usd: list[float]
    follow_up: bool


SYSTEM = (
    "Extract the fields from the customer message. Use null for a missing customer "
    "name and an empty list when no dollar amounts are mentioned."
)

PROBES: list[tuple[str, Triage]] = [
    (
        "Hi, this is Dana Ruiz. I was charged $120.50 twice this month. Please refund one.",
        Triage(
            category="billing",
            urgency="normal",
            customer="Dana Ruiz",
            amounts_usd=[120.5],
            follow_up=True,
        ),
    ),
    (
        "Power is out at our whole warehouse right now and freezers are failing!",
        Triage(category="outage", urgency="high", customer=None, amounts_usd=[], follow_up=True),
    ),
    (
        "Can the technician come Thursday instead of Wednesday? No rush. - Lee Park",
        Triage(
            category="scheduling",
            urgency="low",
            customer="Lee Park",
            amounts_usd=[],
            follow_up=True,
        ),
    ),
    (
        "Just saying thanks, the repair last week was great. Nothing else needed.",
        Triage(category="other", urgency="low", customer=None, amounts_usd=[], follow_up=False),
    ),
    (
        "Invoice shows $89 for parts and $240 labor, but the quote was $300 total. Sam Ode.",
        Triage(
            category="billing",
            urgency="normal",
            customer="Sam Ode",
            amounts_usd=[89.0, 240.0, 300.0],
            follow_up=True,
        ),
    ),
]


@dataclass
class ProbeResult:
    probe: int
    outcome: Literal["honoured", "text_fallback", "parse_error", "error"]
    exact: bool
    cost_usd: float
    latency_ms: int
    detail: str = ""
    # What the model returned: the parsed fields, or the raw text when it did not
    # parse. It lets a reader see which field differed from the expected answer.
    answer: dict[str, Any] | str | None = None


@dataclass
class CandidateReport:
    model: str
    advertised_structured_outputs: bool | None
    probes: list[ProbeResult] = field(default_factory=list[ProbeResult])

    @property
    def honoured(self) -> int:
        return sum(p.outcome == "honoured" for p in self.probes)

    @property
    def exact(self) -> int:
        return sum(p.exact for p in self.probes)

    @property
    def cost_usd(self) -> float:
        return sum(p.cost_usd for p in self.probes)

    def summary(self) -> dict[str, Any]:
        latencies = sorted(p.latency_ms for p in self.probes)
        return {
            "model": self.model,
            "advertised_structured_outputs": self.advertised_structured_outputs,
            "probes_run": len(self.probes),
            "honoured": self.honoured,
            "exact": self.exact,
            "cost_usd": round(self.cost_usd, 6),
            "p50_latency_ms": latencies[len(latencies) // 2] if latencies else None,
            "probes": [asdict(p) for p in self.probes],
        }


def advertised_support(models_payload: dict[str, Any]) -> dict[str, bool]:
    """Model id -> whether OpenRouter lists `structured_outputs` for it."""
    out: dict[str, bool] = {}
    for entry in models_payload.get("data", []):
        params = entry.get("supported_parameters") or []
        out[entry["id"]] = "structured_outputs" in params
    return out


def fetch_models_payload(base_url: str) -> dict[str, Any]:
    response = httpx.get(f"{base_url.rstrip('/')}/models", timeout=30)
    response.raise_for_status()
    return response.json()


def _matches(got: Triage, want: Triage) -> bool:
    return (
        got.category == want.category
        and got.urgency == want.urgency
        and (got.customer or None) == want.customer
        and sorted(got.amounts_usd) == sorted(want.amounts_usd)
        and got.follow_up == want.follow_up
    )


def run_spike(
    models: list[str],
    gateway: Gateway,
    advertised: dict[str, bool],
    clock: Any = time.perf_counter,
) -> tuple[list[CandidateReport], str | None]:
    """Run every probe on every model until done or the budget stops the spike."""
    reports: list[CandidateReport] = []
    stopped: str | None = None
    for model in models:
        report = CandidateReport(model=model, advertised_structured_outputs=advertised.get(model))
        reports.append(report)
        for index, (text, want) in enumerate(PROBES):
            messages = [
                ChatMessage(role="system", content=SYSTEM),
                ChatMessage(role="user", content=text),
            ]
            spent_before = gateway.guard.spent_usd if gateway.guard else 0.0
            started = clock()
            try:
                result = gateway.complete(
                    model=model, prompt_version=PROMPT_VERSION, messages=messages, schema=Triage
                )
            except BudgetExceededError as exc:
                stopped = str(exc)
                return reports, stopped
            except ParseError as exc:
                report.probes.append(
                    _failed(
                        index,
                        "parse_error",
                        gateway,
                        spent_before,
                        started,
                        clock,
                        exc.reason,
                        answer=exc.raw[:2000],
                    )
                )
                continue
            except LLMError as exc:
                report.probes.append(
                    _failed(index, "error", gateway, spent_before, started, clock, str(exc))
                )
                continue
            report.probes.append(
                ProbeResult(
                    probe=index,
                    outcome="honoured" if result.raw.parsed is not None else "text_fallback",
                    exact=_matches(result.value, want),
                    cost_usd=result.cost_usd,
                    latency_ms=int((clock() - started) * 1000),
                    answer=result.value.model_dump(mode="json"),
                )
            )
    return reports, stopped


def _failed(
    index: int,
    outcome: Literal["parse_error", "error"],
    gateway: Gateway,
    spent_before: float,
    started: float,
    clock: Any,
    detail: str,
    answer: str | None = None,
) -> ProbeResult:
    spent = (gateway.guard.spent_usd if gateway.guard else 0.0) - spent_before
    return ProbeResult(
        probe=index,
        outcome=outcome,
        exact=False,
        cost_usd=spent,
        latency_ms=int((clock() - started) * 1000),
        detail=detail[:300],
        answer=answer,
    )


def write_report(
    reports: list[CandidateReport],
    stopped: str | None,
    budget_usd: float,
    out_dir: Path,
    now: datetime | None = None,
) -> Path:
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"spike-{stamp}.json"
    body = {
        "prompt_version": PROMPT_VERSION,
        "budget_usd": budget_usd,
        "spent_usd": round(sum(r.cost_usd for r in reports), 6),
        "stopped_by_budget": stopped,
        "candidates": [r.summary() for r in reports],
    }
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def make_live_gateway(
    transport: Transport, price_lookup: Any, budget_usd: float, max_tokens: int
) -> Gateway:
    return Gateway(
        mode="live",
        store=None,
        transport=transport,
        price_lookup=price_lookup,
        guard=BudgetGuard(budget_usd),
        max_tokens=max_tokens,
    )
