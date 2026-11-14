# Eval report `v03-roles-seen`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `spider_ids.json`.

Status: complete. Spend: $0.0427.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spider_network_1 | ledgerline | anthropic:claude-haiku-5-5 | 3 | 70.8% [59-80] (51/72) | 68.1% [57-78] (49/72) | 96.1% [87-99] (49/51) | 29.2% [20-41] (21/72) | 3.9% [1-13] (2/51) | n/a | 0.0% [0-5] (0/72) | spider_ids.json |
| spider_wta_1 | ledgerline | anthropic:claude-haiku-5-5 | 3 | 83.3% [44-97] (5/6) | 83.3% [44-97] (5/6) | 100.0% [57-100] (5/5) | 16.7% [3-56] (1/6) | 0.0% [0-43] (0/5) | n/a | 0.0% [0-39] (0/6) | spider_ids.json |

## Ledgerline misses

- `spider:894` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:896` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:897` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:898` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:900` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:906` (spider_network_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use. Before: a wrong answer. After: refused.
- `spider:917` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:894` (spider_network_1, spider_ids.json, trial 2): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:896` (spider_network_1, spider_ids.json, trial 2): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:897` (spider_network_1, spider_ids.json, trial 2): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:898` (spider_network_1, spider_ids.json, trial 2): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:900` (spider_network_1, spider_ids.json, trial 2): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:906` (spider_network_1, spider_ids.json, trial 2): wrong — rows differ. Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use. Before: a wrong answer. After: refused.
- `spider:910` (spider_network_1, spider_ids.json, trial 2): refused — refused (unknown_field, unknown_link, unknown_metric). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:917` (spider_network_1, spider_ids.json, trial 2): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:894` (spider_network_1, spider_ids.json, trial 3): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:896` (spider_network_1, spider_ids.json, trial 3): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:897` (spider_network_1, spider_ids.json, trial 3): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:898` (spider_network_1, spider_ids.json, trial 3): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:900` (spider_network_1, spider_ids.json, trial 3): refused — refused (unknown_link, unknown_metric). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:910` (spider_network_1, spider_ids.json, trial 3): refused — refused (invalid_order_by, unknown_field, unknown_metric). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:911` (spider_network_1, spider_ids.json, trial 3): refused — refused (unknown_field, unknown_metric). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:917` (spider_network_1, spider_ids.json, trial 3): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:451` (spider_wta_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.

## Where a baseline beat Ledgerline

None.

## Spider registries (generated by `registry init`, unedited, draft)

- spider_network_1: `60d51b4c9b99b72421e7f024dd0a7ad16e4eb4f02df299945e2e7228fe0213cb`
- spider_wta_1: `807a938123c3f5467290fcab18b29cc9d79c341a9dab73eff6d096b5cb43345a`
