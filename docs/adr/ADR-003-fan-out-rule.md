# ADR-003: Refuse aggregates across a one-to-many join

- **Status:** Proposed. Prediction committed 2026-11-09 (P1).
- **Result:** PENDING.

## Context
`work_orders` is one-to-many to both `invoices` and `work_order_parts` (about 8% of
invoiced work orders carry a supplemental invoice by design in the seed). Summing or
counting across such a join inflates the result. The query runs, the number looks
plausible, and it is wrong: the worst failure for a governed analyst.

## Decision
The builder joins only along many-to-one edges from the base entity. The validator
rejects (`fan_out`) any intent that would aggregate after a join along a one-to-many
edge, and rejects ambiguous paths (more than one shortest path) rather than picking one.
The model can re-base the question on the many side (for example, aggregate invoices and
join up to work orders), which is always safe.

## Prediction (pre-registered)
1. Zero Ledgerline wrong answers on fieldservice are caused by fan-out double counting.
2. The rule causes at most 2 `validator_false_reject` misses on fieldservice (a correct
   question refused because the model chose the wrong base entity and the retry did not
   fix it).
3. At least one baseline wrong answer on fieldservice (any trial, oneshot or sql_agent)
   is traced in the miss triage to a one-to-many join that inflated a count or sum.

## Result
PENDING.
