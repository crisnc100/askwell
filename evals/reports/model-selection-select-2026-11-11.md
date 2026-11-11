# Model selection: select-2026-11-11

ADR-004's rule (Amendment 1), applied to one live fieldservice pass of the `ledgerline` system. Costs are measured, not list prices.

| Model | Cost per question (USD) | Correct | Wrong | Refusal recall | Unreadable | p50 latency | Gates failed |
|---|---|---|---|---|---|---|---|
| `mistralai/mistral-small-24b-instruct-2501` | 0.000145 | 21/43 | 6 | 24/24 | 0/91 (0.0%) | 1.29 s | none |
| `google/gemma-4-26b-a4b-it` | 0.000219 | 23/43 | 7 | 23/24 | 0/93 (0.0%) | 1.31 s | none |
| `openai/gpt-oss-120b` | 0.000277 | 25/43 | 4 | 24/24 | 7/84 (8.3%) | 2.48 s | unreadable |
| `openai/gpt-4o-mini` | 0.000319 | 19/43 | 5 | 24/24 | 4/79 (5.1%) | 1.28 s | unreadable |

- **Best eligible:** `google/gemma-4-26b-a4b-it` (23 correct).
- **Default:** `mistralai/mistral-small-24b-instruct-2501`.
- **Second:** `google/gemma-4-26b-a4b-it`.
