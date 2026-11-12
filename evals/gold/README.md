# Gold sets

The questions and answers the eval scores against. They were frozen before any intent
code existed, so the eval is not fitted to what the intent can express.

Four files are frozen: `fieldservice.jsonl`, `holdout-v02.jsonl`, `spider_ids.json` and
`spider_selection.py`. `MANIFEST.json` holds the SHA-256 of each one, and a test fails if
any hash is off. To change a frozen file, run

    uv run python -m evals.gold.manifest --update --reason "why the gold had to change"

which rewrites the hashes, bumps the revision and adds the reason to `CHANGELOG.md`.
`--check` compares without writing.

## `fieldservice.jsonl`

One JSON object per line: `id`, `category`, `difficulty`, `features`, `question`,
`gold_sql`, `ordered`, `refusal_reason`. The schema is `ledgerline/gold.py`.

- **Categories** (`builds/v01/plan.md`, Definitions): `in_schema` items have a `gold_sql` that must
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

## `holdout-v02.jsonl`

The v0.2 held-out set: 40 items in the same format (28 in_schema, 6 out_of_schema,
6 should_refuse), ids `ho-001` to `ho-040`. A separate writer wrote it before any v0.2
code, from the schema, the registry descriptions and this README only, without seeing
the fieldservice questions or the grammar change. Only its SHA-256 was committed then,
under `pending` (revision 3). `--promote` moved it into the frozen files (revision 4),
and refuses a file whose hash differs from the pending one.

Revision 5 changed only how 14 answers are presented, before any held-out result: no
rounding, periods as dates, and ho-003 as a fraction. `CHANGELOG.md` lists each edit.
No question, filter or join changed. `tests/test_gold_manifest.py` proves it two ways:
it pins the committed file's SHA-256 byte for byte, and it undoes exactly those 14 edits
on the raw text and checks that the result has the pending hash from before any v0.2
code.

## `spider_ids.json`

The Spider questions the eval uses, as IDs only: an ID is a question's 0-based index in
Spider's `dev.json`. Spider is licensed CC BY-SA 4.0, so no Spider question text, SQL or
data is committed. `uv run python -m scripts.fetch_benchmarks` downloads Spider into the
gitignored `data/` folder and checks the archive's pinned SHA-256.

`spider_selection.py` holds the selection rule and produced this file: 5 databases drawn
with a fixed seed, then 50 questions from each, stratified by Spider's own hardness
levels. Its docstring states the rule in full. `--check` recomputes the selection from
`dev.json` and compares it with the committed file.
