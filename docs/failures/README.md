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
