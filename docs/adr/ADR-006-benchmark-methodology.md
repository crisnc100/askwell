# ADR-006: Pre-registered eval on fieldservice and 5 Spider databases, against two baselines

- **Status:** Proposed. Gold, Spider IDs and this prediction committed 2026-11-09 (P1),
  before any intent code.
- **Result:** PENDING.

## Context
The portfolio claim is that Ledgerline works on schemas it was not tuned on, compared
honestly with a one-shot SQL writer and LangChain's SQL agent, including where they win.
A benchmark the builder can steer proves nothing, so everything that decides the
headline numbers is fixed before the system exists.

## Decision
- **Frozen first:** the fieldservice gold set (67 items), the Spider question IDs
  (5 databases × 50, seeded and stratified by Spider hardness), the selection rule, and
  these predictions. Hashes live in `evals/gold/MANIFEST.json`; any later change needs a
  reasoned `CHANGELOG.md` entry.
- **Systems:** Ledgerline, oneshot (schema DDL + registry descriptions → SQL), sql_agent
  (LangChain, same descriptions; scored on its last successful `sql_db_query`). All at
  temperature 0. Fieldservice: 3 trials, mean reported. Spider: 1 trial.
- **Spider registries** come from `registry init` with no hand edits, hash-checked, and
  run with `allow_draft`, labelled in the report.
- **Metrics:** coverage, execution accuracy, accuracy given attempted, false-refusal rate,
  wrong-answer rate given answered, refusal recall, execution-error rate, mean cost, p50
  latency, all rates with Wilson 95% intervals. Results are compared as
  `ledgerline/bench/compare.py` describes.
- **Every Ledgerline miss is triaged** (`grammar_gap | misread | validator_false_reject |
  builder_bug | gold_issue`), and every question where a baseline beat Ledgerline is
  listed (by ID only for Spider).

## Prediction (pre-registered)
Spider, 250 selected questions (dog_kennels, car_1, flight_2, wta_1, network_1), default
model:
1. **Ledgerline coverage 35–55%.** Spider leans on nested queries, set operations and
   multi-condition joins that the intent grammar does not express.
2. **Ledgerline accuracy given attempted ≥ 80%**, and wrong-answer rate given answered
   ≤ 10%.
3. **Both baselines beat Ledgerline on raw execution accuracy:** sql_agent 60–75%,
   oneshot 55–70%, Ledgerline 30–50%.
4. **Ledgerline has the lowest wrong-answer rate given answered of the three**, on Spider
   and on fieldservice. This is the claim; if it fails, the README says so.
5. **Most Ledgerline Spider misses are `grammar_gap`** (≥ 60% of triaged misses), with
   `builder_bug` under 5%.

## Result
PENDING. The simulated run `sim-1` ([evals/reports/sim-1.md](../../evals/reports/sim-1.md))
covers all six databases with Ledgerline and oneshot, one trial, and is not a measurement
of the target model. The sql_agent baseline is not built yet: its many tool calls per
question cannot be honestly simulated, so it waits for a live model.
