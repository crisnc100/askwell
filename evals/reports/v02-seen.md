# Eval report `v02-seen`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `fieldservice.jsonl`.

Status: complete. Spend: $0.1782.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | anthropic:claude-haiku-5-5 | 3 | 87.6% [81-92] (113/129) | 86.0% [79-91] (111/129) | 98.2% [94-100] (111/113) | 12.4% [8-19] (16/129) | 1.8% [0-6] (2/113) | 100.0% [95-100] (72/72) | 0.0% [0-2] (0/201) | fieldservice.jsonl |
| fieldservice | oneshot | anthropic:claude-haiku-5-5 | 3 | 100.0% [97-100] (129/129) | 76.7% [69-83] (99/129) | 76.7% [69-83] (99/129) | 0.0% [0-3] (0/129) | 23.3% [17-31] (30/129) | 100.0% [95-100] (72/72) | 0.0% [0-2] (0/201) | fieldservice.jsonl |

## Floor check: fieldservice, anthropic:claude-haiku-5-5 (v0.1 acceptance floor)

- Execution accuracy >= 80%: 86.0% [79-91] (111/129), met
- Wrong answers among answered <= 5%: 1.8% [0-6] (2/113), met

Result: **met** in v0.1 (live, default model).
Why: Accuracy is met (35 of 43); wrong answers miss by one (2 of 37 answered, 5.4%). Both wrong answers are questions the intent grammar cannot express (a ratio, two date fields in one series), where the model answered a nearby question instead of refusing. Of its 6 refusals, 5 are correct refusals of such questions; 1 (fs-038) is a misread after one intent failed validation.
Next: v0.2 changes the prompt and the grammar, then measures them on a fresh run. The v0.1 prompt is not changed after seeing these results.

## Ledgerline misses

- `fs-025` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs a duration between two dates (opened_at to completed_at), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs the difference between two dates (opened to completed). Refused correctly, naming the missing duration. mistral-small (select-2026-11-11): Needs the difference between two dates (opened to completed). Refused, by failing validation twice.
- `fs-030` (fieldservice, fieldservice.jsonl, trial 1): refused — parts revenue needs the product of quantity (work_order_parts) and unit_price (parts), and the intent cannot express a product of two fields. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a computed value (quantity times unit price). Refused correctly. mistral-small (select-2026-11-11): Needs a computed value (quantity times unit price). Refused, by failing validation twice.
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs a distinct count of months per technician (or a test that every month has at least one completion), and the intent cannot express a distinct count of periods or a per-period presence check. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.
- `fs-039` (fieldservice, fieldservice.jsonl, trial 1): refused — it needs the time from opened_at to completed_at compared against 2 days, which is a duration between two dates that the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs date arithmetic and a ratio. Refused correctly. mistral-small (select-2026-11-11): Needs date arithmetic and a ratio. Refused, by failing validation twice.
- `fs-042` (fieldservice, fieldservice.jsonl, trial 1): refused — the question asks for sites with no related work orders (a 'has none' question), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly. mistral-small (select-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly.
- `fs-024` (fieldservice, fieldservice.jsonl, trial 2): wrong — rows differ. Tag: **gold_issue**. mistral-small (select-2026-11-11): Ambiguous date: "did work for last month" was read as completed last month; the gold uses opened last month. Both readings are defensible.
- `fs-025` (fieldservice, fieldservice.jsonl, trial 2): refused — it needs a duration between two dates (opened_at to completed_at), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs the difference between two dates (opened to completed). Refused correctly, naming the missing duration. mistral-small (select-2026-11-11): Needs the difference between two dates (opened to completed). Refused, by failing validation twice.
- `fs-030` (fieldservice, fieldservice.jsonl, trial 2): refused — parts revenue is quantity times unit price, which is a product of two fields (work_order_parts.quantity and parts.unit_price), and the intent cannot express a product of fields. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a computed value (quantity times unit price). Refused correctly. mistral-small (select-2026-11-11): Needs a computed value (quantity times unit price). Refused, by failing validation twice.
- `fs-037` (fieldservice, fieldservice.jsonl, trial 2): refused — it needs a distinct count of months per technician (to confirm a completed work order in each of the three months of last quarter), and the intent cannot count distinct periods. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.
- `fs-039` (fieldservice, fieldservice.jsonl, trial 2): refused — it needs a duration between two dates (opened_at to completed_at, within 2 days), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs date arithmetic and a ratio. Refused correctly. mistral-small (select-2026-11-11): Needs date arithmetic and a ratio. Refused, by failing validation twice.
- `fs-042` (fieldservice, fieldservice.jsonl, trial 2): refused — finding sites with no work orders is a 'has none' question (items with no related rows), which this intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly. mistral-small (select-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly.
- `fs-025` (fieldservice, fieldservice.jsonl, trial 3): refused — it needs a duration between two dates (opened_at to completed_at), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs the difference between two dates (opened to completed). Refused correctly, naming the missing duration. mistral-small (select-2026-11-11): Needs the difference between two dates (opened to completed). Refused, by failing validation twice.
- `fs-030` (fieldservice, fieldservice.jsonl, trial 3): refused — parts revenue is quantity times unit price, which is a product of two fields (work_order_parts.quantity and parts.unit_price), and the intent cannot express a product of two fields. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a computed value (quantity times unit price). Refused correctly. mistral-small (select-2026-11-11): Needs a computed value (quantity times unit price). Refused, by failing validation twice.
- `fs-034` (fieldservice, fieldservice.jsonl, trial 3): wrong — rows differ. Tag: **misread**. mistral-small (select-2026-11-11): The first intent was a row list from customers with filters on work orders; the retry grouped by customer with a year grain on an ID and filtered the same date twice.
- `fs-037` (fieldservice, fieldservice.jsonl, trial 3): refused — it needs a distinct count of months per technician (to check that each of the three months has a completed work order), and the intent cannot count distinct periods. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly. mistral-small (select-2026-11-11): Needs a distinct count of months in HAVING. Refused correctly.
- `fs-038` (fieldservice, fieldservice.jsonl, trial 3): refused — Customer names are not reachable from invoices in one join. The path is invoices → work_orders → sites → customers, and the registry only lists direct joins (invoices to work_orders, but not work_orders to customers). The intent cannot name a multi-hop field like customers.name, so the per-customer totals cannot be grouped.. Tag: **misread**. Haiku 5.5 (select-haiku-2026-11-11): The first intent named a field that does not exist; on the retry the model said invoices cannot be grouped by customer. They can: the registry links invoices to customers through work orders and sites. mistral-small (select-2026-11-11): The model left out the "paid" filter and grouped by site and customer ID instead of by customer, with no "more than $20,000" condition.
- `fs-039` (fieldservice, fieldservice.jsonl, trial 3): refused — it needs a duration between two dates (opened_at to completed_at, within 2 days), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs date arithmetic and a ratio. Refused correctly. mistral-small (select-2026-11-11): Needs date arithmetic and a ratio. Refused, by failing validation twice.
- `fs-042` (fieldservice, fieldservice.jsonl, trial 3): refused — it is a 'has none' question (sites with no related work orders in the last 6 months), which the intent cannot express. Tag: **grammar_gap**. Haiku 5.5 (select-haiku-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly. mistral-small (select-2026-11-11): Needs an anti-join (sites with no work orders). Refused correctly.

## Where a baseline beat Ledgerline

- `fs-025` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-030` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-037` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-042` (fieldservice, fieldservice.jsonl, trial 1): oneshot
- `fs-024` (fieldservice, fieldservice.jsonl, trial 2): oneshot
- `fs-025` (fieldservice, fieldservice.jsonl, trial 2): oneshot
- `fs-030` (fieldservice, fieldservice.jsonl, trial 2): oneshot
- `fs-037` (fieldservice, fieldservice.jsonl, trial 2): oneshot
- `fs-042` (fieldservice, fieldservice.jsonl, trial 2): oneshot
- `fs-025` (fieldservice, fieldservice.jsonl, trial 3): oneshot
- `fs-030` (fieldservice, fieldservice.jsonl, trial 3): oneshot
- `fs-034` (fieldservice, fieldservice.jsonl, trial 3): oneshot
- `fs-037` (fieldservice, fieldservice.jsonl, trial 3): oneshot
- `fs-038` (fieldservice, fieldservice.jsonl, trial 3): oneshot
- `fs-042` (fieldservice, fieldservice.jsonl, trial 3): oneshot
