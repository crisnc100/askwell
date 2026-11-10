# Ledgerline v0.1 — plan (rev 2, after Fable 5.2 Bounce)

**Outcome:** A Python service and CLI where a natural-language question about a registered schema becomes a validated structured intent, and then a parameterized SQL query run on a read-only connection. A pre-registered eval reports coverage, accuracy, false-refusal rate and wrong-answer rate per schema. It covers 6 schemas (the synthetic fieldservice schema plus 5 Spider databases) and compares against two baselines: a one-shot LLM that writes SQL, and LangChain's SQL agent. Everything except live evals runs with no API key.

**PRs:** three PRs, stacked, each merged with a merge commit.
- **PR1:** P1 + P2, foundations and the correctness core. Main works on its own: a CLI that loads a registry and validates and compiles intents. No LLM is involved.
- **PR2:** P3 + P4, the pipeline and the eval. It needs PR1's core.
- **PR3:** P5, the UI and docs.

The security-relevant core is reviewed apart from routine work.

## Stack (fixed)
- **Core:** Python 3.12 (uv), FastAPI, uvicorn, Pydantic v2, pydantic-settings, PyYAML, SQLAlchemy 2 Core, psycopg, sqlite3.
- **LLM:** LangGraph and langchain-openai (OpenRouter). langchain-community for the SQL agent baseline.
- **CLI and dev:** Typer, httpx, Faker.
- **Tests and checks:** pytest, pytest-asyncio, pytest-cov, hypothesis, ruff, pyright (strict on `ledgerline/core/`), detect-secrets.
- **Web:** Vite + TypeScript, a static build served by FastAPI. Playwright for one smoke test.
- **Infra:** Docker Compose (Postgres 16, api).
- New dependencies outside this list need a callback.

## Definitions (fixed before any code)
- **Reference time:** the config value `LEDGERLINE_NOW` (default `2026-06-30T00:00:00Z`). It's used by the seeder, by the prompt's reference date, and by relative-date resolution. Gold results are computed against it.
- **Gold categories:**
  - `in_schema` is answerable from registry-visible data, and its `gold_sql` must execute and return a non-empty, deterministic result.
  - `out_of_schema` asks for data that does not exist in the DB, such as competitor prices. The gold answer is a refusal.
  - `should_refuse` asks for something that exists but is deliberately excluded or unsafe: a hidden field, a write, a request to delete. The gold answer is a refusal.
  - Each item carries `difficulty` (easy|medium|hard) and `features` (join, group, having, date, distinct, order_limit).
- **Metrics, per schema × system × model:**
  - coverage: share of in_schema items the system attempts
  - execution accuracy on in_schema
  - accuracy given attempted
  - false-refusal rate on in_schema
  - wrong-answer rate given answered, which is the governance metric
  - refusal recall on refusal items
  - execution-error rate
  - mean cost and p50 latency
  - Wilson 95% intervals on every rate
- **Result comparison:**
  - project to the gold column count
  - compare rows as multisets, or as sequences when the gold has ORDER BY
  - cast Decimal to float with tolerance 1e-6
  - NULL is never equal to 0
  - normalize SQLite date strings to ISO
  - compare gold under the same row cap
  - extra columns count as a mismatch unless the gold columns are a subset by value
- **Baselines:**
  - **oneshot:** schema DDL plus the registry descriptions go into the prompt, and the LLM returns SQL that is executed read-only.
  - **sql_agent:** LangChain's SQL agent with the same descriptions in its prompt. It is scored on the rows of its last successful `sql_db_query` call. A refusal is "no query executed" or a final answer matching a fixed refusal pattern list.

  All three systems run at temperature 0. Fieldservice runs 3 trials and reports the mean. Spider runs one trial.

## Phases

### P1 — Foundations, gold, pre-registration (PR1)
1. Scaffold:
   - uv project, Typer CLI, ruff and pyright config, pytest config with **zero skips allowed** (verify fails on any skip)
   - `verify.sh` and a GitHub Actions workflow running it (Postgres service), `.env.example`, Apache-2.0
2. **Compose:** Postgres with roles `ledgerline_owner` and `ledgerline_ro` (SELECT only). One seed path, `uv run ledgerline seed`, which compose calls.
   - **Fieldservice schema:** customers, sites, technicians, work_orders, parts, work_order_parts, invoices, plus a `users` table with `password_hash` and `email` to exercise hidden fields.
   - Faker with a fixed seed, about 5k work orders over 24 months ending at `LEDGERLINE_NOW`.
3. **Model gateway** (`ledgerline/llm/`):
   - An OpenRouter `ChatOpenAI` with structured output (json_schema), pinned to providers that support it, with a Pydantic parse fallback. Unparseable output is a typed `ParseError`.
   - **Replay:** a JSONL store keyed by hash(model, prompt_version, messages, schema), with `record|replay|live` modes. A miss raises.
   - **Agent trajectory replay** is keyed by (system, question_id, model, prompt_version), not by message hash.
   - **Cost:** taken from OpenRouter's usage cost, or estimated from the models-endpoint pricing.
   - **Budget guard:** a worst-case pre-check (max_tokens × price) before each call, a hard stop at `--budget`, 429 backoff, and a checkpointed results JSONL so runs resume and produce a partial report.
   - **Backstop:** `.env.example` tells Cristian to set a credit limit on the OpenRouter key.
4. **Model spike** (live, budget $0.50): pick a default cheap model and a second model that honour json_schema on OpenRouter. Record the choice in ADR-004.
5. **Gold set** `evals/gold/fieldservice.jsonl`:
   - ≥60 items: ≥35 in_schema with a difficulty mix of ≥10 hard, ≥12 out_of_schema, ≥10 should_refuse.
   - A test asserts every in_schema `gold_sql` executes and returns a non-empty, deterministic result (run twice, compared).
6. **Spider pre-registration:**
   - `scripts/fetch_benchmarks.py` downloads Spider dev with a pinned checksum and licence notice into gitignored `data/`.
   - `evals/gold/spider_selection.py` uses a fixed seed and stratifies by Spider hardness across 5 databases picked by seed. It commits only **question IDs** (`spider_ids.json`), never question text.
7. **Gold manifest:** `evals/gold/MANIFEST.json` holds the gold file hashes, and a test checks them. Changing gold after P1 requires `evals/gold/CHANGELOG.md` with a reason.
8. **ADR skeletons with predictions:** intent-not-SQL, LangGraph boundary, fan-out rule, replay and budget, benchmark methodology. Predictions only, committed now.

**Exit:** `./verify.sh` is green. The gold-executes test, budget-guard tests (pre-check, abort, resume), replay-miss test and manifest test all pass. The spike is recorded.

### P2 — Registry, validator, SQL builder, executor (PR1, plain Python, `ledgerline/core/`)
1. **Registry model** (`schema_version: 1`, `draft: bool`):
   - **entities** are DB tables or DB views only. There is no SQL in the YAML.
   - **fields:** name, real identifier, type, description, aliases, filterable, aggregatable, hidden, categorical.
   - **relationships**, each with a cardinality (many_to_one) and a `source: declared|inferred`.
   - **allowed_values** for categorical fields only.

   Registry-safe slugs map to real identifiers, so spaces, dots and case are handled.
2. **`ledgerline registry init <db-url> -o file.yaml [--values]`:**
   - **Introspection:** uses the SQLAlchemy inspector. Infers relationships from `<x>_id` → a primary key when no foreign key is declared, marked `inferred`.
   - **Auto-hide:** hides fields matching `password|hash|token|secret|ssn|email|phone`.
   - **Categoricals:** a field is categorical when it has ≤50 distinct values, isn't hidden and isn't name-like.
   - Marks the file `draft: true`, and warns if the role has write privileges.
   - Running it twice on the same DB gives byte-identical output.
3. **Intent model:**
   - **intent_type:** summary | grouped_summary | row_list | unanswerable.
   - **entity** (the base).
   - **select** (for row_list).
   - **metrics:** count | count_distinct | sum | avg | min | max, with distinct.
   - **filters:** eq | neq | gt | gte | lt | lte | between | in | is_null | ilike_contains, grouped as any_of / all_of, one level deep.
   - **having** (on metrics).
   - **group_by:** fields plus calendar grain day | iso_week | month | quarter | year.
   - **date_range:** relative tokens (last_n_days, last_month, last_quarter, ytd, …) or absolute, applied to one named date field.
   - **order_by**, **limit**, **unanswerable_reason**.

   Code resolves relative dates against `LEDGERLINE_NOW`, never the LLM.
4. **Validator**, with typed errors for:
   - unknown entity or field
   - a hidden field
   - a field that is not filterable or not aggregatable
   - aggregate vs type, operator vs type, value type vs field type
   - a value not in allowed_values (case-insensitive, alias-resolved) for categoricals
   - limit ≤0 or above the cap
   - an empty `in`
   - a reversed `between`
   - date_range on a non-date field, or a date_range that duplicates a filter on the same field
   - intent_type vs populated fields (summary needs metrics, row_list needs select)
   - having without a group_by
   - an unreachable field (no declared or inferred path, more than 2 hops)
   - **an ambiguous path** (more than one shortest path)
   - **fan_out:** a join from the base entity along a one-to-many edge while any metric is aggregated
   - a draft registry without `allow_draft`
5. **SQL builder:** SQLAlchemy Core only. Identifiers come from the registry. Values are bound parameters. Joins run along many-to-one edges only. Calendar grains compile per dialect (`date_trunc` on Postgres, `strftime` on SQLite, ISO week on both).
6. **Executor:**
   - On every connection, Postgres runs `BEGIN READ ONLY` with `statement_timeout`. SQLite opens `mode=ro` with a progress-handler interrupt as its timeout.
   - Row cap.
   - Writes go to an audit table `ask_log` in the app DB (trace id, question, intent, validation, sql, params hash, row count, cost, model). Data rows are never logged.

**Exit:**
- one named test per validator rule (each listed one)
- a Hypothesis property using sentinel values: every filter value appears in params and never in the SQL text
- injection fixtures leave the DB unchanged
- a **differential oracle**: 30 hand-written intents, each with expected rows on the fieldservice fixture DB, on both engines
- cross-dialect grain tests
- write attempts fail on both engines, and the timeout fires on both
- `registry init` is deterministic and auto-hides fields
- **branch** coverage ≥95% per module on `validate.py` and `sqlbuild.py`, and ≥85% on `executor.py` and `registry_init.py`, checked per module by `scripts/check_coverage.py`

### P3 — Pipeline, API, CLI (PR2)
1. **LangGraph graph:** interpret → validate → (one retry with the typed errors) → execute → present.
   - **present is deterministic** (columns, rows, a formatted SQL string). There is no LLM call, and no rows are sent to OpenRouter.
   - **Interpret prompt:** a compact registry view in a fixed order. When it's over budget, truncation is deterministic: allowed values drop beyond 20 per field, then descriptions shorten. The truncation is logged.
   - Hidden fields are never in the prompt.
   - `unanswerable`, or a second validation failure, gives a refusal with a reason and `sql: null`.
2. **`config/schemas.yaml`:** schema_id → registry path + DB URL env var.
3. **FastAPI** `POST /ask` returns `{intent, validation, sql, params, rows, columns, refusal, trace_id, cost_usd}`. Also `GET /schemas`, `GET /schemas/{id}/examples` (canned questions available in replay), `GET /healthz`.
4. **CLI:** `ledgerline ask`.

**Exit:** replay API tests cover answerable, out-of-registry refusal, hidden-field refusal, retry-then-success, and **init → ask on a Spider DB**. The `ask_log` row is written.

### P4 — Eval and benchmark (PR2)
1. **`ledgerline eval --schema <id>|--all --systems ledgerline,oneshot,sql_agent --mode replay|record|live --models a,b --trials N --budget N`**
   - Writes `evals/reports/<date>.md` and `.json`: the metrics table with intervals, plus a **miss triage** for every Ledgerline miss, tagged `grammar_gap | misread | validator_false_reject | builder_bug | gold_issue`.
   - Lists questions where a baseline beat Ledgerline, cited by ID only for Spider.
2. **Spider registries:** generated by `registry init` at eval time with no edits. The report records each registry's hash, and the eval aborts if a committed registry differs from regenerated output. Spider runs use `allow_draft`, labelled in the report.
3. **Replay:** recordings for fieldservice, all 3 systems, the default model and 1 trial are committed. CI checks that the replay eval reproduces the committed replay report. `docs/rerecord.md` documents when and how to re-record and what it costs.
4. **Live run** (orchestrator, with Cristian's key, total ≤$5):
   - fieldservice × 3 systems × 2 models × 3 trials
   - Spider 5 DBs × 50 questions × 3 systems × 1 model

**Exit:** the live report is committed.

**Floors:**
- On fieldservice in_schema with the default model, Ledgerline's execution accuracy is ≥80% and its wrong-answer rate given answered is ≤5%.
- On Spider, no accuracy floor. Coverage and accuracy-given-attempted are reported, and every miss is triaged.

### P5 — UI and docs (PR3)
1. **Vite + TypeScript static page**, served by FastAPI at `/`:
   - pick a schema
   - canned example questions, plus free text (live mode only)
   - trace panels: question → intent JSON → validator verdict (errors highlighted) → SQL + params → result table, or the refusal reason
2. **Docs:**
   - README: problem, mermaid diagram, quickstart, the live eval table with intervals, limits
   - `docs/product-brief.md`
   - ADRs from P1, now closed with measured results
   - `docs/build-log.md` (a dated engineering journal, kept on purpose for interviews)
   - `docs/failures/` with 3 or more triaged misses from the live report
3. **Dockerfile** for api, which includes the static web build.

**Exit:** the Playwright smoke test passes in replay mode. `docker compose up` serves `/` and `/ask`.

## Acceptance criteria
- **L1** `./verify.sh` passes locally: ruff, pyright (strict on core), pytest with zero skips, per-module coverage, the replay eval reproducing the committed report, detect-secrets, and `docker compose build`. The GitHub Actions workflow runs the same `verify.sh`. *CI-green is checked after the first push, which needs Cristian's `gh auth login`.*
- **L2** Per-module branch coverage: ≥95% on `validate.py` and `sqlbuild.py`, ≥85% on `executor.py` and `registry_init.py`.
- **L3** A named passing test exists for every validator rule in P2.4, including fan_out and ambiguous_path.
- **L4** The sentinel-value Hypothesis property passes, the injection fixtures leave the DB unchanged, and the 30-intent differential oracle passes on Postgres and SQLite.
- **L5** Writes fail and timeouts fire on both engines. The row cap is enforced.
- **L6** `registry init` is deterministic, auto-hides sensitive fields and infers relationships, and its output loads, on fieldservice and **every** sampled Spider DB.
- **L7** The replay API tests in P3 pass, including init → ask on a Spider DB, and `ask_log` is written.
- **L8** The gold set meets the P1.5 counts, every in_schema gold executes non-empty and deterministic, and the manifest matches. The gold, Spider IDs and ADR predictions are committed before `intent.py` first appears (`git log`).
- **L9** The replay eval reproduces the committed replay report. `docs/rerecord.md` exists.
- **L10** A committed live report covers fieldservice and 5 Spider DBs × 3 systems, with intervals, miss triage and baseline wins. Total spend is ≤$5, shown in the run log.
- **L11** Fieldservice floors (default model): execution accuracy ≥80% on in_schema, and wrong-answer rate given answered ≤5%.
- **L12** No Spider question text or data is committed; there is a fetch script with checksum and licence. The registry-hash check is enforced.
- **L13** The Playwright smoke test passes in replay mode.
- **L14** Every ADR has a prediction committed before its result, plus the measured result. The README carries the live table.
- **L15** No secrets are committed (detect-secrets baseline), and `.env.example` documents the OpenRouter credit limit.

## Decision 2026-11-09 (Cristian): no OpenRouter key for now; simulate model behaviour
- **The gateway gains an export/import path.**
  - `--mode export` writes each pending model request to `evals/pending/<key>.json`: system prompt, messages, response schema, target model id.
  - The orchestrator has a Claude subagent answer each request as the product model would, using the product's system prompt and returning exactly the response schema.
  - `--mode import` loads those answers into the replay store with provenance `{"simulated_by": "<claude model id>", "standing_in_for": "<target model id>"}`.
- **What changes in the plan:**
  - **"Live" model spikes:** replaced by a simulated schema-compliance check. The real-model spike is deferred until a key exists, and ADR-004 records that.
  - **"Live" eval runs:** become simulated runs, and every simulated report is labelled at the top: "Model responses simulated by <claude model>, standing in for <target>; not an OpenRouter measurement."
  - **Budget caps and live mode:** stay in the code for when a key is added.
- **Floors** apply to the simulated run, and are re-measured on a real model when a key is added.
