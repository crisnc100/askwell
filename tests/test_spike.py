"""The model spike's scoring and reporting, with a fake transport (the live run is separate)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ledgerline.cli import app
from ledgerline.llm.pricing import ModelPrice
from ledgerline.llm.spike import (
    PROBES,
    advertised_support,
    make_live_gateway,
    run_spike,
    write_report,
)
from ledgerline.llm.types import RawResponse

PRICE = ModelPrice(1e-7, 4e-7)


class ScriptedTransport:
    """'good' answers each probe correctly via provider parse; 'text' via fenced text;
    'junk' with unparseable prose."""

    def __init__(self, style: dict[str, str]) -> None:
        self.style = style
        self.calls = 0

    def __call__(self, *, model: str, messages: Any, **_: Any) -> RawResponse:
        self.calls += 1
        index = next(i for i, (text, _) in enumerate(PROBES) if text == messages[1].content)
        want = PROBES[index][1].model_dump()
        usage = {"prompt_tokens": 50, "completion_tokens": 20, "cost": 0.0001}
        kind = self.style[model]
        if kind == "good":
            return RawResponse(content=json.dumps(want), parsed=want, usage=usage, model=model)
        if kind == "text":
            return RawResponse(
                content=f"```json\n{json.dumps(want)}\n```", usage=usage, model=model
            )
        return RawResponse(content="Here is what I found...", usage=usage, model=model)


def test_spike_scores_honoured_fallback_and_parse_errors() -> None:
    transport = ScriptedTransport({"m/good": "good", "m/text": "text", "m/junk": "junk"})
    gateway = make_live_gateway(transport, lambda _m: PRICE, budget_usd=1.0, max_tokens=100)
    reports, stopped = run_spike(
        ["m/good", "m/text", "m/junk"], gateway, {"m/good": True, "m/text": False}
    )
    assert stopped is None
    by_model = {r.model: r for r in reports}
    assert by_model["m/good"].honoured == len(PROBES)
    assert by_model["m/good"].exact == len(PROBES)
    assert by_model["m/text"].honoured == 0
    assert by_model["m/text"].exact == len(PROBES)
    assert {p.outcome for p in by_model["m/text"].probes} == {"text_fallback"}
    assert {p.outcome for p in by_model["m/junk"].probes} == {"parse_error"}
    assert by_model["m/junk"].cost_usd == pytest.approx(0.0001 * len(PROBES))
    assert by_model["m/junk"].advertised_structured_outputs is None


def test_spike_stops_at_budget_and_reports_it(tmp_path: Path) -> None:
    transport = ScriptedTransport({"m/good": "good", "m/two": "good"})
    gateway = make_live_gateway(transport, lambda _m: PRICE, budget_usd=0.0006, max_tokens=100)
    reports, stopped = run_spike(["m/good", "m/two"], gateway, {})
    assert stopped is not None
    assert transport.calls < 2 * len(PROBES)
    assert gateway.guard is not None
    assert gateway.guard.spent_usd <= 0.0006

    path = write_report(reports, stopped, 0.0006, tmp_path, now=datetime(2026, 11, 9, tzinfo=UTC))
    body = json.loads(path.read_text())
    assert path.name == "spike-2026-11-09T000000Z.json"
    assert body["stopped_by_budget"] == stopped
    assert body["spent_usd"] <= 0.0006


def test_advertised_support_reads_supported_parameters() -> None:
    payload = {
        "data": [
            {"id": "a", "supported_parameters": ["tools", "structured_outputs"]},
            {"id": "b", "supported_parameters": ["tools", "response_format"]},
            {"id": "c"},
        ]
    }
    assert advertised_support(payload) == {"a": True, "b": False, "c": False}


def test_spike_command_refuses_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import ledgerline.cli as cli
    from ledgerline.config import Settings

    no_key = Settings(OPENROUTER_API_KEY=None)  # type: ignore[call-arg]
    monkeypatch.setattr(cli, "get_settings", lambda: no_key)
    result = CliRunner().invoke(app, ["spike", "--models", "x/y"])
    assert result.exit_code == 2
    assert "OPENROUTER_API_KEY" in result.output
