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
