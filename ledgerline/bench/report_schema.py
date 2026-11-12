"""The shape of an eval report's JSON (`evals/reports/<run id>.json`), which the Results
page reads.

`evals/report.schema.json` is generated from these models and committed, so a reader can
see the contract without reading Python:

    uv run python -m ledgerline.bench.report_schema --write

A test fails if the committed file differs from the models, or if any committed report or
any freshly built report does not validate.
"""

from __future__ import annotations

import json
import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ledgerline.bench.items import ROOT

SCHEMA_FILE = ROOT / "evals" / "report.schema.json"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rate(_Strict):
    """`n` of `of`, as a share, with its Wilson 95% interval. Both are null when `of` is 0."""

    n: int = Field(ge=0)
    of: int = Field(ge=0)
    rate: float | None = Field(ge=0, le=1)
    ci95: tuple[float, float] | None


class Row(_Strict):
    """Every metric for one schema, system and model, pooled over trials."""

    schema_: str = Field(alias="schema")
    system: str
    model: str
    trials: int = Field(ge=1)
    items: int = Field(ge=0)
    pending: int = Field(ge=0)
    coverage: Rate
    execution_accuracy: Rate
    accuracy_given_attempted: Rate
    false_refusal_rate: Rate
    wrong_answer_rate_given_answered: Rate
    refusal_recall: Rate
    execution_error_rate: Rate
    mean_cost_usd: float | None
    p50_latency_ms: float | None
    gold: str | None = None  # absent in reports from before --gold


class FloorCheck(_Strict):
    metric: str
    rule: str
    rate: Rate
    met: bool


class Floor(_Strict):
    """One schema's acceptance floor from `evals/floors.yaml`, checked on Ledgerline."""

    schema_: str = Field(alias="schema")
    model: str | None
    met: bool
    checks: list[FloorCheck]
    status_note: str | None
    cause: str | None
    next: str | None


class Miss(_Strict):
    """A Ledgerline item that was not answered correctly, with its triage tag."""

    schema_: str = Field(alias="schema")
    gold: str | None = None
    item_id: str
    trial: int = Field(ge=1)
    model: str
    outcome: Literal["wrong", "refused", "error", "pending"]
    issue_codes: list[str]
    refusal: str | None
    error: str | None
    tag: Literal[
        "grammar_gap", "misread", "validator_false_reject", "builder_bug", "gold_issue", "untriaged"
    ]
    note: str


class BaselineWin(_Strict):
    """An item a baseline got right and Ledgerline did not."""

    schema_: str = Field(alias="schema")
    model: str
    trial: int = Field(ge=1)
    gold: str | None = None
    item_id: str
    system: str


class Report(_Strict):
    """One eval run. `simulation` is set when any model answer was simulated, and says by
    which model and for which target."""

    run_id: str
    gold_files: list[str] = Field(default_factory=list[str])
    simulation: str | None
    notes: list[str]
    trials: int = Field(ge=1)
    status: Literal["complete", "partial", "aborted at budget"]
    abort_reason: str | None
    deferred: dict[str, int]
    spent_usd: float = Field(ge=0)
    registry_hashes: dict[str, str]
    table: list[Row]
    floors: list[Floor]
    misses: list[Miss]
    baseline_wins: list[BaselineWin]


def json_schema() -> str:
    schema = Report.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    if "--write" in argv:
        SCHEMA_FILE.write_text(json_schema(), encoding="utf-8")
        print(f"wrote {SCHEMA_FILE}")
        return 0
    if SCHEMA_FILE.read_text(encoding="utf-8") != json_schema():
        print(f"{SCHEMA_FILE} is out of date; run with --write")
        return 1
    print(f"{SCHEMA_FILE} matches the models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
