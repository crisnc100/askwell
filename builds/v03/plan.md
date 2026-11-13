# Askwell v0.3 — accuracy plan (revision 2)

**Outcome:** Askwell is right more often, and wrong less often, on questions nobody building
it has seen: on the curated fieldservice schema and on schemas it was never tuned for,
including CSV files uploaded through the public site. Measured once, live, on Claude
Haiku 5.5, on a new held-out set written and hash-committed before any fix. Nothing
reaches the beta until that measurement passes its gate.

**Why now:** the owner's goal (2026-11-13, "fix accuracy"). On the v0.2 held-out questions
Askwell is right on 40 of 84 (47.6%, target 80%) and wrong on 14 of 54 answered (25.9%,
target 5%) ([v02-holdout](../../evals/reports/v02-holdout.md)). On four of five Spider
databases it refuses 40–56% of questions that have an answer
([v02-spider](../../evals/reports/v02-spider.md)). The public site now lets anyone upload
their own CSV files, which are uncurated schemas.

**PRs:** three, one after another, each branched from main after the previous one merges.
None is deployed before the Phase 4 gate. See "PR shape".

## Decisions (orchestrator, 2026-11-13, after the advisor's review)
- **D1 (O1):** new golds show only the columns the question asks for, never an id it did
  not ask for. ADR-008 records that this convention was chosen after seeing that Askwell
  failed the v0.2 held-out writer's id-column convention.
- **D2 (O2):** the new held-out set has 120 items.
- **D3 (O6):** build the CSV-path eval. It scores all 200 untriaged Spider questions;
  a table that fails the upload check makes its questions count as refusals.
- **D4 (O8):** four grammar features, not five. Distinct count of periods is dropped (it
  was fitted to ho-017 alone). Comparison with an aggregate is restricted (Phase 3, item 4).
- **D5:** no deploy of PR-1, PR-2 or PR-3 before the Phase 4 held-out look and its gate.
- **D6:** the $4 cap stands. Three PRs.
- **D7:** every other open choice takes the recommendation below (S1, O3, O4, O5, O7, O9,
  O10).

## Definitions
- **Seen questions:** every question whose failures anyone building v0.3 has read: the 67
  fieldservice gold questions, the 40 v0.2 held-out questions (`holdout-v02.jsonl`), and
  the 250 pre-registered Spider questions. Results on them are always labelled "seen".
- **v0.3 held-out questions:** a new fieldservice set, `holdout-v03.jsonl`, written before
  any v0.3 code by a separate model run that has seen none of the old questions, their
  failures, the grammar, or this plan. It carries v0.3's main claim.
- **Untriaged Spider questions:** 200 questions from the four Spider dev databases v0.2
  never used, selected by a fixed rule and committed as IDs before any v0.3 code. Nobody
  on v0.3 has read them, but they are public and may be in the model's training data, so
  they are called untriaged, not held out. They carry the uncurated-schema claim.
- **CSV path:** the public upload path. CSV files go through `askwell/workspace/check.py`
  (types, ID columns, links), are loaded into SQLite, and `registry init` drafts a registry
  that keeps only the links Check found (`askwell/workspace/fields.py:1-14`). The Spider
  eval today goes through `registry init` on Spider's own SQLite files, which declare
  their keys, so it never exercises Check.
- **Label field:** a field an entity declares as "the name of the thing" (a customer's
  name, a technician's full name). Grouping by it groups by the thing.
- **False refusal:** a refusal of an `in_schema` question. It counts against accuracy even
  when refusing was honest because the grammar cannot express the question.
- **Question-level accuracy:** a question counts as right if it is right in at least 2 of
  its 3 trials. Its interval uses the number of distinct questions; trials of one
  question are not independent.
- **Per-trial wrong rate:** wrong answers divided by answered, over every trial. It is
  the wrong-answer headline, because a 2-of-3 rule would hide a question answered wrongly
  in 1 of 3 trials.
- **Cutoff tie:** a top-N answer where the row after the Nth has the same ordering values
  as the Nth, so which rows make the list is arbitrary.
- **Feature switch:** each v0.3 feature that can turn a refusal into an answer (link
  roles, inferred links, numbers stored as text, and each grammar feature) can be turned
  off by one setting. Off, the validator refuses it as today and the prompt does not
  describe it.

## Diagnosis

### How it was measured
- Per-trial outcomes and triage notes: `evals/reports/v02-holdout.json` and
  `v02-spider.json` (`misses`).
- The intents and SQL behind each wrong answer were reproduced by replaying the
  committed recordings with `run_eval(..., mode="replay", gold=holdout-v02.jsonl)`.
  Replay makes no model call. It reproduced the report exactly: Askwell 40 right, 30
  refused, 14 wrong on in_schema; 36 of 36 refusal items refused. The scripts are
  committed in `builds/v03/evidence/`: `replay_holdout.py` (the replay),
  `idcheck.py` (gold against answer rows with `compare.py`) and `namecheck.py` (the seen
  golds that group by a thing). They expect the database on port 56452 (see "How this
  was run").

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
  by a customer, technician or part groups by its id and shows its name (fs-032, fs-034,
  fs-038, fs-041, fs-043); the v0.2 held-out golds group by id and show both (ho-018,
  ho-020, ho-024, ho-028). Golds that group by a plain attribute (`region`, `city`,
  `job_type`; fs-019, fs-033, ho-004, ho-022) group by the value. The registry has no way
  to tell the two apart today: `FieldDef` (`askwell/core/registry.py:38-50`) has no
  "name of the thing" marker.
- **Order inside ties is undefined.** `sqlbuild.py:556-566` orders only by what the intent
  names. Rows that tie come back in whatever order the engine returns, which can differ
  between Postgres and SQLite (the deployed engine) and between runs.
- **A top-N list silently cuts a tie** (ho-028). Nothing tells the reader that other rows
  tie with the last one shown.

What each fix would change on the recorded answers (seen, so not a claim):
- Grouping by a declared label field: ho-020 and ho-024 match in all 3 trials, because
  `compare.py` accepts extra columns. 6 of the 14.
- A defined tie order: ho-022 would match only if the tie-break equals the gold's (city
  ascending). A coincidence of conventions, so it is not counted.
- ho-028 has no right answer to match.

**Scoring:** none of this justifies a scorer change (S1). The id column and the tie order
are handled in the product (label grouping, a defined order) and in the new held-out
set's rules, which are fixed before any v0.3 code.

### Held-out, the 30 false refusals
Ten questions, refused in all 3 trials each. Every refusal named the missing feature
correctly (v02-holdout.md, "Ledgerline misses"), so these are grammar gaps, not misreads.

| Missing feature | Items | Refusals | In v0.3 |
|---|---|---|---|
| Duration between two dates, or from a date to now | ho-011, ho-012, ho-019 | 9 | yes |
| A value computed from two fields (product, difference) | ho-013, ho-014, ho-018 | 9 | yes |
| "Has none": rows with no related rows | ho-015, ho-016 | 6 | yes |
| Comparison with an aggregate (above the company average) | ho-025 | 3 | yes, restricted |
| Distinct count of periods (months) | ho-017 | 3 | no (D4) |

These ten were written on purpose as beyond v0.2 (`builds/v02/plan.md`, Phase 0 quotas:
at least 6 such questions). That quota makes the v0.2 held-out accuracy a lower bound for
natural questions, which is one reason the new set has no feature quotas.

**Where the 80% target stands:** with every wrong answer above fixed except ho-010 and
ho-028, the v0.2 held-out would be at most 46/84 (54.8%). The target cannot be reached
without closing grammar gaps. The new held-out set will show how common they are in
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

The car_1 "numbers as text" columns are not clean: `cars_data.Horsepower` holds the
string `'null'` in 6 of 406 rows and `MPG` in 8 (checked with `sqlite3` on the seen
car_1 file before it was removed from this worktree). A rule that needs every value to
parse would leave all 9 car_1 cases refused (Phase 2, item 4).

**The CSV path is narrower still** (`askwell/workspace/check.py:535-565`): a link exists
only for a column named `<x>_id` where `<x>` or `<x>s` is a table. A table with two links
to the same table (`origin_airport_id`, `dest_airport_id`) gets no link at all, and
`permanent_address_id` does not reach `addresses`. No eval measures this path today.

## Held-out honesty

1. **The v0.2 held-out set is seen from now on.** Its reports stay as they are. Every
   later mention (README, floors, Results page, ADR-008) labels it "seen (v0.2 held-out)".
   It is re-run under v0.3 only as a seen set.
2. **A new fieldservice held-out set, `holdout-v03.jsonl`, carries the main claim.**
   - **Size:** 120 items: 96 in_schema, 12 out_of_schema, 12 should_refuse (D2). At 80%
     right on 96 distinct questions the Wilson interval is about 71–87%. The wrong-answer
     rate cannot be proven at or below 5% with any set we can write (5 wrong of about 85
     answered gives about 3–13%); it is reported per trial with its interval and judged
     on the point estimate, as v0.2 did.
   - **No feature quotas.** Questions as a field-service manager would ask them, spread
     over every entity, with a difficulty mix like the seen set's. The writer is not
     told what any grammar can or cannot express.
   - **A scrubbed brief, committed first.** The builder drafts
     `builds/v03/holdout-writer-brief.md`; the orchestrator reviews it and commits its
     SHA-256 in `evals/gold/MANIFEST.json` (`pending`) before the writer runs. It holds
     only: the fieldservice DDL and registry descriptions; the item schema from
     `askwell/gold.py`; the three categories (in_schema, out_of_schema, should_refuse)
     defined from scratch; the reference time and how relative periods resolve; the
     counts; and the neutral answer conventions below. It never quotes or links
     `evals/gold/README.md` (which describes earlier questions as beyond a query grammar
     and states a tie rule this plan replaces), any gold file, ADR, failure page,
     triage file, prompt, grammar or this plan.
   - **Neutral answer conventions** (one list, every item worded the same way, so no item
     points at a feature): money as stored, never rounded; a share as a fraction from 0
     to 1 unless the question asks for a percent; a period as the date of its first day;
     a duration as fractional days; a count as an integer; a thing (customer,
     technician, part) shown by its name, never by an id the question does not ask for
     (D1); text values exactly as stored.
   - **The tie rule:** an ordered gold must not depend on an arbitrary tie order: no two
     returned rows tie on the ordering the question asks for, and the row after a LIMIT
     does not tie with the last row returned, unless the question itself says how to
     break ties.
   - **A clean directory and a separate run.** The orchestrator starts the writer as its
     own model run, not this builder, in a new empty directory,
     `/Users/cortega/Documents/Projects/ledgerline/holdout-v03/`, outside every worktree,
     holding only the brief. It gets read-only access to the seeded database to run its
     gold SQL.
   - **Checks, run by the orchestrator only:** every in_schema gold runs twice as the
     read-only role with the same non-empty result; the tie rule holds (each ordered gold
     is re-run with LIMIT n+1); no question shares a 6-word run with any seen question;
     no two new questions share their gold SQL. The builder writes the check script in
     Phase 0b, tests first, against synthetic items; it never runs it on the new file.
   - **The tie rule's cost is reported.** It removes questions whose honest answer
     depends on a tie, the class ho-022 and ho-028 belong to, so it flatters the absolute
     rate. The writer logs every draft it dropped or reworded for the tie rule, the
     orchestrator counts the check's rejections, and ADR-008 reports both numbers next
     to the result.
   - **Blind until the freeze:** only the file's SHA-256 goes into the manifest, with a
     CHANGELOG revision. No builder brief names the folder. The file enters the repo in
     Phase 4. The hash proves the questions did not change; keeping the file out of every
     brief and worktree keeps it unread.
3. **Untriaged Spider questions.** Of the 15 Spider dev databases v0.2 did not use, four
   have at least 50 questions: `world_1`, `cre_Doc_Template_Mgt`,
   `student_transcripts_tracking`, `tvshow`. All four are used, so no database is chosen
   by draw or by hand. 50 questions each are selected by the existing stratified rule
   with a new seed. `evals/gold/spider_selection.py` is hash-frozen and draws 5
   databases, so it is not changed: a new `evals/gold/spider_selection_v03.py` imports its
   stratification and writes `spider_ids_v03.json`, with its own manifest entry. The
   orchestrator runs it and commits the IDs before any v0.3 code.
   - **The builder never holds the new databases.** Spider was fetched into this
     worktree for the diagnosis; the extracted folder and the archive were deleted after
     it (`data/spider/` and `data/downloads/spider_data.zip`). In this worktree only the
     20 database names and their question counts were listed, and only the gold SQL of
     the 27 seen subquery IDs above was read. For Phases 2 and 3 the orchestrator puts
     only the five seen databases and a `dev.json` cut to the 250 seen IDs into the
     builder's `data/`.
   - **After the freeze,** the orchestrator fetches the new databases, generates their
     registries and runs every untriaged-Spider run.
4. **One look.** Every held-out and untriaged run happens once, in Phase 4, after the
   freeze. Nothing in `askwell/core/`, `askwell/workspace/` or `prompt.py` changes after
   the first such result, except logged bug fixes followed by full re-runs, and the
   switch settings the gate (below) prescribes.
5. **Predictions first.** ADR-008 is committed with the predictions and the gate below
   and an empty Result before the first commit that touches `askwell/core/`,
   `askwell/workspace/` or `askwell/pipeline/`.

## Phase 0b — measurement setup (builder, then orchestrator)
Runs after this plan is approved and before any product code.
1. **Builder:** the writer brief draft; `scripts/check_holdout.py` (run twice, tie rule,
   6-word overlap, duplicate gold SQL), tests first, on synthetic items;
   `evals/gold/spider_selection_v03.py`, tests first; a `tie_rule` field is not added to
   the item schema (the check derives ties from the gold result itself).
2. **Orchestrator:** reviews and hash-commits the brief; runs the writer; runs the checks;
   commits the held-out hash, the Spider IDs and ADR-008 (predictions, gate, empty Result).

**Exit:** the brief hash, held-out hash, `spider_ids_v03.json` and ADR-008 are committed
before the first commit touching `askwell/core/`, `askwell/workspace/` or
`askwell/pipeline/` (`git log`).

## PR-1 — stable answers

### Phase 1 (builder)
1. **A declared label field.** `EntityDef` gains `label: str | None`, a field slug, "the
   name of the thing". Grouping by an entity's label field groups by the entity's key and
   the label, and returns the key as a column (`<entity>_id`) just before the label.
   Grouping by any other field (`region`, `city`, `job_type`) is unchanged: it groups by
   the value.
   - **fieldservice:** `customers.name`, `technicians.full_name`, `parts.name`, and the
     equivalent field on any other entity that has one (the builder lists them in the
     registry diff).
   - **`registry init` (Spider):** a label is inferred only when an entity with a
     single-column key has exactly one column named `name`, `<entity>_name`, `full_name`
     or `title`. Otherwise none, which keeps today's behaviour.
   - **Uploads:** the draft infers a label by the same rule. Confirm shows it per table
     ("Name column: `name`"), and the person can change it to another text column or to
     "none". None keeps today's behaviour. Saved with the other Confirm edits.
   - **Known limit:** a question about the name text itself ("which customer name is most
     common") now gets one row per customer. Rare, and the answer shows the ids, so it is
     visible. Stated in the ADR.
   - **The prompt does not change.** The label is used by the SQL builder only; a test
     checks the fieldservice prompt text is byte-identical to `interpret-v2`'s, so every
     recording stays valid.
2. **A defined order inside ties.** After the intent's own `order_by`, the SQL orders by
   every group-by column ascending (the key first, for a label), and a row list by the
   base entity's key. The same intent then gives the same rows in the same order on both
   engines and on every run.
3. **Say when a top-N cuts a tie.** When an intent has `limit` and `order_by`, the query
   fetches one extra row. If it ties with the last row on every ordering target, the
   answer carries `tied_at_cutoff: true`. Numbers tie when they differ by at most the
   scorer's tolerance (1e-6), so a float sum that differs in its last bits between
   Postgres and SQLite still counts as a tie. The extra row is never shown. The trace
   view and the Ask page say "More rows tie with the last one shown."
4. **No switch.** Label grouping and tie order turn no refusal into an answer; they only
   change how an answer is grouped and ordered, so they are not behind a feature switch.
5. **Tests first:**
   - oracle intents on both engines with hand-written references: two customers with the
     same name give two rows; grouping by `region` still gives one row per region; ties
     come back in the same order on both engines; a top-N with and without a cutoff tie,
     including a float-sum tie;
   - registry tests for label inference (each name form; two candidates gives none; a
     composite key gives none);
   - Confirm: the inferred label is shown, can be changed and cleared, and is saved;
   - the replay eval reproduces a re-scored fieldservice replay report with no live call.

**Pass/fail:**
- **P1.1** The "Garcia Ltd" test gives two rows, and the `region` test one row per
  region, on both engines.
- **P1.2** Every grouped or ordered oracle intent returns identical rows, in identical
  order, on Postgres and SQLite.
- **P1.3** `tied_at_cutoff` is true for each seeded cutoff tie (integer and float) and
  false otherwise; the extra row never appears in `rows`.
- **P1.4** Replaying the v0.2 held-out and the fieldservice seen recordings under PR-1
  code (no live call): ho-020 and ho-024 right in 3 of 3, and no item that was right
  becomes wrong. Reported as a seen check only.
- **P1.5** The fieldservice prompt is byte-identical to `interpret-v2`'s.
- **P1.6** Branch coverage on `sqlbuild.py` and `validate.py` at or above 95%;
  `./verify.sh` green.

## PR-2 — uncurated schemas

### Phase 2 (builder)
1. **Name a link (switch: `link_roles`).** When two or more links join the same pair of
   entities, each gets a role from its column (for example `source_airport`,
   `dest_airport`). A field reference can name the role (exact syntax in the ADR, chosen
   by the builder and tested). The `ambiguous_path` error lists the roles, so the retry
   can pick one. The prompt and the registry view show roles. An unnamed reference across
   an ambiguous pair is still refused, never guessed.
2. **Infer more links in `registry init` (switch: `inferred_links`).** Only for a column
   without a declared key. A link to table T needs all of these:
   - **a name match:** the column's name is T's key name, T's name or singular, or
     `<role>_<T>_id` / `<role>_<T singular>_id`. When several tables match, the longest
     table name wins; if two still match, no link and a warning;
   - **containment:** every non-null value is a value of T's key;
   - **enough evidence:** at least 10 distinct non-null values, and at least 2 rows,
     so an all-null or near-empty column never links. Containment alone is not taken as
     proof: small integer keys contain each other (the review found every `student_id`
     value inside `Addresses.address_id` in one untriaged database), which is why the
     name match is required first;
   - **one reading:** if the name parses two ways (`sales_order_id` as `sales_order` or
     `order` with role `sales`), the full-name table wins when it exists; otherwise the
     role form; never both;
   - **no self-links:** `parent_category_id` on `categories` is not inferred. A
     self-join needs two aliases of one entity, which the path search
     (`validate.py`, paths keyed by entity) does not model. Out of scope, stated in the
     ADR.
3. **Infer more links on the CSV path (same switch).** `check.py` adds the same name
   forms (`<role>_<table>_id`, plurals `-s`, `-es`, `-y`→`-ies`, longest match) and the
   same evidence rules. A link found only by a new rule, with values missing from the
   target, is dropped with a warning, never turned into a blocking error, so a file that
   loads today still loads.
4. **Numbers stored as text (switch: `numeric_text`; `registry init` only, the CSV path
   already types by values).** A TEXT column is typed numeric when every value that is
   not a placeholder parses as a number. Placeholders are blank, `null`, `NULL`, `N/A`,
   `NA` and `-` (trimmed). In SQL the column is read through
   `CAST(CASE WHEN TRIM(x) IN (<placeholders>) OR TRIM(x) = '' THEN NULL ELSE x END AS
   <numeric>)`, so a placeholder is NULL on both engines (SQLite would otherwise cast
   `'null'` to 0 without an error). A column stays text when any value has a leading zero
   (`'01234'`), or its name ends in `id`, `code`, `zip`, `postal` or `phone`.
5. **The CSV-path eval system,** `askwell_csv`: exports each Spider database's tables to
   CSV files in the gitignored `data/` folder, runs them through the workspace check,
   load and draft as they are (the inferred label accepted as drafted), and asks through
   the workspace pipeline with the pinned reference time. It scores every question; a
   question on a table that failed the check counts as refused, and the report lists each
   load failure with its reason (D3).
6. **Feature switches.** One setting, `ASKWELL_FEATURES_OFF` (a comma-separated list of
   switch names, default empty), read by the validator, the registry builders and the
   prompt. Off means the validator refuses as today and the prompt does not describe the
   feature. Tests show each switch off restores today's refusal.
7. **Tests first:** synthetic fixtures for each rule (two links with roles; each name
   form, with and without containment, below and above the evidence floor, two
   candidates, two readings, a self-link; a numeric TEXT column with placeholders; a
   leading-zero column and an `_id`-named column that stay text; SQLite and Postgres give
   NULL for a placeholder); the CSV path on the same fixtures; the Spider registries for
   the five seen databases regenerated, with their hashes updated and the reason
   recorded.

### The link-role gate (orchestrator, live, before PR-2 is marked ready)
Link roles let the model pick origin or destination, so a refusal can become a wrong
answer, and the hand-written intents of P2.1 do not test that choice. Only one of the four
untriaged databases has a pair of links to the same table, so Phase 4 alone cannot
measure it.
- **Run `v03-roles-seen`:** the 36 seen Spider questions refused for two links, Askwell
  only, PR-2 code, 3 trials (108 calls, about $0.04). Seen, and labelled so.
- **Gate:** per-trial wrong among answered at most 5%, and no question wrong in more than
  1 of its 3 trials. If it fails, `link_roles` ships switched off in the deploy settings,
  the result is logged, and PR-2 still merges (off restores today's refusals).
- A prompt change after this run means the run is repeated before the PR is ready.

**Pass/fail:**
- **P2.1** For each of the 62 seen Spider refusals caused by two links, missed links or
  numbers as text, a hand-written intent (from the seen gold SQL) validates and returns
  the gold rows. Expressibility only, not accuracy. Target: at least 55 of 62.
- **P2.2** No inferred link on the five seen Spider databases fails containment or the
  evidence floor (test).
- **P2.3** Every seeded CSV fixture that loads on main still loads, with the same tables,
  types and links.
- **P2.4** `askwell_csv` runs end to end on a fixture in replay mode, and a fixture with
  a failing table scores its questions as refused.
- **P2.5** Each switch off restores today's refusal (test).
- **P2.6** The link-role gate is run and its result recorded.
- **P2.7** `./verify.sh` green; coverage floors held.

## PR-3 — grammar v0.3 and the measurement

### Phase 3 (builder)
1. **Computed values (switch: `computed`).** A metric field or a selected field can be
   `{op: multiply | subtract | add, left, right}` over two numeric fields on the base
   entity or along a many-to-one path. Fan-out rules apply to both fields.
2. **Durations (switch: `durations`).** `{days_between: [start, end]}`, where `end` may be
   `now` (the reference time). Fractional days, the same on Postgres and SQLite. Usable
   wherever a numeric field is.
3. **Has / has none (switch: `has`).** A filter `{has: <one-to-many link>, where: [...],
   none: bool}`, compiled as `EXISTS` / `NOT EXISTS`. Its conditions follow every filter
   rule.
4. **Compare with an aggregate, restricted (switch: `vs_aggregate`).** A filter
   `{field, op, value: {of: avg | min | max}}` on a numeric field of the base entity
   compares each row with that aggregate of the same field, computed over the same rows
   the question already selects: the intent's own filters and date range, on the base
   entity, without joins, grouping or a limit. "Above this year's average" in a question
   about this year then uses this year's average. A question whose comparison set differs
   from its own rows ("this year's jobs longer than last year's average") cannot be
   written, so it is refused. Only in `summary` and `row_list` intents; `grouped_summary`
   is refused (the aggregate per group is a different question).
5. **Prompt `interpret-v3`:** describes each feature that is switched on, with made-up
   entities; adds two general rules: never add a filter the question does not state, and
   a named span of whole months uses explicit start and end dates. Keeps refuse-first and
   lists what is still out (set operations, comparison with the top row's value,
   distinct counts of periods, window functions).
6. **Tests first:** a named test per new validator code; oracle intents per feature on
   both engines with hand-written references (a zero-row "has none", a duration to
   `now`, a product across a join, an aggregate comparison under a filter and a date
   range); the sentinel property covers every new value slot; each switch off restores
   today's refusal; the no-tuning test covers `holdout-v03` once it is in the repo.
7. **Re-record (orchestrator, live):** the canned demo questions and the fieldservice
   replay recordings under `interpret-v3`.

**Pass/fail:**
- **P3.1** For each of the 9 seen v0.2 held-out refusals in scope (all but ho-017) and the
  13 seen Spider "has none" and aggregate-comparison refusals, a hand-written intent
  validates and returns the gold rows (expressibility, not accuracy). Target: all 22;
  any that the restriction in item 4 rules out is listed with the reason.
- **P3.2** Every oracle intent matches its reference on both engines.
- **P3.3** No value in SQL text; every value bound (sentinel property).
- **P3.4** Coverage at or above 95% on `validate.py` and `sqlbuild.py`; `verify.sh` green.
- **P3.5** Every canned demo question answers under `interpret-v3`.

**Checkpoint review** after Phase 3, before any held-out run: `/code-review` on the core
diff (the SQL builder is the security-relevant code), run by the orchestrator.

### Phase 4: the measurement and the gate (orchestrator)
1. Move `holdout-v03.jsonl` into `evals/gold/`; the manifest test checks it against the
   pending hash. Fetch the untriaged Spider databases and generate their registries.
2. Runs, all on `anthropic:claude-haiku-5-5`, record mode, every switch on:

   | Run | Questions | Systems | Code | Trials |
   |---|---|---|---|---|
   | `v03-holdout-before` | v0.3 held-out (120) | askwell, oneshot | main at `4014aa0` | 3 |
   | `v03-holdout` | v0.3 held-out (120) | askwell, oneshot | v0.3 | 3 |
   | `v03-seen` | fieldservice seen (67) | askwell | v0.3 | 3 |
   | `v03-seen-holdout-v02` | v0.2 held-out, seen (40) | askwell | v0.3 | 3 |
   | `v03-spider-new-before` | untriaged Spider (200) | askwell, oneshot | `4014aa0` | 1 |
   | `v03-spider-new` | untriaged Spider (200) | askwell | v0.3 | 1 |
   | `v03-csv-new-before` | untriaged Spider as CSV (200) | askwell_csv | `4014aa0` + only the CSV eval system | 1 |
   | `v03-csv-new` | untriaged Spider as CSV (200) | askwell_csv | v0.3 | 1 |
   | `v03-spider-seen` | old Spider, seen (250) | askwell | v0.3 | 1 |

   "Before" code is branch `v03-before`: `4014aa0` plus only the eval-side additions it
   needs (the gold and Spider ID files it reads, the `askwell_csv` system). Never merged.
3. **The gate (D5).** v0.3 deploys only if its per-trial wrong rate on the v0.3 held-out
   is no higher than `v03-holdout-before`'s (v0.2 code on the same questions), and, per
   untriaged Spider database and for the CSV path, its wrong rate rises by no more than 5
   points. If a gate fails:
   - every switch whose feature appears in a wrong answer of the failing run is turned
     off (triage names the feature for each wrong answer);
   - the failing run is repeated once with those switches off, as `<run>-gated`, and
     reported beside the first; the gate is read on the repeat;
   - if it still fails, nothing deploys and the orchestrator brings the result to
     Cristian. No code changes in between.
   The deploy settings ship with the switches the gate leaves on.
4. Triage every Askwell miss in every run. Held-out notes may quote the questions; Spider
   notes cite IDs only.
5. ADR-008's Result, the README results table (seen, held-out and untriaged labelled),
   the floors file, `docs/failures/` and the build log are written from the reports.

**Exit:** every run's report committed, spend shown in each and summed in the build log,
the gate's outcome recorded, `./verify.sh` green.

### How results are reported
- **Accuracy:** question-level (right in at least 2 of 3 trials), with a Wilson interval
  on distinct questions; pooled trial counts beside it, for comparison with v0.2.
- **Wrong answers:** per trial, wrong among answered, with its interval; never the 2-of-3
  rule.
- **Before and after:** a paired McNemar test (exact binomial on the discordant
  questions) on question-level right or not, v0.2 code against v0.3 code on the same
  held-out questions. The same test for the one-shot baseline is not needed: it does not
  change.
- **Spider and the CSV path:** per database. No pooled Spider headline: four schemas are
  not 200 independent samples. A pooled line, if shown, is labelled as such.
- **The tie rule's cost:** drafts dropped or reworded, and check rejections (Held-out
  honesty, 2).
- These are report additions that apply to every system and every run alike.

## Predictions (for ADR-008, committed before the first core commit)
Predictions are not acceptance; the gate in Phase 4 is.
1. **v0.3 held-out, accuracy:** question-level at least 70%; expected 70–82%. The 80%
   target is the goal; this plan does not predict it is met.
2. **v0.3 held-out, wrong among answered:** per trial at most 8%; expected 3–8%.
3. **Before and after:** v0.3 is right on at least 10 points more of the questions than
   main at `4014aa0`, and McNemar's p < 0.05; its per-trial wrong rate is lower.
4. **Refusals:** refusal recall at least 23 of 24 per trial on the v0.3 held-out.
5. **Seen v0.2 held-out:** at least 63 of 84 right (from 40; ho-017 stays refused), wrong
   at most 4 of answered per trial. Seen, so it shows the fixes work where they were
   aimed, nothing more.
6. **Seen fieldservice:** stays at or above 81.4% right and at or below 5% wrong (L11).
7. **Link roles, seen:** the gate run passes (at most 5% wrong among answered).
8. **Untriaged Spider (`registry init`):** false refusals fall in at least 3 of the 4
   databases; in none does the wrong rate rise by more than 5 points.
9. **Untriaged Spider as CSV:** small movement, because many columns match no link rule
   (`Code`, `CountryCode`, `Channel`): false refusals fall by at least 3 points in at
   least 2 of the 4 databases, scored on all 200 questions; the load failures are listed.
10. **Unreadable answers** at most 2% of calls in every run; **cost per question** up at
    most 35% from v0.2's $0.000480, because the prompt grows.

## Spend
- **Model:** `anthropic:claude-haiku-5-5`, list price, as in v0.2.
- **Estimate**, from v0.2's measured cost per call ($0.00047 on fieldservice, $0.00031 on
  Spider) plus 15% for the longer prompt and retries:

  | Item | Calls | Cost |
  |---|---|---|
  | Link-role gate run (36 × 3) | 108 | $0.04 |
  | Held-out before and after (120 × 3 × 2 systems × 2) | 1,440 | $0.75 |
  | Seen fieldservice and seen v0.2 held-out (107 × 3) | 321 | $0.17 |
  | Untriaged Spider before (×2 systems) and after | 600 | $0.21 |
  | Untriaged Spider as CSV, before and after | 400 | $0.14 |
  | Old Spider, seen | 250 | $0.09 |
  | Demo and replay re-records (PR-2 and PR-3) | ~280 | $0.14 |
  | **Expected total** | **~3,400** | **~$1.55** |
  | A gated repeat of the held-out run, if needed (120 × 3 × 2) | 720 | $0.40 |

- **Cap: $4** for every live call in v0.3, enforced by the budget guard (`--budget` per
  run, summed in the build log). The margin covers a gated repeat and one full re-run
  after a logged bug fix. If a run stops at the cap, its partial report is committed as
  partial and the orchestrator asks before spending more.
- Every live call is the orchestrator's, after its go. Builders make none.
- Not counted: the writer's model run (an agent run, not an API call through the budget
  guard).

## PR shape: three PRs
- **PR-1, stable answers:** Phase 0b's committed artifacts and Phase 1. It changes the SQL
  and the registry, not the prompt, so every recording stays valid.
- **PR-2, uncurated schemas:** Phase 2, the feature switches and the link-role gate. It
  changes the registry, the CSV checker and the prompt, so it carries its own small
  re-record.
- **PR-3, grammar v0.3 and the measurement:** Phase 3 and Phase 4. The prompt changes
  again, and the held-out runs must measure the final code.

Why three: each leaves main working and safe on its own; PR-1 is a small correctness fix
whatever happens to the rest; PR-2 and PR-3 each change `sqlbuild.py`/`validate.py`, the
security-relevant code, and a separate review slice keeps each diff reviewable. Why not
more: the measurement must follow the last code change, so it stays in PR-3. Why
sequential: PR-2 and PR-3 both touch `validate.py`, `sqlbuild.py` and `prompt.py`. One
worktree (this one), each next branch cut from main after the previous merge.

## What touches the deployed beta
Nothing deploys until the Phase 4 gate (D5). PR-1 and PR-2 merge to main and wait.
Then the one deploy carries:
- grouped answers by a thing (customer, technician, part) gain its id column; top-N
  answers can say a tie was cut;
- Confirm shows each upload's name column, which the person can change or clear;
- uploaded CSV files with `<role>_<table>_id` columns get links they did not have; a file
  that loaded before still loads (P2.3);
- the new intent shapes, on the deployed SQLite engine (every oracle test runs on both
  engines), and a new prompt version; the demo answers are re-recorded in PR-3;
- one new setting, `ASKWELL_FEATURES_OFF`, set to whatever the gate leaves off. No
  database change.
- Cost per question rises (prediction 10); the daily cap is unchanged.

## Open choices
Decided by the orchestrator (see Decisions). The recommendations that now stand:
- **S1, scorer:** no change. A later change would need its own ADR, apply to every
  system and re-score the baseline.
- **O3, feature quotas:** none, with an entity spread and a difficulty mix like the seen
  set's.
- **O4, question-level intervals:** added to every report, used for the accuracy
  headline; per-trial for the wrong rate.
- **O5, cutoff ties:** say so in the answer, not `WITH TIES` (no SQLite form; a top-5 of
  6 rows surprises readers).
- **O7, untriaged Spider databases:** all four with at least 50 questions; no draw.
- **O9, attribution:** one look at the end; no held-out run per PR.
- **O10, held-out writer:** a separate model run started by the orchestrator, from the
  hash-committed brief, in a clean directory.

## Needs Cristian
- **The deploy hold (D5):** the beta stays on v0.2 until the Phase 4 gate, likely across
  all three PRs.
- **A new setting** (`ASKWELL_FEATURES_OFF`) and a Confirm-page change (the name column);
  the v0.2 plan's "no new settings" does not hold here.

## Out of scope
- Set operations, comparison with the top row's value, distinct counts of periods,
  window functions, distinct row lists, self-links.
- Showing hidden email and phone fields on Spider (a product choice, kept).
- Any change to the seen gold sets, including fs-022 and fs-024's open gold issues and
  the flight_2 trailing-space golds.
- The model choice (ADR-004) and the default model; the sql_agent baseline.
- The value calculator, except pointing its report constant at the v0.3 reports if
  Cristian asks.
- The Atlas deploy.

## How this was run
- This worktree's own Postgres: `ASKWELL_DB_PORT=56452 docker compose up -d` (56432 is
  held by another worktree's container), with `ASKWELL_DATABASE_URL`,
  `ASKWELL_DATABASE_RO_URL` and `ASKWELL_APP_DATABASE_URL` pointed at port 56452 in the
  environment. `.env` was not read or changed. `./verify.sh` passed on `4014aa0` this way.
- Spider dev was fetched into this worktree's gitignored `data/` for the diagnosis, then
  deleted (Held-out honesty, 3).
- No live model call was made.
