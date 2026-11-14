# Architecture decision records

An ADR (architecture decision record) explains one design choice: the problem, the
decision, what it costs, and a **prediction** of how it will measure. Each prediction was
committed before the code it describes existed (`git log` shows the order), and is never
edited afterwards. The **Result** section records what was measured, whether or not it
agrees, and says "not measured" where nothing could be measured yet.

The Results of ADR-001, 002, 003, 005 and 006 come from simulated answers: before a
model key existed, a stand-in model answered for the target model in the run `sim-1`,
and those Results say so. ADR-004's amendments and ADR-007 were measured live.

| ADR | Decision | Result |
|---|---|---|
| [001](ADR-001-intent-not-sql.md) | The model fills a typed intent; it never writes SQL | Recorded (simulated); the v0.1 floor is not met |
| [002](ADR-002-langgraph-boundary.md) | LangGraph runs one fixed graph, nothing more | Recorded (simulated); the 150-line prediction was wrong (171) |
| [003](ADR-003-fan-out-rule.md) | Refuse totals across a one-to-many join | Recorded (simulated); two predictions held, one not measured |
| [004](ADR-004-model-choice.md) | Default and second model, chosen by a live test | Measured live: default `anthropic:claude-haiku-5-5` (Amendment 3), second `google/gemma-4-26b-a4b-it` |
| [005](ADR-005-replay-and-budget.md) | Replay recordings and a hard per-run budget | Replay held; spend and cost not measured |
| [006](ADR-006-benchmark-methodology.md) | Questions fixed in advance, on fieldservice and 5 Spider databases | Recorded (simulated); sql_agent not measured |
| [007](ADR-007-grammar-v02.md) | Grammar v0.2: ratios, conditional metrics, two-date series, refuse first | Measured live: 8 of 10 predictions held; held-out wrong answers 25.9%, not 8% |
| [008](ADR-008-accuracy-v03.md) | v0.3 accuracy: stable answers, uncurated schemas, four grammar features, a deploy gate | Not measured yet |
