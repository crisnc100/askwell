# Ledgerline v0.2 — plan

**Outcome:** two pieces of work, approved by Cristian on 2026-11-12.
1. **Grammar v0.2.** The intent can express a ratio of two counts or sums, and two counts on
   different date fields in one series. The validator rejects placeholder refusal reasons.
   The change is then measured live on Claude Haiku 5.5, on questions it was built from and
   on questions nobody building it has seen.
2. **Value calculator.** A page where a reader sets their own business numbers and sees
   what Ledgerline would cost to run and what it could be worth. The running cost is
   Ledgerline's measured model cost per question.

**Why now:** the v0.1 live run on Haiku 5.5 (`select-haiku-2026-11-11`) scored 35/43 correct
and 2 wrong among 37 answered: 5.4% wrong, against a limit of 5% (L11, published as not
met). Both wrong answers were questions the grammar could not express: fs-028 (a
percentage) and fs-035 (two dates in one monthly table). In each, the model answered a
nearby question instead of refusing.

**PRs:** two PRs, built in parallel in separate worktrees.
- **PR-G, grammar v0.2.** Grammar, validator, prompt, the live re-measure and its docs.
  These ship together: changing the prompt changes every recording key, so main only stays
  working if the new recordings, reports and demo answers land with the code.
- **PR-V, value calculator.** A new static page and its tests. It reads a committed report
  and changes no Python.

Each stands alone and leaves main working. Neither needs the other's code. The only link
is which report the calculator reads its cost from (see "The cost source" below).

## Decisions (Cristian, 2026-11-12)
- **D1:** a new 40-question held-out set, written blind and committed hash-first, carries
  v0.2's main claim.
- **D2:** the held-out result is the headline for the 5% wrong-answer limit. Results on
  the seen set are reported and always labelled "seen".
- **D3:** a placeholder reason on an answerable intent is still rejected, with its own code,
  `placeholder_reason`.
- **D4:** the calculator prices model calls at list price, and says that API credits are
  not counted.
- **D5:** Spider runs before and after the change.

## Stack (unchanged)
Python 3.12 (uv), FastAPI, Pydantic v2, SQLAlchemy 2 Core, the existing gateway; Vite +
TypeScript and Playwright for the web. No new dependencies. The calculator's formula tests
run in Playwright's own test runner, which runs plain TypeScript tests without a browser,
so no unit test library is added.

## Definitions
- **Seen questions:** the 67 fieldservice gold questions (`evals/gold/fieldservice.jsonl`).
  They are frozen, but they are not held out. Every miss on them has been read and triaged,
  fs-028 and fs-035 have public failure pages, and this grammar change was designed from
  those two. A result on seen questions shows the change works where it was aimed. It
  does not show the change works in general.
- **Held-out questions:** a new set, `evals/gold/fieldservice-holdout.jsonl`, written for
  v0.2 before any grammar code, by an agent that sees neither the grammar design nor the
  seen questions. Its SHA-256 is committed first; the file itself stays outside the
  builder's worktree until the code is finished. It carries v0.2's main claim.
- **Spider questions:** the 250 pre-registered Spider IDs (5 databases × 50). They were
  chosen by seed before any code, but sim-1's triage read them, so they count as seen.
  They serve here as a check that the change does not make other schemas worse.
- **The split today:** v0.1 has no held-out set. Its gold was frozen before the intent
  existed, which kept v0.1 honest, but after triage and the failure pages it is all seen.
  This plan adds the held-out set (Decision 1).
- **Conditional metric:** a metric with its own `where` conditions, counted or summed only
  over the rows that match them. Example: count of work orders where status is cancelled,
  next to the count of all work orders, in the same query.
- **Ratio metric:** one metric divided by another metric of the same intent, optionally
  times 100 (`as_percent`). Both are computed over the same rows. Division by zero gives
  an empty value (NULL), never an error and never 0.
- **Series intent:** a new `intent_type`, `date_series`. It holds one calendar grain, one
  period, and up to 4 series. Each series is a metric counted or summed by its own date
  field. The answer has one row per period, and one column per series.
- **Placeholder reason:** an `unanswerable_reason` that says nothing: empty or blank, or
  (any case, trimmed) `none`, `null`, `n/a`, `na`, `-`, `unknown`, `no reason`.
- **Refuse first:** a prompt rule. When a question needs something the intent cannot
  express, answer `unanswerable` and name what is missing, rather than answer a nearby
  question.
- **Wrong-answer rate:** wrong answers divided by answered questions, as in v0.1. L11 caps
  it at 5%.
- **Cost per question:** the report's measured mean model cost for one question through
  the `ledgerline` system, retries included, at the configured list price.
- **Live spend:** money charged by the Anthropic API for runs in this plan, as the budget
  guard counts it.

## PR-G — grammar v0.2

### Phase 0: held-out set, predictions (orchestrator, before any code)
1. **Who writes it:** a separate one-shot writer agent, which the orchestrator runs
   before any builder starts. It is not the builder, and no builder is briefed until the
   hash is committed. It gets only: the fieldservice schema and
   registry descriptions, `evals/gold/README.md` (categories, reference time, conventions),
   the item schema in `ledgerline/gold.py`, and these counts:
   - 40 items: 28 in_schema, 6 out_of_schema, 6 should_refuse;
   - among in_schema: at least 5 that ask for a share, percentage or ratio; at least 4
     that ask for two counts or totals by two different dates in one table; at least 6
     that need something v0.2 still lacks (a duration between two dates, a product of two
     fields, "has none", a distinct count of periods); the rest ordinary questions.

   It does not see the seen questions, the grammar design or this plan's predictions.
   Every in_schema `gold_sql` must run twice on the seeded Postgres as the read-only role
   and return the same non-empty result, as for the seen set.
2. **How it stays blind:** the writer saves the file to
   `/Users/cortega/Documents/Projects/ledgerline/holdout-v02/`, outside every worktree.
   Only its SHA-256 is committed, in `evals/gold/MANIFEST.json` under a `pending` key, with
   a CHANGELOG revision that says why. The builder's brief never names that folder, and
   the file enters the repo only in Phase 4, after the grammar and prompt are frozen.
   The hash proves the questions did not change after the code was written. It cannot
   prove nobody opened the file; keeping it out of every brief and worktree is what
   guards that.
3. ADR-007 (grammar v0.2) is committed with the predictions below and an empty Result.

**Exit:** the hash, the CHANGELOG revision and ADR-007 are committed before the first
commit that touches `ledgerline/core/` (G1).

### Phase 1: placeholder reasons, conditional and ratio metrics (builder)
1. **Placeholder reasons.** A new code, `placeholder_reason`:
   - on an `unanswerable` intent, a placeholder reason is rejected. Today it passes and
     becomes a refusal whose reason is "None";
   - on any other intent, a placeholder reason is still rejected, as now, but with this code
     and the message "leave unanswerable_reason out unless the intent is unanswerable", so
     the retry can drop it (Decision 3).
2. **Conditional metric.** `Metric` gains `where: list[Condition]` (no groups). Conditions
   follow every filter rule: hidden, filterable, operator and value type, allowed values,
   reachability, fan-out. Compiled as `agg(CASE WHEN … THEN x END)`, which runs the same on
   Postgres and SQLite. A conditional `count` with no field counts matching rows.
3. **Ratio metric.** `agg: "ratio"` with `numerator` and `denominator` (aliases of other
   metrics in the same intent) and `as_percent: bool`. Compiled as
   `numerator * scale / NULLIF(denominator, 0)` in floating point. New validator codes:
   `ratio_ref` (an alias that is missing, is itself a ratio, or is the ratio), `ratio_shape`
   (fields a ratio does not take). A ratio can be sorted on and used in `having`.
4. **Tests:**
   - a named test per new code (the meta-test already fails a code without one);
   - the differential oracle gains 8 hand-written intents with conditional and ratio
     metrics, each with a reference query written by hand, on Postgres and SQLite: a share
     overall, by group, by calendar grain, with `as_percent` both ways, a zero denominator,
     a ratio of two sums, a conditional count in `having`, and a ratio across a join;
   - the sentinel property also generates `where` values and asserts each is bound.

### Phase 2: series intent (builder)
1. `intent_type: "date_series"` with `entity`, `grain`, an optional `date_range` period
   (relative token or start and end, applied to each series by its own date field),
   shared `filters`, and `series`: 1 to 4 items of `{metric, date_field, where, alias}`.
2. Validator: each `date_field` is a date or datetime field on the base entity or along a
   many-to-one path; one grain for all series; series aliases unique and distinct from
   `period`; no `group_by`, `select` or `having`; fan-out checked per series; new codes
   `series_shape` and `series_date_field`.
3. SQL: one grouped subquery per series (`period`, value), each filtered by the shared
   filters, its own `where`, and the period on its own date field. The periods are the
   union of every series' periods; each series is left-joined to them. A period with no
   rows in one series shows 0 for a count and NULL for any other aggregate. Ordered by
   period. No `FULL OUTER JOIN` and no `generate_series`, so it runs on SQLite (the
   deployed engine) and Postgres alike.
4. Tests: a named test per code; 4 oracle intents on both engines (two counts on two
   dates, a count and a sum, a period where one series is empty, a series across a join);
   grain tests reuse the cross-dialect cases.

**Checkpoint review** after Phase 2, before any live spend: `/code-review` on the core
diff. The SQL builder is the security-relevant code, so it is reviewed apart from the
prompt and docs.

### Phase 3: prompt, trace and replay (builder, then orchestrator for live steps)
1. **Prompt `interpret-v2`:** describes conditional metrics, ratios and `date_series`, and
   adds the refuse-first rule. It also says what is still out: durations between two dates,
   products of fields, "has none" questions, distinct counts of periods.
   - Its examples use made-up entities that are not in fieldservice.
   - **No tuning to the gold:** a test fails if any 6-word run from any seen or held-out
     question appears in `prompt.py`, in a registry description, or in an alias.
2. **API and pages:**
   - `/ask` returns the new intent fields as they are.
   - The trace view shows a ratio's formula and each series' date field.
   - The Ask page has a plain-English message and a suggestion for every new code.
   - The Playwright smoke test covers one ratio and one series question in replay mode.
3. **Eval option:** `ledgerline eval --gold <file>` scores a second gold file for the same
   schema. The report names the gold file in its header and in each row, so seen and
   held-out results can never be mixed up. Tested with a two-item fixture file.
4. **Replay (orchestrator, live):**
   - re-record the canned demo questions under `interpret-v2`, and check that every one
     still answers;
   - re-record the fieldservice replay report's recordings, so `verify.sh` reproduces the
     new replay report.

### Phase 4: the live re-measure (orchestrator)
1. Move the held-out file into `evals/gold/`. The manifest test checks it against the
   committed hash, and the gold test runs its SQL.
2. Run, all on `anthropic:claude-haiku-5-5`, record mode, under one `--budget 3` for the
   whole phase:

   | Run | Questions | Systems | Code | Trials |
   |---|---|---|---|---|
   | `v02-holdout-before` | held-out (40) | ledgerline, oneshot | v0.1 (main at `fc97462`) | 3 |
   | `v02-holdout` | held-out (40) | ledgerline, oneshot | v0.2 | 3 |
   | `v02-seen` | seen (67) | ledgerline, oneshot | v0.2 | 3 |
   | `v02-spider-before` | Spider (250) | ledgerline, oneshot | v0.1 | 1 |
   | `v02-spider` | Spider (250) | ledgerline, oneshot | v0.2 | 1 |

   The "before" runs use the v0.1 code, so the held-out and Spider comparisons differ only
   in the grammar and the prompt. v0.1's eval cannot load a second gold file, so the
   "before" code is branch `v02-before`: `fc97462` plus one commit that adds only the
   `--gold` option from Phase 3. It is never merged. Three trials, because the L11
   margin is a single answer and Haiku runs with no sampling settings.
3. **Triage** every Ledgerline miss in all five runs. Notes on held-out items may quote
   them, since they are ours. Spider notes cite IDs only, as before.
4. **No changes after a result.** After the first live result, `prompt.py` and the
   grammar do not change. If a run finds a bug in the builder or the scorer, the fix is
   logged in the build log, and every run it touches is run again in full.
5. `evals/floors.yaml` gains a held-out entry with the same two limits as L11. ADR-007,
   the README results table, `docs/failures/` (a "v0.2" line on fs-028 and fs-035, plus any
   new failure worth a page) and the build log are written from the reports.

**Exit:** five reports committed, total live spend printed in each and summed in the
build log, `./verify.sh` green.

### What is measured, and how
- **Main result:** the held-out runs. Accuracy and wrong-answer rate on its 28 in_schema
  questions, before and after, pooled over 3 trials, with Wilson 95% intervals. Also
  refusal recall on its 12 refusal questions.
- **Seen result:** L11 on the seen set, reported as met or not met as measured. Because
  the change was built from two of these questions, a pass here is labelled "seen"
  wherever it appears.
- **Side effects:** Spider before and after, per database: coverage, accuracy and
  wrong-answer rate. Unreadable answers, as a share of calls, in every run (ADR-004's gate
  is 2%).
- **Cost:** cost per question before and after; total live spend.
- **The baseline:** oneshot runs on the same questions, as the comparison the README
  already makes.

### Predictions (committed in ADR-007 before the first live run)
1. **Seen, fs-028 and fs-035:** each is correct in at least 2 of its 3 trials.
2. **Seen, L11:** wrong-answer rate, pooled over 3 trials, is at most 5% (expected 2–4%).
   Accuracy is at least 81.4% (expected 37–39 of 43 per trial).
3. **Seen, fs-041:** now expressible (a conditional count in `having`, over the 3-hop
   path v0.1 added), and correct in at least 1 of 3 trials. fs-025, fs-030, fs-037,
   fs-039 and fs-042 are still refused.
4. **Held-out, wrong answers:** v0.2's wrong-answer rate is lower than v0.1's on the same
   questions, and at most 8%. Held-out questions are new to both, so a rate above the
   seen rate is expected.
5. **Held-out, accuracy:** v0.2 answers at least 4 more of the 28 in_schema questions
   correctly than v0.1, summed over 3 trials, mostly on the share and two-date questions.
6. **Held-out, refuse first:** of the questions that need something v0.2 lacks, at least
   80% are refused, not answered wrongly.
7. **Refusals:** refusal recall is at least 23/24 per trial on seen, and at least 11/12 per
   trial on held-out.
8. **Spider:** v0.2's wrong-answer rate is no more than 2 points above v0.1's, and
   coverage moves by no more than 3 points either way. Few Spider questions ask for
   ratios or two-date series, so little should change.
9. **Unreadable answers:** at most 2% of calls in every v0.2 run, despite the longer
   schema and prompt.
10. **Cost:** cost per question rises by at most 30% from $0.000415, because the prompt is
    longer. Total live spend for Phase 3 and Phase 4 is under $1.20.

### Spend
- **Cap: $3** for every live call in PR-G (demo re-record, replay recordings and the five
  runs), enforced by the budget guard. Expected: under $1.20.
- If a run stops at the cap, its partial report is committed as partial, and the
  orchestrator asks Cristian before spending more.
- Spend appears in each report's header and, summed, in the build log and the PR body.

### Acceptance (PR-G)
- **G1** The held-out hash, its CHANGELOG revision and ADR-007's predictions are
  committed before the first commit touching `ledgerline/core/` (`git log`). The revealed
  file matches the hash.
- **G2** The held-out set meets the Phase 0 counts. Every in_schema item runs twice with
  the same non-empty result. The manifest test covers it.
- **G3** Every new validator code (`placeholder_reason`, `ratio_ref`, `ratio_shape`,
  `series_shape`, `series_date_field`) has a named test. A placeholder reason is rejected
  on unanswerable intents and on all others.
- **G4** The 12 new oracle intents match their hand-written references on Postgres and
  SQLite. A zero denominator gives NULL. An empty period in one series gives 0 for a
  count.
- **G5** The sentinel property covers `where` values and series filters: no value in SQL
  text, and every value bound.
- **G6** Branch coverage stays at or above 95% on `validate.py` and `sqlbuild.py`.
- **G7** The no-tuning test passes: no 6-word run from any seen or held-out question in
  the prompt, registry descriptions or aliases.
- **G8** Every canned demo question answers under `interpret-v2`. `verify.sh` reproduces
  the new replay report. The Playwright smoke test covers a ratio and a series question.
- **G9** The Ask page has plain-English text for every new code (test).
- **G10** Five live reports are committed, every miss triaged, total spend at most $3 and
  shown. No change to `prompt.py` or `ledgerline/core/` after the first live report,
  except logged bug fixes followed by full re-runs (`git log`).
- **G11** ADR-007 has its measured result against every prediction. The floors file
  reports the seen and held-out results as met or not met, as measured. The README and
  failure pages say which numbers come from seen questions and which from held-out ones.
- **G12** `./verify.sh` is green.

## PR-V — value calculator

### The page
`/value/`, a Vite + TypeScript page next to Results (`web/value/index.html`,
`web/src/value.ts`, plus an entry in `vite.config.ts`). FastAPI already serves the built
pages, so no Python changes.

**Measured, read from a committed report** (shown, not editable, each with its source):
- the model id, the run id and the run date;
- cost per question;
- answered share: the coverage on in_schema questions, on held-out (`v02-holdout`) and on
  seen (`v02-seen`) questions;
- wrong-answer rate among answered, with its 95% interval, on both sets. It is shown
  only and does not feed the formula.

**Set by the reader** (sliders with a number box beside each; defaults labelled
"example, replace with your own"):
- data questions your team asks each month (example: 500), with an example question under
  it: "e.g. 'How many deals closed last month?'";
- minutes a person takes to answer one question by hand (example: 20);
- minutes to check an answer Ledgerline gives (example: 2);
- that person's cost per hour (example: $60);
- hosting per month (example: $10);
- savings from findings you'd act on each month, the reader's estimate (example: $0;
  owner's decision, 2026-11-13), with one line under it: "Messy data hides costs no one
  has time to look for. When asking takes seconds, people ask the questions they used to
  skip."

**The formula** (owner's decision, 2026-11-13: the page shows the value of a tool like
this, the hours saved against the running cost; shown on the page, in words and as math):
- running cost = questions × cost per question + hosting;
- answered = questions × answered share;
- time saved = answered × (minutes by hand − minutes to check) ÷ 60, in hours;
- value of time = time saved × cost per hour;
- net value a month = value of time + findings − running cost (findings added by the
  owner's decision, 2026-11-13; at $0 every figure is as before).

A refused question goes back to a person, so it saves nothing. Its model cost is already
in cost per question. A wrong answer has no separate dollar cost: every answer shows its
query, and checking it is how a wrong one gets caught, so the check time is counted.

**The headline and its range** (owner's decision, 2026-11-13). The headline uses the
held-out answered share. Net value is also shown at the seen answered share, so the
range runs from "on questions it never saw" to "on questions it was tuned on". Cost per
question comes from `v02-seen`.

**Answer time** (owner's decision, 2026-11-13), not in dollars: "Answer time: about N
seconds, compared with hours or days in someone's queue." N is the median latency
(`p50_latency_ms`) of `v02-holdout`'s Askwell row, with its source named.

**Plain words on the page:** model cost is the provider's list price. The measured rates
come from one benchmark schema, not the reader's data.

### The cost source
The page reads one report through the existing `/api/reports/<id>` route. The report id is
one constant in `web/src/value.ts`; a test checks it names a committed live report (not
simulated) with a `ledgerline` row for the default model.
- Built in parallel, PR-V starts on `select-haiku-2026-11-11`.
- Whichever PR merges second points the constant at `v02-seen`, so the calculator shows
  v0.2's cost and rates. That is a one-line change plus its test.

### Design (orchestrator, with /impeccable)
Design happens in two places, both run by the orchestrator, never by the builder:
1. **Before the build:** `/impeccable` shapes the page: layout, hierarchy, how measured
   and reader-set numbers look different, slider and number-box behaviour, empty and
   error states, phone width. It works within the existing pages' `style.css`. The result
   goes in `builds/v02/value-design.md`, and the builder is briefed from it.
2. **After the build, before `/pr-review`:** `/impeccable` critiques the running page
   against `value-design.md`. Material fixes go back to the builder. The rest is filed in
   the PR body.

### Acceptance (PR-V)
- **V1** `/value/` builds and is served. It shows the model id, the run id and the run date
  from the report (Playwright).
- **V2** The cost per question on the page equals the report row's `mean_cost_usd` to 6
  decimals (Playwright). The report constant names a committed live report (test).
- **V3** The formula has a unit test with known inputs, including a zero answered share
  and minutes to check greater than minutes by hand. The page shows the formula.
- **V4** Every reader-set input is labelled as an example. Every measured input names its
  source. Moving a slider updates the results. Typing out of range clamps the value, and
  no `NaN` or `Infinity` ever shows (Playwright).
- **V5** The range at the held-out and seen answered shares matches the formula at those
  two shares (test; owner's decision, 2026-11-13).
- **V6** Works with the keyboard alone, has labels on every input, honours reduced
  motion, and has no sideways scroll at 375 px wide (Playwright).
- **V7** `value-design.md` exists before the first page commit (`git log`), and the
  post-build critique is recorded with each finding fixed or filed.
- **V8** The README links the page with one short paragraph. `./verify.sh` is green.

## Building in parallel
- **PR-G** stays in this worktree, `ledgerline-v01` on branch `v02-grammar`.
- **PR-V** gets its own worktree from `wnew` (branch `v02-value`), cut from the latest
  main.
- **Overlap:** they share only `README.md` (a section each), and later the report constant.
  Before calling them independent, the orchestrator runs
  `git merge-tree --write-tree v02-grammar v02-value`. When one merges, main is merged into
  the other and it is closed again before it is called ready.
- **Builders:** one per PR. PR-G's builder never sees the held-out file or the
  predictions' reasoning beyond what ADR-007 states.

## What touches the deployed beta
Nothing here deploys. These are what the next deploy after each merge carries:
- **PR-G changes the prompt version**, so every replay key changes. The canned demo
  questions are re-recorded in Phase 3; without that, the demo answers 409 in replay mode.
- **Live answers change behaviour.** The beta's model sees the new prompt and can return
  ratios and series. The new SQL must run on SQLite, the deployed engine for both the demo
  and workspaces (G4 tests both engines).
- **Workspace asks** get the same grammar. Uploaded data with two date columns can now
  get series answers.
- **Cost per question rises slightly** (prediction 10). The daily cap is unchanged; at
  about $0.0005 a question it still allows thousands of asks a day.
- **The Results page** lists the new reports. It opens the report covering the most
  schemas first, which will be a Spider run, not `v02-seen`.
- **PR-V adds `/value/`.** It sits behind the invite gate like every page. No new
  settings.
- Neither PR adds an environment setting or a database change. Each needs an image
  rebuild and a redeploy.

## Out of scope
- Durations between two dates, products of fields, "has none" questions, distinct counts
  of periods (fs-025, fs-030, fs-037, fs-039, fs-042). They stay refusals.
- Any change to the seen gold set, or to fs-022 and fs-024's open gold issues.
- The model choice rule (ADR-004) and the default model. No new selection run; gemma is
  not re-run.
- The sql_agent baseline.
- The Atlas deploy.
- Redesigning any page other than `/value/`.
- A cost model for anything but model calls and one hosting number.
