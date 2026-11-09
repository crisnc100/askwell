# Eval report `replay-fieldservice`

> **Model responses simulated by claude-haiku-5-5, standing in for openai/gpt-oss-120b. This is not an OpenRouter measurement.**

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).
- One target model (openai/gpt-oss-120b). A second model runs once there is an OpenRouter key: simulating a second vendor with the same stand-in would add no real diversity.
- Trials: 1. Repeating trials with the same stand-in would measure the stand-in's variance, not the target model's.

Status: complete. Spend: $0.0000.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors |
|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | openai/gpt-oss-120b | 1 | 88.4% [76-95] (38/43) | 76.7% [62-87] (33/43) | 86.8% [73-94] (33/38) | 11.6% [5-24] (5/43) | 13.2% [6-27] (5/38) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) |
| fieldservice | oneshot | openai/gpt-oss-120b | 1 | 100.0% [92-100] (43/43) | 69.8% [55-81] (30/43) | 69.8% [55-81] (30/43) | 0.0% [0-8] (0/43) | 30.2% [19-45] (13/43) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) |

## Floor check: fieldservice (plan.md L11)

- Execution accuracy >= 80%: 76.7% [62-87] (33/43), NOT met
- Wrong answers among answered <= 5%: 13.2% [6-27] (5/38), NOT met

Result: **not met** in v0.1 (simulated run).
Why: For questions the intent grammar cannot express, the stand-in model often answers a nearby question instead of refusing. Example: asked for a percentage, it returned a count per status. Each such answer is a wrong answer, not a refusal.
Next: v0.2 changes the prompt to refuse first when a question needs something the grammar lacks, then measures it on a fresh run. The v0.1 prompt is not changed after seeing these results.

## Ledgerline misses

- `fs-022` (fieldservice, trial 1): wrong — rows differ. Tag: **gold_issue**. Ambiguous date: the answer filtered on completion date (when parts are used), the gold on opening date. Both readings are defensible.
- `fs-024` (fieldservice, trial 1): wrong — rows differ. Tag: **gold_issue**. Ambiguous date: 'did work for last month' was read as completed last month; the gold uses opened last month.
- `fs-025` (fieldservice, trial 1): refused — Average days to complete needs the elapsed time between work_orders.opened_at and work_orders.completed_at, and the registry has no way to compute a difference between two date fields. Metrics aggregate a single field only.. Tag: **grammar_gap**. Needs the difference between two dates (opened to completed). Refused correctly.
- `fs-028` (fieldservice, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a ratio of two counts. The model returned counts per status instead of refusing: a wrong answer, not a refusal.
- `fs-030` (fieldservice, trial 1): refused — Parts revenue needs quantity times unit_price per line, and the registry has no computed line-revenue field. A metric aggregates a single field, so summing unit_price or quantity alone would give a different number.. Tag: **grammar_gap**. Needs a computed value (quantity times unit price). Refused correctly.
- `fs-035` (fieldservice, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs two date fields in one monthly series. The model counted completions among the orders opened each month instead of refusing: a wrong answer.
- `fs-037` (fieldservice, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a distinct count of months in HAVING. The model returned per-technician monthly counts instead of refusing: a wrong answer.
- `fs-039` (fieldservice, trial 1): refused — The question needs a 2-day elapsed-time test between completed_at and opened_at and a ratio of two counts; the intent language supports neither a date arithmetic comparison nor a share metric.. Tag: **grammar_gap**. Needs date arithmetic and a ratio. Refused correctly.
- `fs-041` (fieldservice, trial 1): refused — The question needs two different row sets at once: a sum over unpaid and overdue invoices, and a count of overdue invoices only per customer. Filters apply to every row and having applies to whole groups, so the registry cannot express a conditional count alongside the sum.. Tag: **grammar_gap**. Needs a conditional count beside a sum. Refused correctly.
- `fs-042` (fieldservice, trial 1): refused — Finding sites with no work orders in a window needs an anti-join (sites with no matching work_orders rows), which this intent format cannot express. Filters on work_orders fields only return sites that do have matching rows.. Tag: **grammar_gap**. Needs an anti-join (sites with no work orders). Refused correctly.

## Where a baseline beat Ledgerline

- `fs-025` (fieldservice, trial 1): oneshot
- `fs-030` (fieldservice, trial 1): oneshot
- `fs-037` (fieldservice, trial 1): oneshot
- `fs-042` (fieldservice, trial 1): oneshot
