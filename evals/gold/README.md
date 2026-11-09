# Gold sets

Frozen before any intent code exists (see `MANIFEST.json` and `CHANGELOG.md`).

## `fieldservice.jsonl`

One JSON object per line: `id`, `category`, `difficulty`, `features`, `question`,
`gold_sql`, `ordered`, `refusal_reason`. The schema is `ledgerline/gold.py`.

- **Categories** (plan.md, Definitions): `in_schema` items have a `gold_sql` that must
  execute and return a non-empty, deterministic result; `out_of_schema` items ask for data
  the database does not hold; `should_refuse` items ask for something that exists but is
  excluded or unsafe (hidden `users.email` / `users.password_hash`, or any write). Refusal
  items have `gold_sql: null` and a `refusal_reason`.
- **Questions** are written as a field-service manager would ask them, from the schema
  and these definitions only. Several are deliberately beyond any simple query grammar
  (subqueries, anti-joins, ratios, per-month series); missing them is a coverage finding,
  not a gold error.
- **Reference time** is `LEDGERLINE_NOW = 2026-06-30T00:00:00Z`. Relative periods are
  written into `gold_sql` as literals: last month = May 2026; last quarter = 2026-Q1;
  this year / so far = 2026-01-01 up to the reference time; last year = 2025; last
  12 months = 2025-06-30 up to the reference time; last 90 days = 2026-04-01 onward;
  last 6 months = 2025-12-30 onward.
- **Conventions** where a question leaves room: "invoiced amount" and "revenue" exclude
  void invoices when the question says so; "completed" means `status = 'completed'`;
  a technician's work is attributed through `work_orders.technician_id`; customer
  attributes reach work through `sites.customer_id`.
- **`ordered: true`** when the gold has a meaningful `ORDER BY` (top-N, "most expensive
  first", per-month series); every such ORDER BY ends with a unique tiebreaker so the
  result is deterministic.
- `gold_sql` is Postgres dialect and runs as the read-only role.
