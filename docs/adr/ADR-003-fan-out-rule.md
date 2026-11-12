# ADR-003: Refuse aggregates across a one-to-many join

- **Status:** Proposed. Prediction committed 2026-11-09 (P1).
- **Result:** recorded 2026-11-11 from the simulated run `sim-1` (see Result).

## Context
`work_orders` is one-to-many to both `invoices` and `work_order_parts` (about 8% of
invoiced work orders carry a supplemental invoice by design in the seed). Summing or
counting across such a join inflates the result. The query runs, the number looks
plausible, and it is wrong: the worst failure for a governed analyst.

## Decision
The builder joins only along many-to-one edges from the base entity. The validator
rejects (`fan_out`) any intent that would aggregate after a join along a one-to-many
edge. A row list that reaches the many side is rejected too (`one_to_many_join`). The
validator also rejects ambiguous paths (more than one shortest path,
`ambiguous_path`) rather than picking one.
The model can re-base the question on the many side (for example, aggregate invoices and
join up to work orders), which is always safe.

## Prediction (pre-registered)
1. Zero Askwell wrong answers on fieldservice are caused by fan-out double counting.
2. The rule causes at most 2 `validator_false_reject` misses on fieldservice (a correct
   question refused because the model chose the wrong base entity and the retry did not
   fix it).
3. At least one baseline wrong answer on fieldservice (any trial, oneshot or sql_agent)
   is traced in the miss triage to a one-to-many join that inflated a count or sum.

## Result
Measured on the eval run `sim-1` ([evals/reports/sim-1.md](../../evals/reports/sim-1.md)). Its model answers were **simulated**: claude-haiku-5-5 answered every request as a stand-in for `openai/gpt-oss-120b`, because there is no OpenRouter key yet. A simulated run tests the pipeline and the scoring; it does not measure the target model. One trial.

1. **Zero Askwell wrong answers on fieldservice from fan-out:** held. Askwell gave 5
   wrong answers on fieldservice. The triage tags 2 as `gold_issue` (questions that can be
   read with either of two dates) and 3 as `grammar_gap` (questions it should have
   refused). None came from a one-to-many join.
2. **At most 2 `validator_false_reject` misses on fieldservice:** held. There were none,
   and the `fan_out` check did not fire on any fieldservice question.
3. **At least one baseline wrong answer traced to an inflated join:** not measured. The
   triage covers Askwell's misses only, and the sql_agent baseline is not built yet.
