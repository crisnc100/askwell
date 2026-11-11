# ledgerline

Ledgerline answers plain-English questions about a database, and shows the SQL behind
every answer. It is built so that a wrong number is rare and easy to spot.

A model never writes the SQL. It fills in an *intent*: a small, typed form that says which
table, which numbers, which filters and which dates. Plain Python checks every part of the
intent against a *registry*, a file that lists what the database may expose. Only a valid
intent becomes SQL, and that SQL runs read-only; a rejected intent is refused with a
reason. A question the intent cannot express can still get a wrong answer, when the model
fills in a valid intent for a nearby question instead of refusing. [docs/product-brief.md](docs/product-brief.md) explains
who it is for and what it leaves out on purpose.

**Status.** v0.1 runs on your machine, and an invite-only beta answers live questions
(see [Deploy the hosted beta](#deploy-the-hosted-beta)). The default model,
`mistralai/mistral-small-24b-instruct-2501`, was chosen by a measured rule
([ADR-004](docs/adr/ADR-004-model-choice.md)). Ledgerline does not reach its own accuracy
target with it; the results below say so.

## Try it

You need [uv](https://docs.astral.sh/uv/), Docker, `psql` (the PostgreSQL client) and Node
with npm. No API key is needed.

```sh
uv sync
docker compose up -d                  # a demo database, filled with made-up data
(cd web && npm ci && npm run build)   # the web pages
uv run uvicorn ledgerline.api:create_app --factory
```

Open `http://localhost:8000/` and go through the five steps with the sample shop data
linked on the first page:

1. **Prepare.** Read the rules a CSV file must follow, then start a *workspace*: a private
   folder for your files. Bookmark the link it gives you.
2. **Upload** the CSV files.
3. **Check** reads every file. Each problem names the file, row, column and the fix.
   Nothing loads until every file passes.
4. **Confirm** shows exactly what the model will be sent: table and column names, types
   and your descriptions, never your rows. Hide any field you like.
5. **Ask** a question. With a model key you get the rows and the SQL. Without one, the page
   says that live answers need a key.

To see an answer with no key, ask the demo database one of its recorded questions:

```sh
uv run ledgerline ask "How many invoices are still unpaid?"
```

It prints the intent, the check, the SQL and the rows. Recorded questions are ones the
model answers; [Results](#results) has its measured accuracy.

## Results

`http://localhost:8000/results/` shows the benchmark: how often Ledgerline answers, how
often it is right, and how often it refuses, next to a baseline where the same model writes
SQL directly. Each number has a plain definition and a 95% range. On fieldservice, the
made-up business in the demo database, with the default model, live:

| Live, fieldservice | Ledgerline | one-shot |
|---|---|---|
| Rows match the expected answer | 48.8% (21/43) | 46.5% (20/43) |
| Wrong answers among answered | 22.2% (6/27) | 52.4% (22/42) |

Ledgerline gives far fewer wrong answers, mostly by refusing what it cannot check, but it
misses its v0.1 target (at least 80% right, at most 5% wrong). [docs/failures/](docs/failures/README.md) walks through four misses.

## Read more

- [docs/product-brief.md](docs/product-brief.md): the problem, who it is for, what it
  does and does not do.
- [docs/adr/](docs/adr/README.md): each design decision, with a prediction made before
  the code and the measured result.
- [docs/build-log.md](docs/build-log.md): how v0.1 was built, and what reviews caught.
- [evals/reports/select-2026-11-11.md](evals/reports/select-2026-11-11.md): the live
  report for the four models compared, and [sim-1.md](evals/reports/sim-1.md), the
  earlier run with simulated answers.
- The sections below: each part of the system in detail.

## Setup details

The tests run `infra/postgres/roles.sql` with `psql`, and fail without it. CI uses Node 22.
The browser tests need Chromium, installed once from the repository root with
`(cd web && npm ci && npx playwright install chromium)`. `./verify.sh` runs every check
against the seeded database.

Postgres listens on `localhost:56432`. On first start it creates two roles:
`ledgerline_owner`, which owns the data, and `ledgerline_ro`, which can only read. The
defaults in `ledgerline/config.py` match them. To change them, copy `.env.example` to
`.env`.

Model calls default to replay mode, which answers only from recorded responses. A model is
called live only with `--mode record` or `--mode live`, with `LEDGERLINE_LLM_MODE=record`
or `live` in the environment (it sets the mode for `ledgerline ask` and the API when no
`--mode` is given), or by `ledgerline spike`. Each of those needs `OPENROUTER_API_KEY`.

## Your data

[Try it](#try-it) walks through the five pages. More on each:

- **Prepare.** A file needs one table, a header row, an ID column, `YYYY-MM-DD` dates and
  plain numbers. You pick your time zone, and the workspace lives in its own folder under
  `data/workspaces/`. Anyone with the workspace link can see your data.
- **Upload.** A file with the same name replaces the old one.
- **Check.** Up to 20 problems are listed per file.
- **Confirm.** Fields with names that look sensitive (email, phone and similar) start
  hidden.

What stays private:

- **Your rows.** They never go to the model. A column's values (an order's statuses, for
  example) go only if you tick "Share these values with the model" on Confirm, because
  shared values leave your machine.
- **The workspace link.** Its id is a random 128-bit code after the `#`, a part of the
  link browsers never send to a server. The pages send it in a request header instead,
  so it never appears in a URL the server sees or logs. File names travel the same way.
- **Your address.** It is not stored. A keyed hash of it counts your workspaces.
- **Your files.** They expire after 7 days without use and are deleted the next time
  `uv run ledgerline sweep` runs (run it from cron, for example once an hour) or the
  workspace is opened. "Delete my data" removes them at once.

Limits: at most 10 files per workspace, and per file 10 MB, 200 columns, 1,000,000 rows
and 10,000 characters per value. Each address gets 3 workspaces at a time, 20 uploads, 20 checks and
30 questions an hour (questions to `/ask` count too), and at most 2 uploads running at
once. An upload must finish within 2 minutes. The hourly counts live in the
server process and start again when it restarts; the workspace count does not. All
workspaces together share 2 GB of disk. Behind a proxy that sets `X-Forwarded-For`, set `LEDGERLINE_TRUST_PROXY=1` so the limits
see the real address. Leave it off otherwise, or any client could claim any address.

Answers on your own data need a live model, because no answers are recorded for your
files. Set `OPENROUTER_API_KEY` and `LEDGERLINE_LLM_MODE=live` (see
[.env.example](.env.example)). Without them, Ask replies "Live answers need a model key;
see the README." Questions like "last month" use today's date in your workspace's time
zone.

## Asking from the command line and the API

`ledgerline ask` prints the whole trace as JSON: the intent, each attempt and its
validation result, the SQL with its parameters, the columns and rows, or a refusal with its
reason.
`--schema` picks a schema from `config/schemas.yaml` (default `fieldservice`).

The same pipeline is an HTTP API:

```sh
uv run uvicorn ledgerline.api:create_app --factory
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"schema_id": "fieldservice", "question": "How many invoices are still unpaid?"}'
```

`GET /schemas` lists the schemas, and `GET /schemas/{id}/examples` lists the example
questions. They are examples the current model answers; `/results/` has its measured
accuracy. In replay mode only those examples have recorded answers; any other question
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

An answer cut off at the token limit (`LEDGERLINE_MAX_TOKENS`) is still paid for, so it is
charged and counted as unreadable, like any answer that does not parse.

The default and second models (`LEDGERLINE_DEFAULT_MODEL`, `LEDGERLINE_SECOND_MODEL`) were
chosen on the fieldservice benchmark: the cheapest model, by measured cost per question,
that is not clearly worse than the best one and passes three gates (few unreadable
answers, near-perfect refusals, a median answer within 3 seconds).
[ADR-004](docs/adr/ADR-004-model-choice.md) has the rule and the numbers.
`ledgerline spike` is the earlier, smaller check of structured output; its report is in
`evals/spike/`.

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

The eval questions were written and frozen before the intent code existed: for
fieldservice, each question with its expected answer (the *gold*), and for Spider, a list
of question IDs. Spider is a public text-to-SQL
benchmark; its data is downloaded, never committed. See
[evals/gold/README.md](evals/gold/README.md) and
[ADR-006](docs/adr/ADR-006-benchmark-methodology.md).

`ledgerline eval` scores Ledgerline against a *one-shot baseline*: the same model writes
SQL directly from the schema, and that SQL runs read-only. The baseline's SQL must be a
single SELECT, and the database driver refuses a second statement, so it cannot leave
the read-only transaction. Spider registries come from `registry init` with no edits,
and the eval stops if one no longer matches its committed hash.

The live run `select-2026-11-11` compared four models on fieldservice; its report is
[evals/reports/select-2026-11-11.md](evals/reports/select-2026-11-11.md), and the default
model's numbers are in [Results](#results). Before a key existed, the simulated run
`sim-1` ([evals/reports/sim-1.md](evals/reports/sim-1.md)) checked the pipeline and the
scoring. Every answer in it was written by claude-haiku-5-5 standing in for
`openai/gpt-oss-120b`, so those are simulated numbers, not a measurement of that model.
On fieldservice:

| Simulated, fieldservice | Ledgerline | one-shot |
|---|---|---|
| Execution accuracy (rows match the gold) | 76.7% (33/43) | 69.8% (30/43) |
| Wrong answers among answered | 13.2% (5/38) | 30.2% (13/43) |
| Refusal recall (refused what it should) | 100% (24/24) | 100% (24/24) |

The floor for fieldservice, the minimum v0.1 set out to reach (execution accuracy at
least 80%, wrong answers at most 5%), is **not met in v0.1**, simulated or live. The report lists every
Ledgerline miss with a tag for its cause;
[ADR-001](docs/adr/ADR-001-intent-not-sql.md) explains the result against its
prediction. `./verify.sh` replays the committed fieldservice recordings and checks that
they reproduce `evals/reports/replay-fieldservice.md`.

The Results page (`/results/`) draws every report in `evals/reports/` from its JSON file.
`evals/report.schema.json` is the shape of that file. It is generated from
`ledgerline/bench/report_schema.py` (`uv run python -m ledgerline.bench.report_schema
--write`), and a test checks every committed report against it. The page links each
schema's triage file, `evals/triage/<schema>.yaml`, which gives every miss its cause.

## Deploy the hosted beta

The hosted beta is one container on one host, behind [Caddy](https://caddyserver.com),
a web server that handles HTTPS. It answers live questions with a beta-only OpenRouter
key. Three controls keep it small and cheap:

- **Invite gate.** Every page and API route needs an invite code, except `/healthz`.
  A visitor enters the code once; the browser keeps it in a cookie scripts cannot read.
  Scripts can send it in the `X-Invite-Code` header instead.
- **Daily cap.** All live answers together may spend at most a set amount per UTC day.
  Each model call reserves its worst-case cost before it is sent, so the cap holds even
  when requests overlap. The day's total is kept on disk, so a restart does not reset it.
- **Kill switch.** One setting turns live answers off. Asks then get "Live answers are
  turned off right now." instead of an answer.

The image (`Dockerfile`) builds the pages, installs the app and builds the fieldservice
demo as a read-only SQLite file, so the beta needs no Postgres. It runs as an
unprivileged user, and everything it writes lives in one volume, `/data`: uploaded
workspaces, the audit log (`app.sqlite`) and the day's spend (`spend.sqlite`).

On the host:

1. Copy `.env.beta.example` to `.env.beta` and fill it in:

   | Setting | What it does |
   |---|---|
   | `OPENROUTER_API_KEY` | The beta's own key. Give it a credit limit on OpenRouter too. |
   | `LEDGERLINE_INVITE_CODES` | The invite codes, comma-separated. With none set there is no gate, so never leave it empty on a public host. |
   | `LEDGERLINE_DAILY_SPEND_CAP_USD` | The most live answers may cost per UTC day, for example `1.00`. |
   | `LEDGERLINE_LIVE_ANSWERS_OFF` | `1` turns live answers off. Restart the app after changing it. |

   `compose.prod.yaml` also sets `LEDGERLINE_TRUST_PROXY=1`, because Caddy is the only
   client and it writes `X-Forwarded-For`. The image sets the database and data paths.
2. Start it: `docker compose -f compose.prod.yaml up -d --build`. It starts two
   services: `app`, on `127.0.0.1:8000` so only the host can reach it, and `sweep`,
   which deletes expired workspaces once an hour.
3. Point Caddy at it. Caddy gets the HTTPS certificate on its own:

   ```
   ledgerline.example.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```

4. Check it: `curl https://ledgerline.example.com/healthz` returns
   `{"status": "ok", "mode": "live"}`. It answers 503 if the demo database cannot be read.

To turn live answers off in a hurry, set `LEDGERLINE_LIVE_ANSWERS_OFF=1` in `.env.beta`
and run `docker compose -f compose.prod.yaml up -d`. To back up or move the beta, copy
the `ledgerline-data` volume.

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
