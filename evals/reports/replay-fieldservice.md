# Eval report `replay-fieldservice`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `fieldservice.jsonl`.

Status: complete. Spend: $0.0591.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 1 | 88.4% [76-95] (38/43) | 88.4% [76-95] (38/43) | 100.0% [91-100] (38/38) | 11.6% [5-24] (5/43) | 0.0% [0-9] (0/38) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) | fieldservice.jsonl |
| fieldservice | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [92-100] (43/43) | 74.4% [60-85] (32/43) | 74.4% [60-85] (32/43) | 0.0% [0-8] (0/43) | 25.6% [15-40] (11/43) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) | fieldservice.jsonl |

## Floor check: fieldservice, anthropic:claude-haiku-5-5 (v0.1 acceptance floor)

- Execution accuracy >= 80%: 88.4% [76-95] (38/43), met
- Wrong answers among answered <= 5%: 0.0% [0-9] (0/38), met

Result: **met** in v0.2 on the seen questions (live, default model).
Why: Seen questions: v0.2 was designed from two of them (fs-028, fs-035), so this is not the headline. In v02-seen (3 trials) accuracy is 111 of 129 (86.0%) and wrong answers are 2 of 113 answered (1.8%). fs-028, fs-035 and fs-041 are right in every trial. Of the misses, 15 are correct refusals of questions v0.2 still cannot express, 2 are misreads and 1 is a question that can be read with either of two dates. v0.1 (select-haiku-2026-11-11, 1 trial) had 2 wrong of 37 answered (5.4%).
Next: The held-out result (v02-holdout) is the headline. The v0.2 prompt and grammar are not changed after seeing these results.

## Ledgerline misses

- `fs-025` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs a duration between two dates (opened_at to completed_at), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (v02-seen, v0.2 grammar): Refused correctly in 3 of 3 trials. Haiku 5.5 (select-haiku-2026-11-11): Needs the difference between two dates (opened to completed). Refused correctly, naming the missing duration. mistral-small (select-2026-11-11): Needs the difference between two dates (opened to completed). Refused, by failing validation twice.
- `fs-030` (fieldservice, fieldservice.jsonl, trial 1): refused — parts revenue needs the product of quantity (work_order_parts) and unit_price (parts), and the intent cannot express a product of two fields. Tag: **grammar_gap**. Haiku 5.5 (v02-seen, v0.2 grammar): Refused correctly in 3 of 3 trials. Haiku 5.5 (select-haiku-2026-11-11): Needs a computed value (quantity times unit price). Refused correctly. mistral-small (select-2026-11-11): Needs a computed value (quantity times unit price). Refused, by failing validation twice.
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs a distinct count of months per technician (or a test that every month has at least one completion), and the intent cannot express a distinct count of periods or a per-period presence check. Tag: **grammar_gap**. Haiku 5.5 (v02-seen, v0.2 grammar): Refused correctly in 3 of 3 trials. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.
- `fs-039` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs the time from opened_at to completed_at compared against 2 days, which is a duration between two dates that the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (v02-seen, v0.2 grammar): Refused correctly in 3 of 3 trials. Haiku 5.5 (select-haiku-2026-11-11): Needs date arithmetic and a ratio. Refused correctly. mistral-small (select-2026-11-11): Needs date arithmetic and a ratio. Refused, by failing validation twice.
- `fs-042` (fieldservice, fieldservice.jsonl, trial 1): refused — the question asks for sites with no related work orders (a 'has none' question), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (v02-seen, v0.2 grammar): Refused correctly in 3 of 3 trials. Haiku 5.5 (select-haiku-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly. mistral-small (select-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly.

## Where a baseline beat Ledgerline

- `fs-025` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-030` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-042` (fieldservice, fieldservice.jsonl, trial 1): oneshot
