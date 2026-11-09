# Architecture decision records

Each ADR states its prediction **before** the code or the measurement exists, and is
committed in P1 (before `ledgerline/intent.py` first appears; `git log` shows the order).
The **Result** section is filled in after the live eval (P5) with the measured numbers,
whether or not they agree. A prediction is never edited after the fact; a wrong one stays
wrong, with the result next to it.

| ADR | Decision | Status |
|---|---|---|
| [001](ADR-001-intent-not-sql.md) | The LLM fills a typed intent; it never writes SQL | Result recorded (simulated run); floor not met |
| [002](ADR-002-langgraph-boundary.md) | LangGraph orchestrates one linear graph; nothing more | Prediction committed |
| [003](ADR-003-fan-out-rule.md) | Refuse aggregates across a one-to-many join | Prediction committed |
| [004](ADR-004-model-choice.md) | Default and second model, chosen by a live spike | Spike PENDING |
| [005](ADR-005-replay-and-budget.md) | Replay recordings and a hard per-run budget | Prediction committed |
| [006](ADR-006-benchmark-methodology.md) | Pre-registered eval on fieldservice + 5 Spider DBs vs two baselines | Prediction committed |
