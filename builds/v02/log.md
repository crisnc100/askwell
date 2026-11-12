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
