# Eval report `replay-fieldservice`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `fieldservice.jsonl`.

Status: complete. Spend: $0.0650.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 1 | 97.7% [88-100] (42/43) | 93.0% [81-98] (40/43) | 95.2% [84-99] (40/42) | 2.3% [0-12] (1/43) | 4.8% [1-16] (2/42) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) | fieldservice.jsonl |
| fieldservice | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [92-100] (43/43) | 81.4% [67-90] (35/43) | 81.4% [67-90] (35/43) | 0.0% [0-8] (0/43) | 18.6% [10-33] (8/43) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) | fieldservice.jsonl |

## Floor check: fieldservice, anthropic:claude-haiku-5-5 (v0.1 acceptance floor)

- Execution accuracy >= 80%: 93.0% [81-98] (40/43), met
- Wrong answers among answered <= 5%: 4.8% [1-16] (2/42), met

Result: **met** with prompt interpret-v3.

## Ledgerline misses

- `fs-022` (fieldservice, fieldservice.jsonl, trial 1): wrong — rows differ. Tag: **misread**. mistral-small (select-2026-11-11): Both intents had a placeholder reason and no group_by; the first also counted from parts, a fan-out. Grouping work_order_parts by part would answer it.
- `fs-024` (fieldservice, fieldservice.jsonl, trial 1): wrong — rows differ. Tag: **gold_issue**. Haiku 5.5 (v02-seen, v0.2 grammar): Wrong in 1 of 3 trials on the same ambiguous date as below. mistral-small (select-2026-11-11): Ambiguous date: "did work for last month" was read as completed last month; the gold uses opened last month. Both readings are defensible.
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs a per-technician check that completions occurred in each month of last quarter, which requires counting distinct months per technician. The intent cannot express a distinct count of periods.. Tag: **grammar_gap**. Haiku 5.5 (v02-seen, v0.2 grammar): Refused correctly in 3 of 3 trials. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.

## Where a baseline beat Ledgerline

- `fs-022` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-024` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): oneshot
