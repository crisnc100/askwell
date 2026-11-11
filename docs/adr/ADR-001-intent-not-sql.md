# ADR-001: The LLM fills a typed intent; it never writes SQL

- **Status:** Proposed. Prediction committed 2026-11-09 (P1), before any intent code.
- **Result:** recorded 2026-11-09 from a simulated run (see Result). The live run waits for an
  OpenRouter key.

## Context
A data analyst that answers with numbers is only useful if a wrong number is rare and
detectable. LLM-written SQL can be valid, run, and be wrong (a bad join, a missed filter,
a double count) with nothing to catch it. Ledgerline's claim is governance: every answer
comes from a query the system can explain and audit.

## Decision
The model returns a structured intent (`ledgerline/core/intent.py`): an entity, selected
fields, metrics, filters, having, group-by, a date range, order and limit, or
`unanswerable` with a reason. Plain Python validates every field against the registry
and returns typed errors. Code resolves relative dates: against `LEDGERLINE_NOW` for a
configured schema, so evals reproduce, and against the wall clock in the workspace's time
zone for uploaded data ([Your data](../../README.md#your-data)). A
SQLAlchemy Core builder writes parameterized SQL that runs on a read-only connection.
Anything the grammar or validator cannot express is refused with a reason, never guessed.

## Trade-off accepted
Coverage. Questions outside the grammar are refused even when a free-form SQL writer
would get them right.

## Prediction (pre-registered)
On the fieldservice gold set (43 in_schema items, default model, mean of 3 trials):

1. **Coverage ceiling ≈ 72%.** Reading the frozen gold against the P2 grammar as planned,
   12 of 43 in_schema items need something it does not have: a path of 3 hops
   (fs-033, fs-038, fs-040, fs-041), computed expressions or ratios (fs-025, fs-028,
   fs-030, fs-039), a column-to-column comparison (fs-029), two date fields in one
   series (fs-035), a distinct count over a calendar grain in HAVING (fs-037), or an
   anti-join (fs-042). So at most 31/43 can be attempted correctly.
2. **Execution accuracy 60–70%**, below the plan's 80% floor, because of item 1
   plus some misreads. The floor is predicted to fail unless the grammar grows.
3. **Accuracy given attempted ≥ 85%** and **wrong-answer rate given answered ≤ 5%.**
4. **The oneshot baseline answers more but is wrong more:** execution accuracy within
   ±15 points of Ledgerline, and wrong-answer rate given answered ≥ 15%.
5. **Refusal recall ≥ 95%** on the 24 refusal items (13 out_of_schema, 11 should_refuse),
   with zero hidden-field values returned.

## How it is measured
`ledgerline eval --schema fieldservice --systems ledgerline,oneshot --trials 3`, metrics
as defined in `builds/v01/plan.md` (Definitions), Wilson 95% intervals. The sql_agent
baseline is planned but waits for a live model ([ADR-006](ADR-006-benchmark-methodology.md)). With 43
items one question is about 2.3 points, so differences under about 10 points are within
noise.

## Result
Measured on eval run `sim-1` (`evals/reports/sim-1.md`). The model's answers were
**simulated**: claude-haiku-5-5 answered every request as a stand-in for
`openai/gpt-oss-120b`, because there is no OpenRouter key yet. This is not a measurement of
the real model. One trial, fieldservice gold revision 2.

Two things changed between the prediction and the run:
- The grammar grew before the run: a field can now be up to three relationship hops from
  the base table (was two), and filters can compare two columns. That made 4 of the 12
  "beyond the grammar" items expressible: fs-029 (compare two dates), fs-033 and fs-038
  (four tables, three hops) and fs-040 (five tables, three hops on its longest path).
  fs-041 now has a join path but still needs a conditional count, so it stays out of reach.
- Gold revision 2 fixed fs-032, which contradicted the gold README (`evals/gold/CHANGELOG.md`).

| Metric (fieldservice) | Ledgerline | oneshot |
|---|---|---|
| Coverage (in_schema attempted) | 88.4% [76-95], 38/43 | 100%, 43/43 |
| Execution accuracy | 76.7% [62-87], 33/43 | 69.8% [55-81], 30/43 |
| Accuracy given attempted | 86.8% [73-94], 33/38 | 69.8%, 30/43 |
| Wrong answers among answered | 13.2% [6-27], 5/38 | 30.2% [19-45], 13/43 |
| Refusal recall (24 refusal items) | 100% [86-100] | 100% [86-100] |

Square brackets are Wilson 95% intervals. With 43 items, one question moves a rate by about
2.3 points.

How the predictions held:
1. **Coverage ceiling about 72%:** superseded by the larger grammar. Coverage was 88.4%, but 3
   of those attempts were wrong answers to questions the grammar still cannot express (below).
2. **Execution accuracy 60–70%:** wrong. It was 76.7%, helped by the larger grammar. The 80%
   floor is still **not met**.
3. **Accuracy given attempted ≥ 85%:** held (86.8%). **Wrong answers among answered ≤ 5%:**
   failed (13.2%).
4. **oneshot answers more and is wrong more:** held. Its accuracy is within 7 points of
   Ledgerline's, and 30.2% of its answers are wrong.
5. **Refusal recall ≥ 95%:** held (100%). No hidden-field value was returned.

**The v0.1 floor is not met (simulated run).** Execution accuracy is 76.7% against a floor of
80%, and wrong answers among answered are 13.2% against a ceiling of 5%.

Why: for a question the grammar cannot express, the stand-in model often answered a nearby
question instead of refusing. Asked for a percentage, it returned a count per status (fs-028).
Asked for two monthly series, it merged them into one (fs-035). Asked which technicians worked
every month, it returned monthly counts (fs-037). Each of these is a wrong answer, which is
the failure this design exists to prevent. The other 2 wrong answers (fs-022, fs-024) are
questions that can be read with either date; the gold picked one reading.

Next: v0.2 changes the prompt so the model refuses first when a question needs something the
grammar lacks, and measures that on a fresh run. The v0.1 prompt is not changed after seeing
these results.
