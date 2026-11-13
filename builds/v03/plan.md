# Askwell v0.3 — accuracy plan

**Outcome:** Askwell is right more often, and wrong less often, on questions nobody building
it has seen: on the curated fieldservice schema and on schemas it was never tuned for,
including CSV files uploaded through the public site. Measured once, live, on Claude
Haiku 5.5, on a new held-out set written and hash-committed before any fix.

**Why now:** the owner's goal (2026-11-13, "fix accuracy"). On the v0.2 held-out questions
Askwell is right on 40 of 84 (47.6%, target 80%) and wrong on 14 of 54 answered (25.9%,
target 5%) ([v02-holdout](../../evals/reports/v02-holdout.md)). On four of five Spider
databases it refuses 40–56% of questions that have an answer
([v02-spider](../../evals/reports/v02-spider.md)). The public site now lets anyone upload
their own CSV files, which are uncurated schemas.

**PRs:** three, one after another, each branched from main after the previous one merges.
See "PR shape" for the reason.

## Status of this plan
Phase 0 only. Nothing below is approved. The decisions the orchestrator or Cristian must
make are listed under "Open choices", each with a recommended answer. No code and no live
call happens before approval.

## Definitions
- **Seen questions:** every question whose failures anyone building v0.3 has read. From
  now on that is the 67 fieldservice gold questions, the 40 v0.2 held-out questions
  (`holdout-v02.jsonl`), and the 250 pre-registered Spider questions. Results on them are
  always labelled "seen".
- **v0.3 held-out questions:** a new fieldservice set, `holdout-v03.jsonl`, written before
  any v0.3 code by an agent that has seen neither the old questions, their failures, nor
  this plan. It carries v0.3's main claim.
- **New Spider questions:** questions from the Spider dev databases v0.2 never used,
  selected by a fixed rule and committed as IDs before any v0.3 code. They carry the
  uncurated-schema claim. The builder never opens them.
- **CSV path:** the public upload path: CSV files → `askwell/workspace/check.py` (types,
  ID columns, links) → a workspace registry → ask. It is different code from
  `registry init`, which the Spider eval uses today.
- **False refusal:** a refusal of an `in_schema` question. It counts against accuracy even
  when refusing was the honest thing to do because the grammar cannot express the
  question; the scorer does not change that.
- **Question-level result:** a question counts as right if it is right in at least 2 of its
  3 trials. Its interval uses the number of distinct questions, which is the honest
  sample size; trials of one question are not independent.
- **Cutoff tie:** a top-N answer where the row after the Nth has the same ordering values
  as the Nth, so which rows make the list is arbitrary.

## Diagnosis

### How it was measured
- The per-trial outcomes and the triage notes are from
  `evals/reports/v02-holdout.json` and `v02-spider.json` (`misses`).
- The intents and SQL behind each wrong answer were reproduced in this worktree by
  replaying the committed recordings (`evals/recordings/eval/fieldservice/*.jsonl`) with
  `run_eval(..., mode="replay", gold=holdout-v02.jsonl)`. Replay makes no model call. It
  reproduced the report exactly: Askwell 40 right, 30 refused, 14 wrong on in_schema;
  36 of 36 refusal items refused. The scratch script is
  `/private/tmp/claude-501/-Users-cortega-Documents-Garman-Homes/605bd24a-e5e7-4ead-9928-3e9484df48a9/scratchpad/v03/replay_holdout.py`.
- Gold and answer rows were compared with `askwell/bench/compare.py` on this worktree's
  seeded database (Postgres on port 56452, see "How this was run").

### Held-out, the 14 wrong answers

| Item | Trials | What Askwell returned | Why it is scored wrong | Kind |
|---|---|---|---|---|
| ho-020 | 3 of 3 | Right 5 customers, right totals, right order | Gold also returns `c.id`; `compare.py:178-188` needs every gold column, and Askwell returns name and total only | Scoring question, and a product bug behind it (below) |
| ho-024 | 3 of 3 | Right 10 parts, units and order | Same: gold returns `p.id` | Same |
| ho-022 | 3 of 3 | Right 10 cities and counts | Gold breaks ties by city name (Des Moines, Milwaukee, Philadelphia all 36; Charlotte, Kansas City both 33); the answer's order inside those ties differs, and ordered comparison is strict (`compare.py:150-151`) | Scoring question (the tie order is the gold's arbitrary choice) and a product bug (order inside ties is undefined) |
| ho-028 | 3 of 3 | Five technicians, right counts | Gold returns `t.id`, and the question has no single answer: three technicians (ids 8, 15, 17) tie at 21 jobs for places 4 and 5; gold picks 8 and 15 by id, the answer picked 17 and 8 | Gold ambiguity (cutoff tie) plus the id column |
| ho-010 | 2 of 3 | Monthly scheduled and completed counts | Trial 1 added `status != cancelled`, which the question does not ask for. Trial 3 read "January through June" as `ytd`, which stops at the reference time (2026-06-30 00:00) and drops 30 June's scheduled visits | Product: model misread |

Evidence for the product bugs:
- **Grouping by a name merges different things.** `askwell/core/sqlbuild.py:531-551`
  groups by the requested field only (`GROUP BY t3.name` in every ho-020 trial). The
  seeded data has two different customers named "Garcia Ltd" (ids 56 and 144), so any
  per-customer answer that includes them adds them together. Every seen gold that groups
  by a thing groups by its id and shows its name (fs-032, fs-034, fs-038, fs-041, fs-043);
  the v0.2 held-out golds group by id and show both (ho-018, ho-020, ho-024, ho-028).
  Askwell matches neither.
- **Order inside ties is undefined.** `sqlbuild.py:556-566` orders only by what the intent
  names. Rows that tie come back in whatever order the engine returns, which can differ
  between Postgres and SQLite (the deployed engine) and between runs.
- **A top-N list silently cuts a tie** (ho-028). Nothing tells the reader that other rows
  tie with the last one shown.

What would change with each fix, checked on the recorded answers (seen, so not a claim):
- Grouping by id and returning it: ho-020 and ho-024 match the gold in all 3 trials
  (`compare.py` accepts extra columns, so the seen golds that show only the name still
  match). 6 of the 14.
- A defined tie order: ho-022 matches only if the tie-break happens to equal the gold's
  (city ascending). That is a coincidence of conventions, not accuracy, so it is not
  counted as a fix.
- ho-028 has no right answer to match. Its honest fix is in the gold, not in Askwell.

**Scoring:** none of this justifies a scorer change. The scorer stays as it is
(Decision S1 below). The id column and the tie order are handled in the product (stable,
correct grouping) and in the new held-out set's rules (a gold may not depend on an
arbitrary tie order), which are fixed before any v0.3 code.

### Held-out, the 30 false refusals
Ten questions, refused in all 3 trials each. Every refusal named the missing feature
correctly (v02-holdout.md, "Ledgerline misses"), so these are grammar gaps, not misreads.

| Missing feature | Items | Refusals |
|---|---|---|
| Duration between two dates, or from a date to now | ho-011, ho-012, ho-019 | 9 |
| A value computed from two fields (product, difference) | ho-013, ho-014, ho-018 | 9 |
| "Has none": rows with no related rows | ho-015, ho-016 | 6 |
| Distinct count of periods (months) | ho-017 | 3 |
| Comparison with an aggregate (above the company average) | ho-025 | 3 |

These ten were written on purpose as beyond v0.2 (`builds/v02/plan.md`, Phase 0 quotas:
at least 6 such questions). That quota makes the v0.2 held-out accuracy a lower bound
for natural questions, which is one reason the new set has no feature quotas.

**Where the 80% target stands:** with every wrong answer above fixed except ho-010 and
ho-028, the v0.2 held-out would be at most 46/84 (54.8%). The target cannot be reached
without closing grammar gaps. The new held-out will show how common they are in
questions written without quotas.

### Spider, the 99 false refusals (seen)
From `v02-spider.json`, classified by each triage note; the 27 subquery cases were split
further by reading their Spider gold SQL (IDs only here, by the Spider licence rule).

| Cause | car_1 | dog_kennels | flight_2 | network_1 | wta_1 | Total | Kind |
|---|---|---|---|---|---|---|---|
| Two links between the same two tables (`ambiguous_path`, `validate.py:369-374`) | 0 | 0 | 10 | 24 | 2 | 36 | Product: no way to name a link |
| Link not inferred by `registry init` | 3 | 0 | 13 | 0 | 0 | 16 | Product: inference too narrow |
| Numbers stored in a TEXT column | 9 | 1 | 0 | 0 | 0 | 10 | Product: type taken from the declaration, not the data |
| Set operation (INTERSECT, UNION, EXCEPT) | 2 | 4 | 2 | 1 | 1 | 10 | Grammar gap, out of scope |
| "Has" or "has none" (IN / NOT IN a related table) | 0 | 4 | 1 | 2 | 0 | 7 | Grammar gap, in scope |
| Comparison with an aggregate (avg, min) | 3 | 3 | 0 | 0 | 0 | 6 | Grammar gap, in scope |
| Comparison with the top row's value | 2 | 2 | 0 | 0 | 0 | 4 | Grammar gap, out of scope |
| Email and phone fields hidden by design | 0 | 6 | 0 | 0 | 0 | 6 | Product choice, kept |
| Gold returns no rows (trailing spaces) | 0 | 0 | 2 | 0 | 0 | 2 | Gold issue |
| Distinct rows in a list | 1 | 0 | 0 | 0 | 0 | 1 | Grammar gap, small |
| Misread (alias used as a field) | 1 | 0 | 0 | 0 | 0 | 1 | Product: model |

62 of the 99 (two links, missed links, numbers as text) need no new query shapes, only a
better registry and a way to name a link. 13 more need the "has none" and
aggregate-comparison features that the fieldservice gaps also need.

**The CSV path is narrower still** (`askwell/workspace/check.py:535-565`): a link exists
only for a column named `<table>_id` or `<singular>_id`. A table with two links to the
same table (`origin_airport_id`, `dest_airport_id`) gets no link at all, so the
two-links problem shows up there as `unreachable_field`. No eval measures this path today;
every Spider number comes through `registry init`.

## Held-out honesty

1. **The v0.2 held-out set is seen from now on.** Its failures were read for this plan.
   Its reports stay as they are. Every later mention (README, floors, Results page,
   ADR-008) labels it "seen (v0.2 held-out)". It is re-run under v0.3 only as a seen set.
2. **A new fieldservice held-out set, `holdout-v03.jsonl`, carries the main claim.**
   - **Size:** 120 items: 96 in_schema, 12 out_of_schema, 12 should_refuse. At 80% right
     on 96 distinct questions the Wilson interval is about 71–87%, so it can tell 80% from
     v0.2's level. The wrong-answer rate cannot be proven at or below 5% with any set we
     can write (5 wrong of about 85 answered gives about 3–13%); it is reported with its
     interval and judged on the point estimate, as v0.2 did.
   - **No feature quotas.** The writer writes questions as a field-service manager would
     ask them, spread over every entity, with a difficulty mix like the seen set's. It is
     not told what any grammar can or cannot express. A quota for the features v0.3 adds
     would steer the measure toward what v0.3 is built for.
   - **Who writes it, and what it sees:** a separate one-shot writer agent run by the
     orchestrator, before any builder starts on v0.3 code. It gets the fieldservice
     schema and registry descriptions, the item schema in `askwell/gold.py`, and the gold
     README's category, reference-time and convention rules with the two new rules below.
     It never sees the seen questions, the v0.2 held-out set, `docs/failures/`, the
     triage files, ADRs, the grammar, the prompt, or this plan.
   - **Two new gold rules, fixed now:**
     - A gold returns the columns the question asks for. When it groups or ranks by a
       thing (customer, technician, part), it groups by that thing's id and shows its
       name; it shows the id only if the question asks for it. This is the seen set's
       convention (Open choice O1).
     - An ordered gold must not depend on an arbitrary tie order: no two returned rows
       tie on the ordering the question asks for, and the row after a LIMIT does not tie
       with the last row returned, unless the question itself says how to break ties.
   - **Checks before the hash is taken** (a script run by the writer, then by the
     orchestrator): every in_schema gold runs twice as the read-only role with the same
     non-empty result; the tie rule holds (the gold is re-run with its ordering key only
     and LIMIT n+1); no question shares a 6-word run with any seen question; no two new
     questions share their gold SQL.
   - **Blind:** the file is saved to
     `/Users/cortega/Documents/Projects/ledgerline/holdout-v03/`, outside every worktree.
     Only its SHA-256 goes into `evals/gold/MANIFEST.json` under `pending`, with a
     CHANGELOG revision. No builder brief names that folder. The file enters the repo
     only in Phase 4, after the code and prompt are frozen. As in v0.2, the hash proves
     the questions did not change; keeping the file out of every brief and worktree is
     what keeps it unread.
3. **New Spider questions carry the uncurated claim.** The 5 Spider dev databases used so
   far are seen. Of the other 15, four have at least 50 questions: `world_1`,
   `cre_Doc_Template_Mgt`, `student_transcripts_tracking`, `tvshow`. All four are used, so
   no database is chosen by draw or by hand; 50 questions each are selected by the
   existing stratified rule (`evals/gold/spider_selection.py`) with a new seed, and the
   200 IDs are committed as `spider_ids_v03.json` before any v0.3 code (Open choice O7).
   The builder develops against the old 5 databases and synthetic fixtures only.
4. **One look.** Every held-out run (before and after) happens once, in Phase 4, after the
   freeze. No held-out result is seen before the code is final, and nothing in
   `askwell/core/`, `askwell/workspace/` or `prompt.py` changes after the first held-out
   result except logged bug fixes followed by full re-runs (as v0.2's rule 4).
5. **Predictions first.** ADR-008 is committed with the predictions below and an empty
   Result before the first commit that touches `askwell/core/`, `askwell/workspace/` or
   `askwell/pipeline/`.
6. **Question-level intervals.** Reports keep the pooled trial counts (comparable with
   v0.2) and add the question-level result with its interval (Open choice O4). The
   headline uses the question-level interval.

## PR-1 — stable answers

### Phase 1 (builder)
1. **Group by the thing, not its name.** When a `group_by` field belongs to an entity with
   a single-column primary key and is not that key, the SQL also groups by the key and
   returns it as a column (`<entity>_id`) just before the named field. On Postgres and
   SQLite alike.
2. **A defined order inside ties.** After the intent's own `order_by`, the SQL orders by
   every group-by column ascending (the key first), and a row list by the base entity's
   key. The same intent then gives the same rows in the same order on both engines and on
   every run.
3. **Say when a top-N cuts a tie.** When an intent has `limit` and `order_by`, the query
   fetches one extra row. If it ties with the last row on every ordering target, the
   answer carries `tied_at_cutoff: true`. The extra row is never shown. The trace view and
   the Ask page say "More rows tie with the last one shown."
4. **Tests first:**
   - oracle intents on both engines with hand-written references: two customers with the
     same name give two rows; ties come back in the same order on both engines; a top-N
     with and without a cutoff tie;
   - the replay eval reproduces a re-scored fieldservice replay report (the prompt does
     not change, so no recording changes and no live call is needed).

**Pass/fail:**
- **P1.1** The "Garcia Ltd" test gives two rows, on both engines.
- **P1.2** Every grouped or ordered oracle intent returns identical rows, in identical
  order, on Postgres and SQLite.
- **P1.3** `tied_at_cutoff` is true for a seeded cutoff tie and false otherwise; the extra
  row never appears in `rows`.
- **P1.4** Replaying the v0.2 held-out recordings under PR-1 code (seen, no live call):
  ho-020 and ho-024 right in 3 of 3, every item that was right is still right. Reported
  as a seen check only.
- **P1.5** Branch coverage on `sqlbuild.py` and `validate.py` stays at or above 95%;
  `./verify.sh` green.

## PR-2 — uncurated schemas

### Phase 2 (builder)
1. **Name a link.** When two or more links join the same pair of entities, each gets a
   role from its column (for example `source_airport`, `dest_airport`). A field reference
   can name the role (exact syntax in the ADR, chosen by the builder and tested). The
   `ambiguous_path` error lists the roles, so the retry can pick one. The prompt and the
   registry view show roles. An unnamed reference across an ambiguous pair is still
   refused, never guessed.
2. **Infer more links in `registry init`.** Without a declared key, a column links to
   table T when its name is T's key name, T's name, T's singular, or `<role>_<T>_id`, and
   every non-null value is a value of T's key (checked on the data). Containment is
   required, so a name match alone never makes a join.
3. **Infer more links on the CSV path.** `check.py` adds `<role>_<table>_id` and
   `<role>_<singular>_id`, with the same containment rule. A looser-rule link with values
   missing from the target is dropped with a warning, never turned into a blocking error,
   so a file that loads today still loads.
4. **Numbers stored as text** (`registry init` only; the CSV path already types by
   values): a TEXT column whose non-null values all parse as numbers is typed numeric
   and cast in SQL.
5. **A CSV-path eval system,** `askwell_csv`: it exports each Spider database's tables to
   CSV files in the gitignored `data/` folder, runs them through the workspace check and
   load as they are, and asks through the workspace pipeline with the pinned reference
   time. A table that fails the check is reported with its reason, and its questions count
   as refused (Open choice O6).
6. **Tests first:** synthetic fixtures for each rule (two links with roles; each inferred
   name form, with and without full containment; a numeric TEXT column; a mixed TEXT
   column that stays text); the CSV path on the same fixtures; a regenerated Spider
   registry for the old 5 databases, with its hashes updated and the reason recorded.

**Pass/fail:**
- **P2.1** For each of the 62 seen Spider refusals caused by two links, missed links or
  numbers as text, a hand-written intent (from the seen gold SQL) validates and returns
  the gold rows. This checks that the questions are now expressible; it does not measure
  the model. Target: at least 55 of 62.
- **P2.2** No inferred link on the old 5 Spider databases joins columns whose values are
  not contained in the target key (test).
- **P2.3** Every seeded CSV fixture that loads on main still loads, with the same tables
  and types.
- **P2.4** The `askwell_csv` system runs end to end on a fixture in replay mode.
- **P2.5** `./verify.sh` green; coverage floors held.

## PR-3 — grammar v0.3 and the measurement

### Phase 3 (builder)
1. **Computed values.** A metric field or a selected field can be
   `{op: multiply | subtract | add, left, right}` over two numeric fields on the base
   entity or along a many-to-one path. Fan-out rules apply to both fields.
2. **Durations.** `{days_between: [start, end]}`, where `end` may be `now` (the reference
   time). Numeric days, fractional, the same on Postgres and SQLite. Usable wherever a
   numeric field is.
3. **Has / has none.** A filter `{has: <one-to-many link>, where: [...], none: bool}`,
   compiled as `EXISTS` / `NOT EXISTS`. Its conditions follow every filter rule.
4. **Distinct count of periods.** `count_distinct` takes a `grain` on a date field.
5. **Compare with an aggregate.** A filter value `{of: avg | min | max, field}` computed
   over all rows of that field's entity, as a scalar subquery.
6. **Prompt `interpret-v3`:** describes each new feature with made-up entities; adds two
   general rules: never add a filter the question does not state, and a named span of
   whole months uses explicit start and end dates. Keeps refuse-first and lists what is
   still out (set operations, comparison with the top row's value, window functions).
7. **Tests first:** a named test per new validator code; oracle intents per feature on
   both engines with hand-written references (including a zero-row "has none", a
   duration to `now`, a product across a join); the sentinel property covers every new
   value slot; the no-tuning test also covers `holdout-v03` once it is in the repo.
8. **Re-record (orchestrator, live):** the canned demo questions and the fieldservice
   replay recordings under `interpret-v3`.

**Pass/fail:**
- **P3.1** For each of the 10 seen v0.2 held-out refusals and the 13 seen Spider
  "has none" and aggregate-comparison refusals, a hand-written intent validates and
  returns the gold rows (expressibility, not accuracy). Target: all 23.
- **P3.2** Every oracle intent matches its reference on both engines.
- **P3.3** No value in SQL text; every value bound (sentinel property).
- **P3.4** Coverage at or above 95% on `validate.py` and `sqlbuild.py`; `verify.sh` green.
- **P3.5** Every canned demo question answers under `interpret-v3`.

**Checkpoint review** after Phase 3, before any held-out run: `/code-review` on the core
diff (the SQL builder is the security-relevant code), run by the orchestrator.

### Phase 4: the measurement (orchestrator)
1. Move `holdout-v03.jsonl` into `evals/gold/`; the manifest test checks it against the
   pending hash. Add `spider_ids_v03.json` to the Spider eval.
2. Runs, all on `anthropic:claude-haiku-5-5`, record mode:

   | Run | Questions | Systems | Code | Trials |
   |---|---|---|---|---|
   | `v03-holdout-before` | v0.3 held-out (120) | askwell, oneshot | main at `4014aa0` | 3 |
   | `v03-holdout` | v0.3 held-out (120) | askwell, oneshot | v0.3 | 3 |
   | `v03-seen` | fieldservice seen (67) | askwell | v0.3 | 3 |
   | `v03-seen-holdout-v02` | v0.2 held-out, seen (40) | askwell | v0.3 | 3 |
   | `v03-spider-new-before` | new Spider (200) | askwell, oneshot | `4014aa0` | 1 |
   | `v03-spider-new` | new Spider (200) | askwell | v0.3 | 1 |
   | `v03-csv-new-before` | new Spider as CSV (200) | askwell_csv | `4014aa0` + only the CSV eval system | 1 |
   | `v03-csv-new` | new Spider as CSV (200) | askwell_csv | v0.3 | 1 |
   | `v03-spider-seen` | old Spider, seen (250) | askwell | v0.3 | 1 |

   "Before" code is branch `v03-before`: `4014aa0` plus only the eval-side additions it
   needs (the `--gold` file and the Spider ID file it reads, the `askwell_csv` system).
   Never merged.
3. Triage every Askwell miss in every run. Held-out notes may quote the questions; Spider
   notes cite IDs only.
4. ADR-008's Result, the README results table (seen and held-out labelled), the floors
   file, `docs/failures/` and the build log are written from the reports.

**Exit:** nine reports committed, spend shown in each and summed in the build log,
`./verify.sh` green.

## Predictions (for ADR-008, committed before the first core commit)
1. **v0.3 held-out, accuracy:** question-level at least 70%; expected 70–82%. The 80%
   target is the goal; this plan does not predict it is met.
2. **v0.3 held-out, wrong among answered:** pooled at most 8%; expected 3–8%.
3. **v0.3 held-out, before and after:** v0.3 is right on at least 10 points more of the
   questions than main at `4014aa0`, and its wrong rate is lower.
4. **Refusals:** refusal recall at least 23 of 24 per trial on the v0.3 held-out.
5. **Seen v0.2 held-out:** at least 66 of 84 right (from 40), wrong at most 4 of answered.
   Seen, so it shows the fixes work where they were aimed, nothing more.
6. **Seen fieldservice:** stays at or above 81.4% right and at or below 5% wrong (L11).
7. **New Spider (`registry init`):** false refusals fall by at least 10 points pooled
   over the four databases; the wrong rate rises by no more than 3 points.
8. **New Spider as CSV:** the share of tables that load is reported per database; on the
   loaded ones, false refusals fall by at least 10 points.
9. **Unreadable answers** at most 2% of calls in every run; **cost per question** up at
   most 35% from v0.2's $0.000480, because the prompt grows.

## Spend
- **Model:** `anthropic:claude-haiku-5-5`, list price, as in v0.2.
- **Estimate**, from v0.2's measured cost per call ($0.00047 on fieldservice, $0.00031 on
  Spider) plus 15% for the longer prompt and retries:

  | Item | Calls | Cost |
  |---|---|---|
  | Held-out before and after (120 × 3 × 2 systems × 2) | 1,440 | $0.75 |
  | Seen fieldservice and seen v0.2 held-out (107 × 3) | 321 | $0.17 |
  | New Spider before (×2 systems) and after | 600 | $0.21 |
  | New Spider as CSV, before and after | 400 | $0.14 |
  | Old Spider, seen | 250 | $0.09 |
  | Demo and replay re-records (PR-2 and PR-3) | ~280 | $0.14 |
  | **Total** | **~3,300** | **~$1.50** |

- **Cap: $4** for every live call in v0.3, enforced by the budget guard (`--budget` per
  run, summed in the build log). The margin covers one full re-run after a logged bug
  fix. If a run stops at the cap, its partial report is committed as partial and the
  orchestrator asks before spending more.
- No live call happens without the orchestrator's go, run by the orchestrator. Builders
  make none.
- Not counted here: the writer agent that writes the held-out set (an agent run, not an
  API call through the budget guard).

## PR shape: three PRs
- **PR-1, stable answers:** Phase 0's committed artifacts (held-out hash, new Spider IDs,
  ADR-008 with predictions) and Phase 1. It changes the SQL, not the prompt, so every
  recording stays valid and main keeps working with a re-scored replay report.
- **PR-2, uncurated schemas:** Phase 2. It changes the registry, the CSV checker and the
  prompt (link roles), so it carries its own small re-record.
- **PR-3, grammar v0.3 and the measurement:** Phase 3 and Phase 4. The prompt changes
  again, and the held-out runs must measure the final code.

Why three: each leaves main working and safe on its own; PR-1 is a small correctness fix
that is useful whatever happens to the rest; PR-2 and PR-3 each change
`sqlbuild.py`/`validate.py`, the security-relevant code, and a separate review slice
keeps each diff reviewable. Why not more: the measurement has to come after the last
code change, so it stays in PR-3. Why sequential and not parallel: PR-2 and PR-3 both
touch `validate.py`, `sqlbuild.py` and `prompt.py`. One worktree (this one), each next
branch cut from main after the previous merge.

## What touches the deployed beta
Nothing here deploys. The next deploy after each merge carries:
- **PR-1:** grouped answers gain an id column; top-N answers can say a tie was cut. Same
  prompt, so the demo's recorded answers still replay.
- **PR-2:** uploaded CSV files with `<role>_<table>_id` columns get links they did not
  have; a file that loaded before still loads (P2.3). New prompt version, so the demo is
  re-recorded in the PR.
- **PR-3:** new intent shapes on the deployed SQLite engine (every oracle test runs on
  both engines). New prompt version; cost per question rises (prediction 9). The daily
  cap is unchanged.
- No new environment setting or database change in any of the three.

## Open choices (with recommendations)
- **S1, scorer.** Recommend: no change. Penalising a missing id column and an arbitrary
  tie order is fixed instead in the product (stable grouping and order) and in the new
  gold rules. Any later scorer change would need its own ADR, apply to every system and
  re-score the baseline too.
- **O1, new gold columns.** Show only what the question asks for (the seen set's
  convention), or id and name (the v0.2 held-out writer's). Recommend: the seen set's.
  After PR-1 Askwell returns the id anyway, so this only changes how the one-shot
  baseline is scored, and the narrower gold is the fairer one.
- **O2, held-out size.** 120 (96/12/12) or 80 (64/8/8, about $0.25 cheaper). Recommend:
  120. At 64 questions the interval around 80% is about 68–88%, too wide to tell 75%
  from 85%.
- **O3, feature quotas.** None, or quotas like v0.2's. Recommend: none, with an entity
  spread and a difficulty mix like the seen set's.
- **O4, question-level intervals in reports.** Recommend: yes, added beside the pooled
  counts and used for the headline. It is a report change that applies to every system
  and every past report alike.
- **O5, cutoff ties.** Say so in the answer, or return every tied row (`WITH TIES`).
  Recommend: say so. `WITH TIES` has no SQLite form, and a top-5 that returns 6 rows
  surprises readers.
- **O6, CSV-path eval.** Build `askwell_csv`, or keep measuring uncurated schemas through
  `registry init` only. Recommend: build it. The public site's uploads go through
  `check.py`, which Spider through `registry init` never exercises.
- **O7, new Spider databases.** All four remaining dev databases with at least 50
  questions (200 questions), or lower the bar to 40 and draw 5 of 8. Recommend: all four;
  no draw, no hand choice.
- **O8, grammar scope.** All five features in Phase 3, or a subset. Recommend: all five.
  Set operations and "compare with the top row" stay out: they need nested queries the
  intent cannot keep simple.
- **O9, attribution.** Measure the held-out after each PR, or once at the end.
  Recommend: once. Each extra look at held-out results is a chance to tune to them.
- **O10, who writes the held-out set.** Recommend: the same arrangement as v0.2 (a
  one-shot writer agent, run by the orchestrator, not this builder).

## Out of scope
- Set operations, comparison with the top row's value, window functions, distinct row
  lists.
- Showing hidden email and phone fields on Spider (a product choice, kept).
- Any change to the seen gold sets, including fs-022 and fs-024's open gold issues and
  the flight_2 trailing-space golds.
- The model choice (ADR-004) and the default model; the sql_agent baseline.
- The value calculator, except pointing its report constant at the v0.3 reports if
  Cristian asks.
- The Atlas deploy.

## How this was run
- This worktree's own Postgres: `ASKWELL_DB_PORT=56452 docker compose up -d` (56432 is held
  by another worktree's container), with `ASKWELL_DATABASE_URL`,
  `ASKWELL_DATABASE_RO_URL` and `ASKWELL_APP_DATABASE_URL` pointed at port 56452 in the
  environment. `.env` was not read or changed.
- Spider dev was fetched into this worktree's gitignored `data/` with
  `uv run python -m scripts.fetch_benchmarks`.
- No live model call was made.
