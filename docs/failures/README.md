# Failures

Four questions Askwell got wrong or refused in the simulated run `sim-1`
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
Askwell exists to prevent: the model filled in a valid intent for a nearby question
instead of refusing. They are 2 of the 5 wrong answers (5 of 38 answered) that put
Askwell over its v0.1 limit of 5% wrong.

## In v0.2

v0.2 added ratios, conditional counts and two-date series, and tells the model to refuse
first ([ADR-007](../adr/ADR-007-grammar-v02.md)). fs-028 and fs-035 are now right in every
trial, but they are seen questions, so the headline is a set of 40 held-out questions
written before the v0.2 code ([report](../../evals/reports/v02-holdout.md)). There, 14 of
54 answers were wrong over 3 trials:

- 12 differ from the gold only in form or in how ties are broken: the gold also returns
  an id column (ho-020, ho-024, ho-028), or breaks ties by a column the question does not
  name (ho-022, and fifth place in ho-028).
- 2 are misreads of one question (ho-010). In one trial the model left cancelled jobs
  out of "visits on the schedule", which the question does not ask for. In another it
  read "January through June" as year to date, which stops at the reference date and
  cuts the end of June.

The other 30 misses are correct refusals of 10 questions v0.2 still cannot express:
durations between two dates, products of fields, "has none" questions, distinct counts of
periods and a comparison with an average.

## In v0.3

v0.3 was measured on 96 new held-out questions, written before the code and revealed
after it was frozen ([ADR-008](../adr/ADR-008-accuracy-v03.md),
[report](../../evals/reports/v03-holdout.md)). Over 3 trials, 8 of 193 answers were
wrong (main before v0.3: 12 of 164):

- h3-065, in every trial, returns the gold's values but is scored wrong. Its gold has
  3,649 rows in no order, past the 1,000-row cap, and the scorer keeps a different 1,000
  rows than Askwell returns. A scoring limit, tagged `gold_issue`.
- h3-005, in 2 trials, returns a percentage where the question asks for a fraction.
- h3-038 and h3-045, once each, return an id without the name the gold also returns.
- h3-058, once, puts age buckets in the columns of one row instead of one row each.

31 questions are refused in every trial, almost all correctly: they need window
functions, ranks within groups, medians, set intersections or per-group totals beside
each row, which the grammar does not have.

The untriaged Spider databases are where v0.3's deploy gate fails. Their misses are
listed by ID only in `evals/triage/spider_*.yaml`. On world_1, three of the new wrong
answers come from ties: the gold keeps one row of a tie, and the answer does not
return just that row. Another limit of the scorer: when a gold stores a number as text,
an answer with the number itself is scored wrong; ADR-008 lists those answers and shows
the figures both ways.
