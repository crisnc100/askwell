# Ledgerline v0.2 build log

Deliberate choices made while building, and why. Newest at the bottom of each phase.

## Phase 0 item 3: ADR-007
- **ADR-007** (`1cbf394`) holds the plan's ten predictions and a Result of "not measured
  yet". It was committed after the held-out hash (`f2e6191`) and before any commit that
  touches `ledgerline/core/` (G1).
- **ADR count test** (`522768c`, tests only). `test_every_adr_has_a_result_and_none_is_left_pending`
  asserted exactly 6 ADRs. It now asserts at least 6 and that the ADR files equal the
  ADRs linked from `docs/adr/README.md`. A missing ADR still fails, through the index.

## Phase 1: placeholder reasons, conditional and ratio metrics
- **placeholder_reason** (`40a1377`). Blank, `none`, `null`, `n/a`, `na`, `-`, `unknown`
  and `no reason` (any case, trimmed) are placeholders. On `unanswerable` the validator
  rejects them and asks what is missing. On other intents it rejects them with the
  message "leave unanswerable_reason out unless the intent is unanswerable". A missing
  reason on `unanswerable`, and a real reason on another intent, keep `intent_shape`.
- **Conditional metric** (`ef8eaed`). Conditions go through the same `check_condition`
  as filters, so every filter rule applies. Compiled as `agg(CASE WHEN … THEN x END)`.
  A conditional count with no field counts `CASE WHEN … THEN 1 END`.
- **Joins used only by a metric's `where` are outer joins.** An inner join would drop
  rows from every other metric: the share of work orders done by senior technicians
  would lose the unassigned ones from its total. Tested, and covered by oracle case v08.
- **Ratio metric** (`ef8eaed`). Its parts are labels (an alias, or a default label) of
  other non-ratio metrics, checked after every metric is labelled, so a ratio may name a
  metric listed after it. A ratio's default label is `ratio`. `ratio_shape` covers both
  directions: a ratio with `field`, `distinct` or `where`, and a non-ratio with
  `numerator`, `denominator` or `as_percent`.
- **Ratio SQL:** `CAST(numerator AS FLOAT) [* 100] / NULLIF(denominator, 0)`. The cast
  stops Postgres dividing two counts as integers. `100`, `0` and the conditional count's
  `1` are rendered as SQL text, not bound, so the sentinel property can still require
  that every bound parameter is a user value.
- **Oracle:** 8 new cases in `tests/core/oracle_cases_v02.py`, run on both engines from
  `tests/core/test_grammar_v02.py`. The 30 v0.1 cases and their count test are unchanged.
- **Sentinel property:** a new property generates conditional metrics (and a ratio over
  them) with random `where` values plus filters, and requires every value bound and
  nothing else bound, on both dialects.
- **Replay keys.** The Intent JSON schema is part of every replay key, so adding
  `Metric.where` changed them all. From `ef8eaed` until the Phase 3 re-record, the 11
  tests in `tests/pipeline/test_api_replay.py` and the replay report step miss their
  recordings. Everything else in `verify.sh` is green: ruff, pyright, the other 941
  tests, the coverage floors (validate.py 100%, sqlbuild.py 97.3% branch) and the 12
  Playwright tests. The orchestrator has been told.

## Phase 2: the date_series intent
- **Shape** (`f3f69b3`). `date_series` takes `entity`, `grain`, shared `filters`, an
  optional `date_range` and 1 to 4 `series`. It takes no `metrics`, `select`,
  `group_by`, `having`, `order_by` or `limit` (`series_shape`): it is always ordered by
  period and not capped by a limit. The plan left `order_by` and `limit` open; rejecting
  them keeps one way to write a series.
- **The period has no field.** `DateRange.field` became optional. A `date_series` must
  leave it out (`series_shape`), and every other intent must give it
  (`invalid_date_range`, "date_range needs a field"). Reusing `date_range` keeps the
  relative tokens and the start and end rules in one place.
- **A series' metric is plain:** no ratio, and no `where` or `alias` on the metric
  itself; those go on the series (`series_shape`). A series needs an alias. Aliases
  reuse `invalid_alias`, `duplicate_alias` and `alias_collision` (for `period`).
- **`series_date_field`** fires when a series' date field is not a date or datetime.
  Reaching it across a one-to-many edge is `fan_out`, checked per series by the existing
  resolver.
- **Period refactor.** `check_date_range` was split into the field checks, the period
  resolution and the predicates, so series reuse them. Its order of checks is unchanged.
- **SQL.** One grouped CTE per series, `(period, value)`. The plan said subqueries; CTEs
  are used because each series is read twice (for the union of periods and for its
  values), and a subquery would be written out, and run, twice. Each series builds its
  own table aliases and inner-joins only what it uses.
- **Rows with no date are left out of that series** (`date IS NOT NULL`). A NULL period
  would otherwise appear as a row that no series can join to.
- **Shared filter values are bound once per series**, since each CTE applies them. The
  series sentinel property counts them that way.
- **Oracle:** 4 cases (v09 to v12): two counts on two dates, a count and a sum, weeks
  where one series is empty, and a series across a join. The references use
  `FULL OUTER JOIN` or a correlated count on Postgres, independent of the builder.
- **State of verify.sh:** the same 11 replay API tests and the replay report step miss
  their recordings (see Phase 1). Everything else passes: 987 tests, coverage
  (validate.py 99.7%, sqlbuild.py 97.0% branch) and 12 Playwright tests.

## Phase 3: prompt, eval option, Ask page and trace (before the re-record)
- **No-tuning test** (`10bd601`, G7). It reads every `evals/gold/*.jsonl`, so the
  held-out file is checked as soon as it lands in Phase 4. It checks `prompt.py` and every
  registry's descriptions, entity and field aliases and value aliases. Words are
  lowercased with punctuation dropped. A planted run shows the checker finds one. It
  caught a 6-word run in a first draft of one example question, which was reworded.
- **interpret-v2** (`d983cb7`). It describes a metric's `where`, the ratio metric and
  `date_series`. It says a reason must name what is missing and must be left out of
  answerable intents, and it adds the refuse-first rule with the four things still out of
  reach. Three worked examples use a made-up tickets schema (`tickets`, `agents`,
  `opened_on`, `closed_on`, `stage`, `minutes`). A test validates each one against a
  made-up registry with the real validator, and checks that no example names a
  fieldservice entity or field.
- **`eval --gold <file>`** (`d4fc91c`). The items of that file replace the schema's
  default gold. Every record, metrics row, miss and baseline win carries its gold file's
  name, and the report header lists the gold files. The Markdown table gains a Gold
  column, added last so existing column checks still hold. Reports and checkpoints from
  before carry no gold name and are read as the default (`fieldservice.jsonl`, or
  `spider_ids.json`). Only a second gold file adds `|gold=<name>` to the checkpoint key.
  `--gold` takes exactly one schema and is refused for Spider. This commit touches only
  the eval code and applies cleanly to `fc97462`, so it can be the `v02-before` commit.
  Its Gold column changes the Markdown, so `v02-before`'s own replay report check needs
  a `--write` there.
- **Ask page** (`93d239d`, G9). Each of the five new codes has a plain-English message
  and suggestion, and a test keeps them off the general fallback. The trace gains "How
  the numbers are built": each ratio's formula and each series' metric and date field.
  It is read defensively, because the intent is model output.
- **Browser test** (`web/e2e/grammar.spec.ts`). It asks a ratio question and a two-date
  series question on the sample workspace through the fake model, and checks the
  answers, the columns and the trace lines. The real validator and builder run on
  SQLite. A replay-mode browser test on the demo needs canned ratio and series questions,
  which need recording first (see the callback).
- **`/ask`** returns the new intent fields as the model gave them (test in
  `tests/pipeline/test_api_double.py`).
- **State of verify.sh:** the same 11 replay API tests and the replay report step miss
  their recordings. Everything else passes: 1,004 tests, the coverage floors and 13
  Playwright tests.

## Core review fix round (reviews 777016 and 19f26a)
- **Ratio parts must be numeric** (`bfc9638`). The min or max of a date or datetime as a
  numerator or denominator is now `ratio_ref`. Dividing it errored on Postgres and gave
  a meaningless number on SQLite.
- **`distinct` on a count with no field is rejected** (`value_shape`). Rejecting it was
  simpler than compiling it: a conditional form compiled to
  `count(DISTINCT CASE … THEN 1)`, which is only ever 0 or 1, and the plain form used to
  ignore the flag silently.
- **Explicit NULLS LAST on every ORDER BY item, both directions.** Postgres puts NULLs
  first when sorting descending and SQLite puts them last. The bundled SQLite is 3.50.4
  (NULLS LAST needs 3.30). This also changes v0.1 intents that sort descending on a
  column with NULLs on Postgres: the NULLs now come last there too. Oracle case v13 and
  a test in each direction on both engines cover it.

## Phase 3: canned questions and the re-record
- **Two canned demo questions** (`4f81c28`): "What percentage of work orders were
  cancelled?" and "Per month this year, show work orders opened next to work orders
  completed." The first wording of the series question shared six 6-word runs with a
  seen question, found with the no-tuning checker before anything was committed, and was
  replaced. The replay API tests cover both (`b3b284c`, tests only).
- **Demo re-recorded live** (`anthropic:claude-haiku-5-5`, record mode, each ask capped at
  $0.005): 10 questions, 11 calls (one retry), $0.0046. Every canned question answers or
  refuses as its test expects. The ratio question answers with a ratio metric, and the
  series question with a `date_series` on `opened_at` and `completed_at`.
- **Replay report re-recorded live** (budget $0.15): 68 ledgerline calls ($0.0314) and 67
  oneshot calls ($0.0274), $0.0588 in all. The estimate assumed oneshot would replay, but
  record mode calls the provider for every request. `scripts.check_replay_report --write`
  then reproduced the record run's results exactly from the recordings.
- **Total live spend in PR-G so far: $0.0634** of the $3 cap ($0.20 approved for this step).
- **This is a live seen-set result.** The re-recorded replay report scores ledgerline 38/43
  correct and 0 wrong among 38 answered (1 trial). `prompt.py` and `ledgerline/core/`
  have not changed since it was recorded.
- **Browser coverage in replay mode.** The web app has no demo Ask page: the only Ask page
  is the workspace's, which takes uploaded data. The two canned questions are therefore
  covered in replay mode by the API tests (real recordings through the real pipeline),
  and in the browser by `web/e2e/grammar.spec.ts` (fake model, real validator and builder).
- **State of verify.sh:** green. 1,031 tests, coverage (validate.py 99.7%, sqlbuild.py
  97.0% branch), the replay report reproduces, and 13 Playwright tests pass.
