# Eval report `select-haiku-2026-11-11`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Status: complete. Spend: $0.0547.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors |
|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 1 | 86.0% [73-93] (37/43) | 81.4% [67-90] (35/43) | 94.6% [82-99] (35/37) | 14.0% [7-27] (6/43) | 5.4% [1-18] (2/37) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) |
| fieldservice | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [92-100] (43/43) | 79.1% [65-89] (34/43) | 79.1% [65-89] (34/43) | 0.0% [0-8] (0/43) | 20.9% [11-35] (9/43) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) |

## Floor check: fieldservice, anthropic:claude-haiku-5-5 (v0.1 acceptance floor)

- Execution accuracy >= 80%: 81.4% [67-90] (35/43), met
- Wrong answers among answered <= 5%: 5.4% [1-18] (2/37), NOT met

Result: **not met** in v0.1 (live, default model).
Why: Accuracy is met (35 of 43); wrong answers miss by one (2 of 37 answered, 5.4%). Both wrong answers are questions the intent grammar cannot express (a ratio, two date fields in one series), where the model answered a nearby question instead of refusing. Of its 6 refusals, 5 are correct refusals of such questions; 1 (fs-038) is a misread after one intent failed validation.
Next: v0.2 changes the prompt and the grammar, then measures them on a fresh run. The v0.1 prompt is not changed after seeing these results.

## Ledgerline misses

- `fs-025` (fieldservice, trial 1): refused — The registry cannot compute elapsed days between opened_at and completed_at. Metrics aggregate a single field, and no duration field exists. Average labour hours for urgent work orders is available instead, if that helps.. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs the difference between two dates (opened to completed). Refused correctly, naming the missing duration. mistral-small (select-2026-11-11): Needs the difference between two dates (opened to completed). Refused, by failing validation twice.
- `fs-028` (fieldservice, trial 1): wrong — rows differ. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a ratio of two counts. The model returned work order counts per status instead of refusing: a wrong answer, not a refusal. mistral-small (select-2026-11-11): Needs a ratio of two counts. The model returned two counts of cancelled orders instead of refusing: a wrong answer, not a refusal.
- `fs-030` (fieldservice, trial 1): refused — Parts revenue requires multiplying quantity by unit_price per line, and the registry metrics only aggregate a single field. No product or computed revenue measure is available.. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a computed value (quantity times unit price). Refused correctly. mistral-small (select-2026-11-11): Needs a computed value (quantity times unit price). Refused, by failing validation twice.
- `fs-035` (fieldservice, trial 1): wrong — rows differ. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs two date fields in one monthly series. The model counted completions among the orders opened each month instead of refusing: a wrong answer. mistral-small (select-2026-11-11): Needs two date fields in one monthly series. Refused, by failing validation twice.
- `fs-037` (fieldservice, trial 1): refused — The registry can't express a per-technician check that every month in the quarter has at least one completion. A grouped query can't require all months to be present, and count_distinct on completed_at counts distinct timestamps, not distinct months.. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.
- `fs-038` (fieldservice, trial 1): refused — The registry has no direct link from invoices to customers. Invoices join only to work_orders, and customers are reachable only through work_orders and sites, a multi-step path that the registry cannot group by. Customer totals cannot be computed from the listed fields.. Tag: **misread**. Haiku 5.5 (select-haiku-2026-11-11): The first intent named a field that does not exist; on the retry the model said invoices cannot be grouped by customer. They can: the registry links invoices to customers through work orders and sites. mistral-small (select-2026-11-11): The model left out the "paid" filter and grouped by site and customer ID instead of by customer, with no "more than $20,000" condition.
- `fs-039` (fieldservice, trial 1): refused — The registry has no way to express an elapsed-time comparison (completed_at within 2 days of opened_at) or a share computed from two counts. Filters can only compare a field to a fixed value or another field directly, not to a date plus an interval.. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs date arithmetic and a ratio. Refused correctly. mistral-small (select-2026-11-11): Needs date arithmetic and a ratio. Refused, by failing validation twice.
- `fs-042` (fieldservice, trial 1): refused — The registry cannot express 'sites with no work orders in a period'. That needs an anti-join from sites to work_orders, and the only listed relationship runs from work_orders to sites, so it cannot be filtered by the absence of related work orders.. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly. mistral-small (select-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly.

## Where a baseline beat Ledgerline

- `fs-025` (fieldservice, trial 1): oneshot
- `fs-030` (fieldservice, trial 1): oneshot
- `fs-035` (fieldservice, trial 1): oneshot
- `fs-037` (fieldservice, trial 1): oneshot
- `fs-038` (fieldservice, trial 1): oneshot
- `fs-042` (fieldservice, trial 1): oneshot
