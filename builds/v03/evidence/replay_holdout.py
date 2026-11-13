"""Replay the committed v02-holdout recordings (no model calls) into a run folder.

    uv run python builds/v03/evidence/replay_holdout.py <out dir>

Writes <out dir>/ho-replay/results.jsonl: per item and trial, the outcome, intent and SQL.
The database URLs come from the environment, as for any askwell command.
"""

import sys
from pathlib import Path

from askwell.bench import run as run_module
from askwell.config import Settings

run_module.RUNS_DIR = Path(sys.argv[1])
result = run_module.run_eval(
    Settings(),
    run_id="ho-replay",
    schema_ids=["fieldservice"],
    systems=["ledgerline", "oneshot"],
    mode="replay",
    models=["anthropic:claude-haiku-5-5"],
    trials=3,
    budget_usd=0.0,
    gold=Path("evals/gold/holdout-v02.jsonl"),
)
print("deferred", dict(result.deferred))
