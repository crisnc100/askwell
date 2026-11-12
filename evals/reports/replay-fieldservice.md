# Eval report `replay-fieldservice`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `fieldservice.jsonl`.

Status: complete. Spend: $0.0588.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 1 | 88.4% [76-95] (38/43) | 88.4% [76-95] (38/43) | 100.0% [91-100] (38/38) | 11.6% [5-24] (5/43) | 0.0% [0-9] (0/38) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) | fieldservice.jsonl |
| fieldservice | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [92-100] (43/43) | 76.7% [62-87] (33/43) | 76.7% [62-87] (33/43) | 0.0% [0-8] (0/43) | 23.3% [13-38] (10/43) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) | fieldservice.jsonl |

## Floor check: fieldservice, anthropic:claude-haiku-5-5 (v0.1 acceptance floor)

- Execution accuracy >= 80%: 88.4% [76-95] (38/43), met
- Wrong answers among answered <= 5%: 0.0% [0-9] (0/38), met

Result: **met** in v0.1 (live, default model).
Why: Accuracy is met (35 of 43); wrong answers miss by one (2 of 37 answered, 5.4%). Both wrong answers are questions the intent grammar cannot express (a ratio, two date fields in one series), where the model answered a nearby question instead of refusing. Of its 6 refusals, 5 are correct refusals of such questions; 1 (fs-038) is a misread after one intent failed validation.
Next: v0.2 changes the prompt and the grammar, then measures them on a fresh run. The v0.1 prompt is not changed after seeing these results.

## Ledgerline misses

- `fs-025` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs a duration between two dates (opened_at to completed_at) in days, which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs the difference between two dates (opened to completed). Refused correctly, naming the missing duration. mistral-small (select-2026-11-11): Needs the difference between two dates (opened to completed). Refused, by failing validation twice.
- `fs-030` (fieldservice, fieldservice.jsonl, trial 1): refused — parts revenue requires multiplying work_order_parts.quantity by parts.unit_price for each line, and the intent cannot express a product of two fields.. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a computed value (quantity times unit price). Refused correctly. mistral-small (select-2026-11-11): Needs a computed value (quantity times unit price). Refused, by failing validation twice.
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): refused — The question needs a distinct count of calendar months per technician (at least one completion in each of the three months of last quarter). The intent cannot count distinct periods, so it cannot test for a completion in every month.. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.
- `fs-039` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs a duration between two dates (opened_at to completed_at) compared against a 2-day threshold, which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs date arithmetic and a ratio. Refused correctly. mistral-small (select-2026-11-11): Needs date arithmetic and a ratio. Refused, by failing validation twice.
- `fs-042` (fieldservice, fieldservice.jsonl, trial 1): refused — the question asks for sites with no related work orders (a 'has none' question), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly. mistral-small (select-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly.

## Where a baseline beat Ledgerline

- `fs-025` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-030` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-042` (fieldservice, fieldservice.jsonl, trial 1): oneshot
