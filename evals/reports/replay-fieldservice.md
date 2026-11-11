# Eval report `replay-fieldservice`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Status: complete. Spend: $0.0159.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors |
|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | mistralai/mistral-small-24b-instruct-2501 | 1 | 62.8% [48-76] (27/43) | 48.8% [35-63] (21/43) | 77.8% [59-89] (21/27) | 37.2% [24-52] (16/43) | 22.2% [11-41] (6/27) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) |
| fieldservice | oneshot | mistralai/mistral-small-24b-instruct-2501 | 1 | 100.0% [92-100] (43/43) | 46.5% [33-61] (20/43) | 46.5% [33-61] (20/43) | 0.0% [0-8] (0/43) | 52.4% [38-67] (22/42) | 95.8% [80-99] (23/24) | 3.0% [1-10] (2/67) |

## Floor check: fieldservice, mistralai/mistral-small-24b-instruct-2501 (v0.1 acceptance floor)

- Execution accuracy >= 80%: 48.8% [35-63] (21/43), NOT met
- Wrong answers among answered <= 5%: 22.2% [11-41] (6/27), NOT met

Result: **not met** in v0.1 (live, default model).
Why: Most misses are refusals. 16 of the 43 answerable questions end in one: 12 because the model's intent failed validation twice (most often a malformed intent shape, or a sort on a field that is neither a metric nor a group), and 4 because the model judged the question unanswerable. Eight questions need things the intent grammar cannot express, so no model can score above 81.4%. Of the 27 answers given, 6 are wrong.
Next: v0.2 changes the prompt and the grammar, then measures them on a fresh run. The v0.1 prompt is not changed after seeing these results.

## Ledgerline misses

- `fs-009` (fieldservice, trial 1): refused — The question asks for a list of technicians, but the registry does not include a field for technician names.. Tag: **misread**. The first intent was right except for a placeholder reason. On the retry the model said the registry has no technician names, which is wrong (full_name is visible).
- `fs-011` (fieldservice, trial 1): wrong — rows differ. Tag: **misread**. Asked for the most expensive part and its price, the model returned the highest price and a count, not the part. A row list sorted by price with a limit of 1 would answer it.
- `fs-018` (fieldservice, trial 1): refused — no valid query after 2 attempts (intent_shape, invalid_order_by). Tag: **misread**. Both intents had a placeholder reason, no group_by, and a sort on an issued_at_month field that does not exist. A monthly group on issued_at would answer it.
- `fs-020` (fieldservice, trial 1): wrong — rows differ. Tag: **misread**. The model added a year-to-date filter on completion date that the question does not ask for. The gold averages every completed job.
- `fs-021` (fieldservice, trial 1): refused — no valid query after 2 attempts (grain_type). Tag: **misread**. The first intent counted from technicians, a fan-out the validator rightly refused. The retry re-based on work orders but asked for a day grain on a text field.
- `fs-022` (fieldservice, trial 1): refused — no valid query after 2 attempts (intent_shape). Tag: **misread**. Both intents had a placeholder reason and no group_by; the first also counted from parts, a fan-out. Grouping work_order_parts by part would answer it.
- `fs-023` (fieldservice, trial 1): refused — no valid query after 2 attempts (intent_shape). Tag: **misread**. Both intents were right except for a placeholder reason ("None"), and neither kept the "at least 25" condition.
- `fs-024` (fieldservice, trial 1): wrong — unknown_field. Tag: **gold_issue**. Ambiguous date: "did work for last month" was read as completed last month; the gold uses opened last month. Both readings are defensible.
- `fs-025` (fieldservice, trial 1): refused — no valid query after 2 attempts (date_range_duplicate). Tag: **grammar_gap**. Needs the difference between two dates (opened to completed). Refused, by failing validation twice.
- `fs-028` (fieldservice, trial 1): wrong — date_range_duplicate. Tag: **grammar_gap**. Needs a ratio of two counts. The model returned two counts of cancelled orders instead of refusing: a wrong answer, not a refusal.
- `fs-030` (fieldservice, trial 1): refused — no valid query after 2 attempts (invalid_order_by, unknown_field). Tag: **grammar_gap**. Needs a computed value (quantity times unit price). Refused, by failing validation twice.
- `fs-032` (fieldservice, trial 1): refused — no valid query after 2 attempts (fan_out, intent_shape, invalid_order_by). Tag: **misread**. Both intents had a placeholder reason and no group_by, and summed invoices from technicians or work orders, a fan-out. Grouping invoices by technician would answer it.
- `fs-033` (fieldservice, trial 1): refused — no valid query after 2 attempts (intent_shape). Tag: **misread**. Both intents had a placeholder reason and no group_by; the first sorted on fields that do not exist. Grouping invoices by customer region and quarter would answer it.
- `fs-034` (fieldservice, trial 1): refused — no valid query after 2 attempts (date_range_duplicate, grain_type). Tag: **misread**. The first intent was a row list from customers with filters on work orders; the retry grouped by customer with a year grain on an ID and filtered the same date twice.
- `fs-035` (fieldservice, trial 1): refused — no valid query after 2 attempts (intent_shape, invalid_order_by). Tag: **grammar_gap**. Needs two date fields in one monthly series. Refused, by failing validation twice.
- `fs-036` (fieldservice, trial 1): refused — no valid query after 2 attempts (intent_shape, invalid_order_by). Tag: **misread**. Both intents had a placeholder reason and no group_by, and sorted on a field that does not exist; the "at least 100 invoices" condition was dropped.
- `fs-037` (fieldservice, trial 1): refused — The question requires a join that would double count rows, which is not allowed.. Tag: **grammar_gap**. Needs a distinct count of months in HAVING. Refused correctly.
- `fs-038` (fieldservice, trial 1): wrong — fan_out, invalid_order_by. Tag: **misread**. The model left out the "paid" filter and grouped by site and customer ID instead of by customer, with no "more than $20,000" condition.
- `fs-039` (fieldservice, trial 1): refused — no valid query after 2 attempts (date_range_duplicate, grain_type). Tag: **grammar_gap**. Needs date arithmetic and a ratio. Refused, by failing validation twice.
- `fs-041` (fieldservice, trial 1): refused — The question requires aggregating invoices, which are in a one-to-many relationship with customers, and ordering by the aggregated value. This is not supported.. Tag: **grammar_gap**. Needs a conditional count beside a sum. Refused correctly.
- `fs-042` (fieldservice, trial 1): refused — The question asks for sites with no work orders, but the registry does not have a field for the last work order date on a site.. Tag: **grammar_gap**. Needs an anti-join (sites with no work orders). Refused correctly.
- `fs-043` (fieldservice, trial 1): wrong — fan_out, intent_shape, invalid_order_by. Tag: **misread**. The model dropped the "at least 20 completed jobs" condition and sorted by job count instead of average hours.

## Where a baseline beat Ledgerline

- `fs-009` (fieldservice, trial 1): oneshot
- `fs-011` (fieldservice, trial 1): oneshot
- `fs-020` (fieldservice, trial 1): oneshot
- `fs-023` (fieldservice, trial 1): oneshot
- `fs-025` (fieldservice, trial 1): oneshot
- `fs-030` (fieldservice, trial 1): oneshot
- `fs-032` (fieldservice, trial 1): oneshot
- `fs-043` (fieldservice, trial 1): oneshot
