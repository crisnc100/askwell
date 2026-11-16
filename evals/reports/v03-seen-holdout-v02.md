# Eval report `v03-seen-holdout-v02`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `holdout-v02.jsonl`.

Status: complete. Spend: $0.0747.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 3 | 92.9% [85-97] (78/84) | 89.3% [81-94] (75/84) | 96.2% [89-99] (75/78) | 7.1% [3-15] (6/84) | 3.8% [1-11] (3/78) | 100.0% [90-100] (36/36) | 0.0% [0-3] (0/120) | holdout-v02.jsonl |

## Floor check: fieldservice, holdout-v02.jsonl, anthropic:claude-haiku-5-5 (v0.1 acceptance floor)

- Execution accuracy >= 80%: 89.3% [81-94] (75/84), met
- Wrong answers among answered <= 5%: 3.8% [1-11] (3/78), met

Result: **met** with prompt interpret-v3.

## Ledgerline misses

- `ho-014` (fieldservice, holdout-v02.jsonl, trial 1): refused — Markup needs (unit_price - unit_cost) times quantity, which is three fields in one expression. A computed value takes exactly two fields and cannot nest, and the intent cannot subtract one aggregate from another, so the total cannot be expressed.. Tag: **grammar_gap**. Haiku 5.5 (v02-holdout, v0.2 grammar): Needs a computed value (quantity times a price difference). Refused correctly in 3 of 3 trials, as with v0.1.
- `ho-017` (fieldservice, holdout-v02.jsonl, trial 1): refused — it needs a distinct count of months per region, which the intent cannot express (distinct count of periods is not supported). Tag: **grammar_gap**. Haiku 5.5 (v02-holdout, v0.2 grammar): Needs a distinct count of months. Refused correctly in 3 of 3 trials. Haiku 5.5 (v02-holdout-before, v0.1 grammar): Wrong in 3 of 3 trials.
- `ho-006` (fieldservice, holdout-v02.jsonl, trial 2): wrong — rows differ. Tag: **grammar_gap**. Haiku 5.5 (v02-holdout-before, v0.1 grammar): Needs a proportion. Answered a nearby grouped count instead: wrong in 3 of 3 trials. Right in all 3 trials with the v0.2 grammar.
- `ho-014` (fieldservice, holdout-v02.jsonl, trial 2): refused — The markup is (unit_price minus unit_cost) times quantity, which combines three fields in one row-level expression. The intent allows only one two-field computation and cannot nest it, so it cannot express the dollar markup per line.. Tag: **grammar_gap**. Haiku 5.5 (v02-holdout, v0.2 grammar): Needs a computed value (quantity times a price difference). Refused correctly in 3 of 3 trials, as with v0.1.
- `ho-017` (fieldservice, holdout-v02.jsonl, trial 2): refused — it needs a distinct count of months per region, and a distinct count of periods is not expressible in this intent. Tag: **grammar_gap**. Haiku 5.5 (v02-holdout, v0.2 grammar): Needs a distinct count of months. Refused correctly in 3 of 3 trials. Haiku 5.5 (v02-holdout-before, v0.1 grammar): Wrong in 3 of 3 trials.
- `ho-019` (fieldservice, holdout-v02.jsonl, trial 2): wrong — rows differ. Tag: **grammar_gap**. Haiku 5.5 (v02-holdout, v0.2 grammar): Needs date arithmetic (days open). Refused correctly in 3 of 3 trials. Haiku 5.5 (v02-holdout-before, v0.1 grammar): Wrong in 3 of 3 trials.
- `ho-014` (fieldservice, holdout-v02.jsonl, trial 3): refused — Markup is (unit_price minus unit_cost) times quantity, which combines three fields. A computed value takes exactly two fields and cannot nest, and the intent cannot subtract one aggregate from another (revenue at price minus cost at cost), so this cannot be expressed.. Tag: **grammar_gap**. Haiku 5.5 (v02-holdout, v0.2 grammar): Needs a computed value (quantity times a price difference). Refused correctly in 3 of 3 trials, as with v0.1.
- `ho-017` (fieldservice, holdout-v02.jsonl, trial 3): refused — it needs a distinct count of months per region, and the intent cannot express a distinct count of periods. Tag: **grammar_gap**. Haiku 5.5 (v02-holdout, v0.2 grammar): Needs a distinct count of months. Refused correctly in 3 of 3 trials. Haiku 5.5 (v02-holdout-before, v0.1 grammar): Wrong in 3 of 3 trials.
- `ho-019` (fieldservice, holdout-v02.jsonl, trial 3): wrong — rows differ. Tag: **grammar_gap**. Haiku 5.5 (v02-holdout, v0.2 grammar): Needs date arithmetic (days open). Refused correctly in 3 of 3 trials. Haiku 5.5 (v02-holdout-before, v0.1 grammar): Wrong in 3 of 3 trials.

## Where a baseline beat Ledgerline

None.

## Question-level accuracy

A question counts as right when it is right in more than half of its planned trials; a trial that did not finish counts as not right. The interval is over distinct questions.

| Schema | System | Model | Right | Gold |
|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 89.3% [73-96] (25/28) | holdout-v02.jsonl |
