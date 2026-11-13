# ADR-006: Pre-registered eval on fieldservice and 5 Spider databases, against two baselines

- **Status:** Proposed. Gold, Spider IDs and this prediction committed 2026-11-09 (P1),
  before any intent code.
- **Result:** recorded 2026-11-11 from the simulated run `sim-1` (see Result).

## Context
The portfolio claim is that Askwell works on schemas it was not tuned on, compared
honestly with a one-shot SQL writer and LangChain's SQL agent, including where they win.
A benchmark the builder can steer proves nothing, so everything that decides the
headline numbers is fixed before the system exists.

## Decision
- **Frozen first:** the fieldservice gold set (67 items), the Spider question IDs
  (5 databases × 50, seeded and stratified by Spider hardness), the selection rule, and
  these predictions. Hashes live in `evals/gold/MANIFEST.json`; any later change needs a
  reasoned `CHANGELOG.md` entry.
- **Systems:** Askwell, oneshot (schema DDL + registry descriptions → SQL), sql_agent
  (LangChain, same descriptions; scored on its last successful `sql_db_query`). All at
  temperature 0. Fieldservice: 3 trials, mean reported. Spider: 1 trial.
- **Spider registries** come from `registry init` with no hand edits, hash-checked, and
  run with `allow_draft`, labelled in the report.
- **Metrics:** coverage, execution accuracy, accuracy given attempted, false-refusal rate,
  wrong-answer rate given answered, refusal recall, execution-error rate, mean cost, p50
  latency, all rates with Wilson 95% intervals. Results are compared as
  `askwell/bench/compare.py` describes.
- **Every Askwell miss is triaged** (`grammar_gap | misread | validator_false_reject |
  builder_bug | gold_issue`), and every question where a baseline beat Askwell is
  listed (by ID only for Spider).

## Prediction (pre-registered)
Spider, 250 selected questions (dog_kennels, car_1, flight_2, wta_1, network_1), default
model:
1. **Askwell coverage 35–55%.** Spider leans on nested queries, set operations and
   multi-condition joins that the intent grammar does not express.
2. **Askwell accuracy given attempted ≥ 80%**, and wrong-answer rate given answered
   ≤ 10%.
3. **Both baselines beat Askwell on raw execution accuracy:** sql_agent 60–75%,
   oneshot 55–70%, Askwell 30–50%.
4. **Askwell has the lowest wrong-answer rate given answered of the three**, on Spider
   and on fieldservice. This is the claim; if it fails, the README says so.
5. **Most Askwell Spider misses are `grammar_gap`** (≥ 60% of triaged misses), with
   `builder_bug` under 5%.

## Result
Measured on the eval run `sim-1` ([evals/reports/sim-1.md](../../evals/reports/sim-1.md)). Its model answers were **simulated**: claude-haiku-5-5 answered every request as a stand-in for `openai/gpt-oss-120b`, because there is no OpenRouter key yet. A simulated run tests the pipeline and the scoring; it does not measure the target model. One trial. The sql_agent baseline is not built yet: its many tool calls per question cannot be
honestly simulated, so it waits for a live model.

The Spider numbers below pool the 5 databases (250 questions). Square brackets are Wilson
95% intervals.

| Spider, 5 databases | Askwell | one-shot |
|---|---|---|
| Coverage (questions attempted) | 65.6% [60-71], 164/250 | 100% [98-100], 250/250 |
| Execution accuracy | 58.0% [52-64], 145/250 | 80.0% [75-84], 200/250 |
| Accuracy given attempted | 88.4% [83-92], 145/164 | 80.0% [75-84], 200/250 |
| Wrong answers among answered | 11.6% [8-17], 19/164 | 19.7% [15-25], 49/249 |

1. **Askwell coverage 35–55%:** wrong. It was 65.6%, from 48% on network_1 to 96% on
   wta_1.
2. **Accuracy given attempted ≥ 80%:** held (88.4%). **Wrong answers among answered
   ≤ 10%:** failed (11.6%).
3. **Both baselines beat Askwell on execution accuracy:** held for one-shot, which
   scored 80.0% against Askwell's 58.0%. Both were above their predicted ranges
   (one-shot 55–70%, Askwell 30–50%). sql_agent: not measured.
4. **Askwell has the lowest wrong-answer rate:** held against one-shot on both Spider
   (11.6% [8-17] against 19.7% [15-25]) and fieldservice (13.2% [6-27] against 30.2%
   [19-45]). On both, the two intervals overlap. sql_agent: not measured.
5. **Most Spider misses are `grammar_gap`, and `builder_bug` is under 5%:** held. Of 105
   Spider misses, 76 (72%) are `grammar_gap`, 12 `validator_false_reject`, 11 `gold_issue`,
   6 `misread` and none `builder_bug`.
