# Model selection: select-haiku-2026-11-11

ADR-004's rule (Amendment 1), applied to one live fieldservice pass of the `ledgerline` system. Costs are measured, not list prices.

| Model | Cost per question (USD) | Correct | Wrong | Refusal recall | Unreadable | p50 latency | Gates failed |
|---|---|---|---|---|---|---|---|
| `anthropic:claude-haiku-5-5` | 0.000415 | 35/43 | 2 | 24/24 | 0/72 (0.0%) | 0.92 s | none |

- **Best eligible:** `anthropic:claude-haiku-5-5` (35 correct).
- **Default:** `anthropic:claude-haiku-5-5`.
- **Second:** none.
