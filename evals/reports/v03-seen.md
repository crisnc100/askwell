# Eval report `v03-seen`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `fieldservice.jsonl`.

Status: complete. Spend: $0.1150.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 3 | 98.4% [95-100] (127/129) | 94.6% [89-97] (122/129) | 96.1% [91-98] (122/127) | 1.6% [0-5] (2/129) | 3.9% [2-9] (5/127) | 100.0% [95-100] (72/72) | 0.0% [0-2] (0/201) | fieldservice.jsonl |

## Floor check: fieldservice, anthropic:claude-haiku-5-5 (v0.1 acceptance floor)

- Execution accuracy >= 80%: 94.6% [89-97] (122/129), met
- Wrong answers among answered <= 5%: 3.9% [2-9] (5/127), met

Result: **met** with prompt interpret-v3.

## Ledgerline misses

- `fs-022` (fieldservice, fieldservice.jsonl, trial 1): wrong — rows differ. Tag: **misread**. mistral-small (select-2026-11-11): Both intents had a placeholder reason and no group_by; the first also counted from parts, a fan-out. Grouping work_order_parts by part would answer it.
- `fs-024` (fieldservice, fieldservice.jsonl, trial 1): wrong — rows differ. Tag: **gold_issue**. Haiku 5.5 (v02-seen, v0.2 grammar): Wrong in 1 of 3 trials on the same ambiguous date as below. mistral-small (select-2026-11-11): Ambiguous date: "did work for last month" was read as completed last month; the gold uses opened last month. Both readings are defensible.
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs a per-technician check that completions occurred in each month of last quarter, which requires counting distinct months per technician. The intent cannot express a distinct count of periods.. Tag: **grammar_gap**. Haiku 5.5 (v02-seen, v0.2 grammar): Refused correctly in 3 of 3 trials. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.
- `fs-022` (fieldservice, fieldservice.jsonl, trial 2): wrong — rows differ. Tag: **misread**. mistral-small (select-2026-11-11): Both intents had a placeholder reason and no group_by; the first also counted from parts, a fan-out. Grouping work_order_parts by part would answer it.
- `fs-034` (fieldservice, fieldservice.jsonl, trial 2): wrong — rows differ. Tag: **misread**. Haiku 5.5 (v02-seen, v0.2 grammar): Wrong in 1 of 3 trials: grouped by customer id, not customer name. mistral-small (select-2026-11-11): The first intent was a row list from customers with filters on work orders; the retry grouped by customer with a year grain on an ID and filtered the same date twice.
- `fs-037` (fieldservice, fieldservice.jsonl, trial 2): refused — it needs a distinct count of months per technician (every month of last quarter has at least one completed work order), and the intent cannot express a distinct count of periods. Tag: **grammar_gap**. Haiku 5.5 (v02-seen, v0.2 grammar): Refused correctly in 3 of 3 trials. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.
- `fs-034` (fieldservice, fieldservice.jsonl, trial 3): wrong — rows differ. Tag: **misread**. Haiku 5.5 (v02-seen, v0.2 grammar): Wrong in 1 of 3 trials: grouped by customer id, not customer name. mistral-small (select-2026-11-11): The first intent was a row list from customers with filters on work orders; the retry grouped by customer with a year grain on an ID and filtered the same date twice.

## Where a baseline beat Ledgerline

None.

## Question-level accuracy

A question counts as right when it is right in more than half of its planned trials; a trial that did not finish counts as not right. The interval is over distinct questions.

| Schema | System | Model | Right | Gold |
|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 93.0% [81-98] (40/43) | fieldservice.jsonl |
