# Eval report `rerecord-v3-fieldservice`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `fieldservice.jsonl`.

Status: complete. Spend: $0.0669.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 1 | 97.7% [88-100] (42/43) | 95.3% [85-99] (41/43) | 97.6% [88-100] (41/42) | 2.3% [0-12] (1/43) | 2.4% [0-12] (1/42) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) | fieldservice.jsonl |
| fieldservice | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [92-100] (43/43) | 81.4% [67-90] (35/43) | 81.4% [67-90] (35/43) | 0.0% [0-8] (0/43) | 18.6% [10-33] (8/43) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) | fieldservice.jsonl |

## Floor check: fieldservice, anthropic:claude-haiku-5-5 (v0.1 acceptance floor)

- Execution accuracy >= 80%: 95.3% [85-99] (41/43), met
- Wrong answers among answered <= 5%: 2.4% [0-12] (1/42), met

Result: **met** in v0.2 on the seen questions (live, default model).
Why: Seen questions: v0.2 was designed from two of them (fs-028, fs-035), so this is not the headline. In v02-seen (3 trials) accuracy is 111 of 129 (86.0%) and wrong answers are 2 of 113 answered (1.8%). fs-028, fs-035 and fs-041 are right in every trial. Of the misses, 15 are correct refusals of questions v0.2 still cannot express, 2 are misreads and 1 is a question that can be read with either of two dates. v0.1 (select-haiku-2026-11-11, 1 trial) had 2 wrong of 37 answered (5.4%).
Next: The held-out result (v02-holdout) is the headline. The v0.2 prompt and grammar are not changed after seeing these results.

## Ledgerline misses

- `fs-024` (fieldservice, fieldservice.jsonl, trial 1): wrong — rows differ. Tag: **gold_issue**. Haiku 5.5 (v02-seen, v0.2 grammar): Wrong in 1 of 3 trials on the same ambiguous date as below. mistral-small (select-2026-11-11): Ambiguous date: "did work for last month" was read as completed last month; the gold uses opened last month. Both readings are defensible.
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs a distinct count of months per technician, checked against every month of the quarter, which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (v02-seen, v0.2 grammar): Refused correctly in 3 of 3 trials. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.

## Where a baseline beat Ledgerline

- `fs-024` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): oneshot
