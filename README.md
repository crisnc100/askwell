# ledgerline

Ledgerline is a governed AI data analyst. A person asks a business question in plain
English. A model turns it into an *intent*: a small, typed description of a query (which
table, which numbers, which filters). Plain Python checks every part of the intent
against a *registry*, a YAML file that says what a database may expose. Only a valid
intent becomes SQL, and that SQL runs read-only.

The model never writes SQL, so it cannot invent a column or slip a value into the query
text. The cost is coverage: a question the intent cannot express is refused.
[ADR-001](docs/adr/ADR-001-intent-not-sql.md) explains the choice.

**Status.** This version holds the foundations and the correctness core: the registry,
the intent, the validator, the SQL builder and the read-only executor, plus the model
gateway and the frozen eval set. The step that asks a model for an intent is not built
yet. Today you write an intent by hand and compile it to SQL (see below).

## Quick start

You need [uv](https://docs.astral.sh/uv/), Docker and `psql` (the PostgreSQL client).
The tests run `infra/postgres/roles.sql` with `psql`, and fail without it.

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
recorded responses. Only `ledgerline spike` calls a model live.

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
notes and addresses are skipped). The output is always `draft: true`, and the same
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
one row to `ask_log` for every run, including one that could not connect. The row holds
the question and the intent as given, the validation outcome, the SQL with placeholders,
a SHA-256 of the bound parameters, the row count, the cost, the model and the outcome.
The question and intent can contain the values a person typed, such as a customer name
in a filter, so those values do reach the log. The row never holds the result rows or
the separate list of bound parameters. `ask_log` lives in a separate app database that
the read-only role cannot connect to.

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
LangChain. It has three modes: `record`, `replay` and `live`. In replay mode a missing
recording is an error; it never falls back to a live call. Before each live call, a
budget guard checks the call's worst-case cost against what is left of the run's
budget, and stops the run when it would go over. A long run saves each finished item,
so a stopped run can resume and its spend still counts.
[ADR-005](docs/adr/ADR-005-replay-and-budget.md) has the details.

`ledgerline spike` checks which candidate models return valid structured output. It
has not run yet, so no model is chosen; see
[ADR-004](docs/adr/ADR-004-model-choice.md).

## Evaluation

The eval questions were written and frozen before the intent code existed: a gold set
for fieldservice and a list of Spider question IDs. Spider is a public text-to-SQL
benchmark; its data is downloaded, never committed. See
[evals/gold/README.md](evals/gold/README.md) and
[ADR-006](docs/adr/ADR-006-benchmark-methodology.md).

## Checks

`./verify.sh` is the one gate, locally and in CI. It runs a locked `uv sync`, ruff
(lint and format), pyright (strict on `ledgerline/core`), detect-secrets against
`.secrets.baseline`, pytest with branch coverage, and per-module coverage floors
(`scripts/check_coverage.py`). A skipped test fails the run, so a missing database
shows up as a failure, not a pass.

## Decisions

Each design decision has an ADR with a prediction committed before the result. The
index is [docs/adr/README.md](docs/adr/README.md).

## License

Apache-2.0 (see `LICENSE`). Spider is CC BY-SA 4.0 and is not part of this repository.
