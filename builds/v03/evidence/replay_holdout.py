"""Replay the committed v02-holdout recordings (no live calls) and dump per-item detail."""
import json, sys
from pathlib import Path
import askwell.bench.run as R
from askwell.config import Settings
out = Path(sys.argv[1])
R.RUNS_DIR = out
s = Settings()
assert s.llm_mode if hasattr(s,'llm_mode') else True
res = R.run_eval(s, run_id="ho-replay", schema_ids=["fieldservice"], systems=["ledgerline","oneshot"],
    mode="replay", models=["anthropic:claude-haiku-5-5"], trials=3, budget_usd=0.0,
    gold=Path("evals/gold/holdout-v02.jsonl"))
print("spent", res.spent_usd, "deferred", dict(res.deferred))
