# ledgerline

Ledgerline is a governed AI data analyst. A person asks a business question in plain
English. A model turns it into an *intent*: a small, typed description of a query (which
table, which numbers, which filters). Plain Python checks every part of the intent
against a *registry*, a YAML file that says what a database may expose. Only a valid
intent becomes SQL, and that SQL runs read-only.

The model never writes SQL, so it cannot invent a column or slip a value into the query
text. The cost is coverage: a question the intent cannot express is refused.
[ADR-001](docs/adr/ADR-001-intent-not-sql.md) explains the choice.

**Status.** v0.1 runs end to end: ask a question from the command line or over HTTP, and
get the rows back with the SQL that produced them. There is no OpenRouter key yet, so
every model answer in this repo is *simulated*: another model wrote it, standing in for
the target model (see [Simulated answers](#simulated-answers)). The eval results are
labelled that way, and the accuracy floor for fieldservice is not met in v0.1.

## Quick start

You need [uv](https://docs.astral.sh/uv/), Docker, `psql` (the PostgreSQL client) and
Node with npm (CI uses Node 22). The tests run `infra/postgres/roles.sql` with `psql`,
and fail without it. The browser tests need Chromium, installed once with
`cd web && npx playwright install chromium`.

```sh
uv sync
docker compose up -d   # starts Postgres, then runs `ledgerline seed` once
./verify.sh            # every check; the tests use the seeded database
```

Postgres listens on `localhost:56432`. On first start it creates two roles:
`ledgerline_owner`, which owns the data, and `ledgerline_ro`, which can only read. The
defaults in `ledgerline/config.py` match them. To change them, copy `.env.example` to
`.env`.

No API key is needed. Model calls default to replay mode, which answers only from
recorded responses. A model is called live only with `--mode record` or `--mode live`,
with `LEDGERLINE_LLM_MODE=record` or `live` in the environment (it sets the mode for
`ledgerline ask` and the API when no `--mode` is given), or by `ledgerline spike`. Each
of those needs `OPENROUTER_API_KEY`.

## Asking a question

```sh
uv run ledgerline ask "How many invoices are still unpaid?"
```

It prints the whole trace as JSON: the intent, each attempt and its validation result,
the SQL with its parameters, the columns and rows, or a refusal with its reason.
`--schema` picks a schema from `config/schemas.yaml` (default `fieldservice`).

The same pipeline is an HTTP API:

```sh
uv run uvicorn ledgerline.api:create_app --factory
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"schema_id": "fieldservice", "question": "How many invoices are still unpaid?"}'
```

`GET /schemas` lists the schemas, and `GET /schemas/{id}/examples` lists the example
questions. In replay mode only those examples have recorded answers; any other question
gets a 409 (the CLI exits with code 4).

Each question goes through the same steps. The model makes one call and returns an
intent. The validator checks it. If the intent is invalid, the model gets one retry, with
the validator's errors in the message; a second failure is a refusal. A valid intent
becomes SQL and runs read-only. The answer is built by code, not by a model, and the
result rows are never sent to the model. [ADR-002](docs/adr/ADR-002-langgraph-boundary.md)
explains why the graph (built with LangGraph) does no more than that.

Every `ask` and `/ask` writes one row to the audit log (`ask_log`, below), whether it
was answered, refused or failed. In live or record mode each ask also has its own
spending limit (`LEDGERLINE_ASK_BUDGET_USD`, default $0.05). A question that would go
over it is refused, and that refusal is audited too.

## Your data

You can also ask questions about your own CSV files. This runs on your machine for now.
Build the pages once, then start the server:

```sh
(cd web && npm ci && npm run build)
uv run uvicorn ledgerline.api:create_app --factory
```

Open `http://localhost:8000/` and follow the five steps:

1. **Prepare.** Read the rules a file must follow: one table per file, a header row, an
   ID column, `YYYY-MM-DD` dates and plain numbers. A small sample shop is there to try.
   Pick your time zone and start a *workspace*: a private folder of its own under
   `data/workspaces/`. The page gives you a link back to it. Bookmark it; anyone with the
   link can see your data.
2. **Upload** your files. A file with the same name replaces the old one.
3. **Check** reads every file. Each problem names the file, the row, the column and the
   fix, up to 20 per file. Nothing loads until every file passes.
4. **Confirm** shows exactly what the model will be sent: table and column names, types,
   links and your descriptions. You can hide any field. Fields with names that look
   sensitive (email, phone and similar) start hidden.
5. **Ask** a question in plain English. The answer shows the rows and the SQL behind them.

What stays private:

- **Your rows.** They never go to the model. A column's values (an order's statuses, for
  example) go only if you tick "Share these values with the model" on Confirm, because
  shared values leave your machine.
- **The workspace link.** Its id is a random 128-bit code after the `#`, a part of the
  link browsers never send to a server. The pages send it in a request header instead,
  so it never appears in a URL the server sees or logs.
- **Your address.** It is not stored. A keyed hash of it counts your workspaces.
- **Your files.** They are deleted after 7 days without use, or at once with "Delete my
  data". `uv run ledgerline sweep` removes expired workspaces; run it from cron, for
  example once an hour.

Limits: at most 10 files per workspace, and per file 10 MB, 200 columns, 1,000,000 rows
and 10,000 characters per value. Each address gets 3 workspaces at a time, 20 uploads and
30 questions an hour (questions to `/ask` count too). These counts live in the server
process and start again when it restarts. All workspaces together share 2 GB of disk.
Behind a proxy that sets `X-Forwarded-For`, set `LEDGERLINE_TRUST_PROXY=1` so the limits
see the real address. Leave it off otherwise, or any client could claim any address.

Answers on your own data need a live model, because no answers are recorded for your
files. Set `OPENROUTER_API_KEY` and `LEDGERLINE_LLM_MODE=live` (see
[.env.example](.env.example)). Without them, Ask replies "Live answers need a model key;
see the README." Questions like "last month" use today's date in your workspace's time
zone.

## The demo database

`ledgerline seed` drops and rebuilds *fieldservice*, a synthetic field-service business:
customers, sites, technicians, parts, work orders, invoices and back-office users. The
same seed and reference time give the same rows every time. The reference time is
`LEDGERLINE_NOW` (default 2026-06-30 00:00 UTC). The command prints a SHA-256 of the
content, so you can check that two databases match.

The read-only role cannot read `users.email` or `users.password_hash` at all. The
registry hides the same two fields, so they are blocked twice.

## Registries

A registry describes one database. For each *entity* (a table or view) it lists
*fields*. Each field has a type, a description, aliases and these flags:

- `filterable`: may appear in a filter.
- `aggregatable`: may be summed, averaged, or take a min or max. Any visible field can be
  counted.
- `hidden`: may not appear anywhere in an intent.
- `categorical`: has a fixed list of `allowed_values`, and a filter value must be one of
  them. Case is ignored only when that leaves exactly one match. `value_aliases` map
  other words to an allowed value.

The registry also lists *relationships*: which field on the "many" side points at which
key on the "one" side. A registry marked `draft: true` is refused unless the caller
allows drafts. `registries/fieldservice.yaml` is the curated registry for the demo
database.

To draft a registry for another database:

```sh
uv run ledgerline registry init <database-url> -o my.yaml [--values]
uv run ledgerline registry check my.yaml
```

`registry init` opens the database read-only and reads its tables, views, columns and
keys. Where no foreign key is declared, it infers a relationship from a column such as
`customer_id` that names another table's key. Fields with sensitive-looking names
(password, token, email, phone and similar) start hidden. With `--values` it reads the
data and marks a text field categorical when it has at most 50 distinct values (names,
notes and addresses are skipped). On SQLite, a DATE or DATETIME column that holds only
numbers (such as `20010203`) is typed as a number, so a calendar grain on it is refused
rather than returning nulls. The output is always `draft: true`, and the same
database gives the same file. It warns when the connecting role could write.

## Intents, validation and SQL

An intent (`ledgerline/core/intent.py`) has an `intent_type` (`summary`,
`grouped_summary`, `row_list`, or `unanswerable` with a reason), a base `entity`, and
optional `select`, `metrics`, `filters`, `having`, `group_by`, `date_range`, `order_by`
and `limit`. A field is named `entity.field`, or just `field` on the base entity.
Filters can be grouped one level deep (`any_of`, `all_of`) and can compare two columns.
A group-by on a date can take a calendar grain (`day`, `iso_week`, `month`, `quarter`,
`year`). A date range is either a start and end, or a token such as `last_quarter`;
code turns the token into dates using `LEDGERLINE_NOW`, never the model.

The validator (`ledgerline/core/validate.py`) checks an intent against the registry. It
never raises for a bad intent; it returns typed errors such as `unknown_field`,
`hidden_field`, `ambiguous_path` (two equally short join paths: refused, not guessed),
`fan_out` (an aggregate across a one-to-many join, which would double count; see
[ADR-003](docs/adr/ADR-003-fan-out-rule.md)) and `ambiguous_value`. `ErrorCode` in that
file lists them all.

The SQL builder (`ledgerline/core/sqlbuild.py`) writes SQLAlchemy Core. Table and column
names come only from the registry, and every value is a bound parameter. Joins follow
many-to-one relationships only, at most 3 hops from the base entity. A join used only
inside an `any_of` group is a LEFT JOIN, so it does not drop rows that match another
branch. Postgres and SQLite are supported.

The executor (`ledgerline/core/executor.py`) runs the query in a read-only transaction
with a timeout (5 seconds by default) and a row cap (1000 by default); the result says
when rows were cut off. SQLite files are opened read-only. Given an audit log, it writes
one row to `ask_log` for every query it runs, including one that could not connect. The
row holds the question and the intent as given, the validation outcome, the SQL with
placeholders, a SHA-256 of the bound parameters, the row count, the cost, the model and
the outcome. The question and intent can contain the values a person typed, such as a
customer name in a filter, so those values do reach the log. The row never holds the
result rows or the separate list of bound parameters. `ask_log` lives in a separate app
database that the read-only role cannot connect to.

Try it with an intent file, for example `revenue.json`:

```json
{"intent_type": "grouped_summary", "entity": "invoices",
 "metrics": [{"agg": "sum", "field": "amount", "alias": "revenue"}],
 "filters": [{"field": "status", "op": "neq", "value": "void"}],
 "group_by": [{"field": "work_orders.priority"}],
 "date_range": {"field": "issued_at", "relative": "last_quarter"},
 "order_by": [{"target": "revenue", "direction": "desc"}]}
```

```sh
uv run ledgerline compile --registry registries/fieldservice.yaml --intent revenue.json
```

It prints the Postgres SQL with placeholders, then the parameter values. Base the same
question on `work_orders` and sum `invoices.amount`, and it prints a `fan_out` error
instead, because a work order can have more than one invoice.

## Model gateway

`ledgerline/llm/` makes one structured-output call to a model on OpenRouter, through
LangChain. It has four modes: `record`, `replay`, `live` and `export`. In replay mode a
missing recording is an error; it never falls back to a live call. Before each live
call, a budget guard checks the call's worst-case cost against what is left of the
budget, and stops when it would go over. A long eval run saves each finished item, so a
stopped run can resume and its spend still counts.
[ADR-005](docs/adr/ADR-005-replay-and-budget.md) has the details.

`ledgerline spike` checks which candidate models return valid structured output. It
has not run yet. Until it does, the default model is a provisional target,
`openai/gpt-oss-120b`; see [ADR-004](docs/adr/ADR-004-model-choice.md).

## Simulated answers

Without a key, a stand-in model makes the recordings. Export mode writes every request
that has no recording to `evals/pending/`. The stand-in (here a Claude model) answers
each one as the target model would. `ledgerline replay import` (or `ledgerline eval --mode
import`) checks each JSON answer strictly against the response schema and stores it as a
recording, marked with who wrote it and which model it stands in for.
That mark reaches every result: `ask` and `/ask` return it as `provenance`, and every
eval report built from simulated answers says so on its first line.

A simulated result shows that the pipeline, the validator and the scoring work. It does
not measure the target model. [docs/rerecord.md](docs/rerecord.md) gives the full loop,
when recordings go stale, and how to record with a real key.

## Evaluation

The eval questions were written and frozen before the intent code existed: a gold set
for fieldservice and a list of Spider question IDs. Spider is a public text-to-SQL
benchmark; its data is downloaded, never committed. See
[evals/gold/README.md](evals/gold/README.md) and
[ADR-006](docs/adr/ADR-006-benchmark-methodology.md).

`ledgerline eval` scores Ledgerline against a *one-shot baseline*: the same model writes
SQL directly from the schema, and that SQL runs read-only. The baseline's SQL must be a
single SELECT, and the database driver refuses a second statement, so it cannot leave
the read-only transaction. Spider registries come from `registry init` with no edits,
and the eval stops if one no longer matches its committed hash.

Results of the simulated run `sim-1` are in
[evals/reports/sim-1.md](evals/reports/sim-1.md). Every answer in it was written by
claude-haiku-5-5 standing in for `openai/gpt-oss-120b`, so these are simulated numbers,
not a measurement of that model. On fieldservice:

| Simulated, fieldservice | Ledgerline | one-shot |
|---|---|---|
| Execution accuracy (rows match the gold) | 76.7% (33/43) | 69.8% (30/43) |
| Wrong answers among answered | 13.2% (5/38) | 30.2% (13/43) |
| Refusal recall (refused what it should) | 100% (24/24) | 100% (24/24) |

The floor for fieldservice, the minimum v0.1 set out to reach (execution accuracy at
least 80%, wrong answers at most 5%), is **not met in v0.1**. The report lists every
Ledgerline miss with a tag for its cause;
[ADR-001](docs/adr/ADR-001-intent-not-sql.md) explains the result against its
prediction. `./verify.sh` replays the committed fieldservice recordings and checks that
they reproduce `evals/reports/replay-fieldservice.md`.

## Checks

`./verify.sh` is the one gate, locally and in CI. It runs a locked `uv sync`, ruff
(lint and format), pyright (strict on `ledgerline/core` and `ledgerline/workspace`),
detect-secrets against `.secrets.baseline`, pytest with branch coverage, per-module
coverage floors (`scripts/check_coverage.py`) and the replay check above. It then type
checks and builds the pages in `web/` and runs the browser tests (Playwright, against a
fake model). A skipped test fails the run, so a missing database shows up as a failure,
not a pass.

## Decisions

Each design decision has an ADR with a prediction committed before the result. The
index is [docs/adr/README.md](docs/adr/README.md).

## License

Apache-2.0 (see `LICENSE`). Spider is CC BY-SA 4.0 and is not part of this repository.
