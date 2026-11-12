# Failures

Four questions Ledgerline got wrong or refused in the simulated run `sim-1`
([report](../../evals/reports/sim-1.md)). The model answers in that run were written by a
stand-in model (claude-haiku-5-5) for the target model (`openai/gpt-oss-120b`), so these
show how the system behaves, not how the target model behaves.

All four come from fieldservice, the synthetic demo database. Spider questions are left
out on purpose: their text is never copied into this repository.

Each miss has a *category*, given when the run was reviewed (`evals/triage/fieldservice.yaml`):

- `grammar_gap`: the question needs something an intent cannot express.
- `gold_issue`: the expected answer (the *gold*) is itself doubtful.

| Question | What happened | Category |
|---|---|---|
| [fs-028](fs-028-percentage.md) | Asked for a percentage, got counts | `grammar_gap`, wrong answer |
| [fs-035](fs-035-two-dates.md) | Asked for two monthly series, got one series cut by the wrong date | `grammar_gap`, wrong answer |
| [fs-025](fs-025-date-difference.md) | Asked for an average duration, refused | `grammar_gap`, refusal |
| [fs-022](fs-022-which-date.md) | "Used over the last 12 months" read with a different date than the gold | `gold_issue`, wrong answer |

A wrong answer is worse than a refusal. A refusal tells the person to look elsewhere; a
wrong table of numbers looks just like a right one. The first two are the kind of miss
Ledgerline exists to prevent: the model filled in a valid intent for a nearby question
instead of refusing. They are 2 of the 5 wrong answers (5 of 38 answered) that put
Ledgerline over its v0.1 limit of 5% wrong.

## In v0.2

v0.2 added ratios, conditional counts and two-date series, and tells the model to refuse
first ([ADR-007](../adr/ADR-007-grammar-v02.md)). fs-028 and fs-035 are now right in every
trial, but they are seen questions, so the headline is a set of 40 held-out questions
written before the v0.2 code ([report](../../evals/reports/v02-holdout.md)). There, 14 of
54 answers were wrong over 3 trials:

- 12 differ from the gold only in form or in how ties are broken: the gold also returns
  an id column (ho-020, ho-024, ho-028), or breaks ties by a column the question does not
  name (ho-022, and fifth place in ho-028).
- 2 are a misread (ho-010): the model left cancelled jobs out of "visits on the
  schedule", which the question does not ask for.

The other 30 misses are correct refusals of 10 questions v0.2 still cannot express:
durations between two dates, products of fields, "has none" questions, distinct counts of
periods and a comparison with an average.
