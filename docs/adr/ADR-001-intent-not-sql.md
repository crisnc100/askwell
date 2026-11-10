# ADR-001: The LLM fills a typed intent; it never writes SQL

- **Status:** Proposed. Prediction committed 2026-11-09 (P1), before any intent code.
- **Result:** PENDING (filled in after the P4 live run).

## Context
A data analyst that answers with numbers is only useful if a wrong number is rare and
detectable. LLM-written SQL can be valid, run, and be wrong (a bad join, a missed filter,
a double count) with nothing to catch it. Ledgerline's claim is governance: every answer
comes from a query the system can explain and audit.

## Decision
The model returns a structured intent (`ledgerline/core/intent.py`): an entity, selected
fields, metrics, filters, having, group-by, a date range, order and limit, or
`unanswerable` with a reason. Plain Python validates every field against the registry
and returns typed errors. Code resolves relative dates against `LEDGERLINE_NOW`. A
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
2. **Execution accuracy 60–70%**, below the plan's 80% floor (L11), because of item 1
   plus some misreads. The floor is predicted to fail unless the grammar grows.
3. **Accuracy given attempted ≥ 85%** and **wrong-answer rate given answered ≤ 5%.**
4. **The oneshot baseline answers more but is wrong more:** execution accuracy within
   ±15 points of Ledgerline, and wrong-answer rate given answered ≥ 15%.
5. **Refusal recall ≥ 95%** on the 24 refusal items (13 out_of_schema, 11 should_refuse),
   with zero hidden-field values returned.

## How it is measured
`ledgerline eval --schema fieldservice --systems ledgerline,oneshot,sql_agent --trials 3`,
metrics as defined in `builds/v01/plan.md` (Definitions), Wilson 95% intervals. With 43
items one question is about 2.3 points, so differences under about 10 points are within
noise.

## Result
PENDING.
