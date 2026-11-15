# v0.3 build log

## Phase 1 — stable answers (PR-1)

**What changed**
- `EntityDef.label`: the field that names a row. fieldservice declares it for
  customers, parts and sites (`name`) and technicians and users (`full_name`).
  `registry init` infers it from exactly one visible text column called `name`,
  `full_name`, `title` or `<entity>_name`, beside a single-field key. Uploads get the
  inferred one, and Confirm lets the person change it or set it to none.
- Grouping by a label groups by the entity's key as well and returns the key just
  before the label. Grouping by anything else is unchanged.
- After the intent's own ORDER BY, every group column (key first) or a row list's key,
  ascending, NULLs last.
- A top-N with an ORDER BY fetches one extra row; if it ties with the last on every
  ORDER BY value (numbers within 1e-6), the answer carries `tied_at_cutoff: true` and
  the Ask page says "More rows tie with the last one shown." The extra row, and any
  column added only to compare a row list's ORDER BY field, are dropped before the
  answer is returned or audited. The SQL shown is the SQL that ran, so it reads
  `LIMIT n+1`.

**Spider registry hashes.** `evals/spider_registries.json` changed for dog_kennels and
network_1 only, because `registry init` now writes the labels it infers there
(`breeds.breed_name`, `dogs.name`, `highschooler.name`). A registry without a label
dumps byte for byte as before, so car_1, flight_2 and wta_1 keep their hashes. The
prompt text does not include labels, so no recording key changes.

**P1.4, replay of the recordings under PR-1 code (seen; no model call).**

| Set | Before PR-1 | After PR-1 |
|---|---|---|
| v0.2 held-out (84 in_schema trials) | 40 right, 14 wrong, 30 refused | 52 right, 2 wrong, 30 refused |
| fieldservice seen (129 in_schema trials) | 111 right | 111 right |

- ho-020 and ho-024 are right in 3 of 3 trials: the answer now carries the id the gold
  asks for. These are the 6 the plan counts.
- ho-022 and ho-028 also turn right in 3 of 3, but only because the new tie order
  (group key ascending) happens to equal the gold's tie-break (city name; technician id).
  The plan does not count them as fixes.
- The 2 left are ho-010's misreads. No item that was right became wrong.

**Existing test changed** (its own commit): four reference queries in
`tests/core/oracle_cases.py` (o06, o12, o14, o16) group by a part, technician or
customer and now group by its id as well and return it.

**detect-secrets.** `evals/gold/spider_ids_v03.json` line 4 is the SHA-256 of Spider's
`dev.json`, the same value `spider_ids.json` already carries; it is added to
`.secrets.baseline` as not a secret, as that one is. Without it `./verify.sh` failed at
the gold freeze commit `37f85d7`.

**How it was run.** This worktree's Postgres on port 56452 (another worktree holds
56432), with the three `ASKWELL_*DATABASE*_URL` settings pointed at it in the
environment. `./verify.sh` green: 1,166 pytest, 29 Playwright; branch coverage
`validate.py` 99.4%, `sqlbuild.py` 96.8%, `executor.py` 90.0%.

## Phase 2 — uncurated schemas (PR-2)

**Feature switches.** `askwell/core/features.py` names three: `link_roles`,
`inferred_links`, `numeric_text`. `ASKWELL_FEATURES_OFF` (comma-separated) turns them
off; an unknown name fails at startup. Settings hand the set that is on to the
validator, the prompt, `registry init`, the upload check and draft, the CLI and the
eval runner; no other code reads the environment.

**Named links (`link_roles`).** A field across one of two links between the same tables
is written `entity@link.field`, where `link` is the linking field of the many-to-one
relationship (`airports@sourceairport.city`). Each named link is its own join, labelled
`entity_link__field`. An unnamed field across two links is still `ambiguous_path`, and
its message now lists the named forms; a link that does not lead into the entity, or
that names a way into the base entity, is the new code `unknown_link` (plain text on the
Ask page: the ambiguous-path message). Off, `@` is not read, so the reference is an
unknown entity, and the ambiguous-path message is byte for byte today's.

**Inferred links (`inferred_links`).**
- `registry init` keeps a declared key to a single-column unique column (car_1's
  `car_names.model -> model_list.model`).
- A column named after a table, `<table>`, its singular, or `<role>_<table>_id`
  (`flights.airline -> airlines`), links only on evidence: at least 10 distinct values,
  every one a key of the target. The longest table name wins; two of one length give
  none. A table never links to itself by name. The older forms (`<x>_id`, a column
  named like another table's key) are kept without a data check, so switching the
  feature off restores today's links exactly.
- The upload check adds `<role>_<x>_id` and the singulars the `<x>_id` rule misses
  (`company_id -> companies`), on the same evidence. A column that fails stays a plain
  column, never an error; the sample files load with the same tables, types and links
  (P2.3).

**Numbers stored as text (`numeric_text`).** A text column whose every value reads as a
number, after trimming and skipping the placeholders `''`, `null`, `NULL`, `Null`,
`N/A`, `n/a`, `NA`, `na` and `-`, is drafted as a number with `text_number: true`. The
builder reads it as `CAST(CASE WHEN TRIM(x) IN (placeholders) THEN NULL ELSE x END AS
FLOAT)`, with every placeholder a bound value; SQLite and Postgres give the same rows. A
leading zero, or a name ending in id, code, zip, postal or phone, keeps a column text.
So does a column with at most `CODE_MAX` (5) distinct numbers: those are codes, such as
dog_kennels' 0/1 `gender` and `abandoned_yn`, and stay categorical text with their value
list, so the model still sees the values it may filter on. Five covers flags and small
code sets; dog ages (8 distinct) stay numbers that can be averaged. car_1's `mpg` and
`horsepower` (130 and 94 distinct) are unaffected, and P2.1 is unchanged. With the switch off at ask time, such a field is read as the text it is. A column whose
stored bytes are not UTF-8 (wta_1's `players.first_name`) is text.

**Prompt version stays `interpret-v2`.** The plan expected a re-record for PR-2. The
prompt's wording is unchanged; the one new section, "Named links", is written only for
a schema with two links between the same tables. The fieldservice prompt is byte for
byte the same with every switch on or off (test), so its recordings and the demo's
stay valid. The Spider prompts do change, through their registries:

| Database | Registry change | Prompt change |
|---|---|---|
| car_1 | `cars_data.mpg`, `horsepower` numbers; `car_names.model -> model_list.model` | yes |
| dog_kennels | `dogs.age`, `weight` numbers | yes |
| flight_2 | `flights.airline -> airlines.uid` | yes, and named links |
| network_1 | none | named links |
| wta_1 | none | named links |

`evals/spider_registries.json` is regenerated for car_1, dog_kennels and flight_2 (the
other two hashes are unchanged). Every recorded Spider answer for these five databases
now misses in replay; the Phase 4 seen Spider run is live anyway. The one replay test
on a Spider database, `tests/pipeline/test_api_replay.py::
test_registry_init_then_ask_on_a_spider_db`, was re-recorded live (one ask, two
attempts, $0.0007) and passes unchanged.

**P2.1, hand-written intents for the 62 seen refusals: 42 of 62 return the gold rows;
the target was 55.** `tests/bench/test_expressible_v03.py` holds each intent (values as
`$n`, read from the gold SQL at test time).
- 54 can be written. 8 cannot: triaged as two links, their golds also need rows with no
  related row (spider:258, 894, 896, 897, 917, the "has none" of PR-3) or a set
  intersection (spider:451, 898, 900, out of scope).
- 12 of the 54 return answers that differ from the gold for a reason in the gold:
  - 9 numbers-as-text items in car_1 (spider:95, 96, 117, 126, 132, 135, 136, 165, 170):
    the gold computes on the text. `avg` counts 'null' as 0, `max` returns 'null', and
    comparisons and ORDER BY compare characters, so '150' sorts before '46'. No numeric answer
    can match these golds.
  - spider:152: the gold's inner join drops a model whose maker is missing; the
    intent's left join keeps it when its weight qualifies.
  - spider:229, 230: every airline has 100 flights; the gold's top-1 is an arbitrary
    pick among the tie.
- flight_2 stores airport codes in `flights` with a leading space and cities with a
  trailing one, so every gold and every answer on those joins is zero rows. The test
  runs flight_2 on a copy with the spaces trimmed, so its matches compare real rows.
- P2.2: every new inferred link on the five seen databases holds its evidence (test);
  the only one is flight_2's `airline`.

**The CSV path, `askwell_csv`.** `askwell/bench/csv_path.py` exports each table to
`data/csv/<schema>/files/`, then runs the functions the workspace store runs (check,
load, draft, confirm as drafted). A file that fails is dropped and the rest are checked
again; a question whose gold reads a dropped table is refused without a model call, and
the report lists each dropped table with its problem codes. A fixture runs end to end in
replay mode, with a failing table scored as refused (P2.4). On the seen databases, in
export mode (no call), most tables fail the upload check's ID-column rule:

| Database | Questions sent / refused | Dropped tables |
|---|---|---|
| car_1 | 15 / 35 | continents, countries, model_list, car_names: `no_id_column` |
| dog_kennels | 44 / 6 | breeds, treatment_types: `no_id_column` |
| flight_2 | 0 / 50 | airlines, airports, flights: `no_id_column` |
| network_1 | 19 / 31 | friend: `duplicate_id`; likes: `no_id_column` |
| wta_1 | 0 / 50 | matches: `no_id_column`; players: `not_utf8`; rankings: `file_too_large` |

So the Phase 4 CSV numbers will mostly measure that rule, not links or numbers.

**`--items` on `askwell eval`.** The link-role gate needs 3 trials on chosen Spider
items, and a Spider run is one trial (ADR-006). `--items <file>` runs only the IDs in the
file, each for every trial asked, Spider included; an ID no given schema has stops the
run before any call. `evals/v03_roles_seen.json` lists the gate's 26 (IDs only).

**Link-role gate, `v03-roles-seen`: failed; `link_roles` ships off.** Read on 26 of the
plan's 36 questions, network_1's 24 and wta_1's 2. flight_2's 10 are left out, decided
before the run: its airport codes carry a leading space, so either link returns zero
rows, matching the gold's zero rows, and a wrong link cannot show. Run:
```
uv run askwell eval --schema spider_network_1 --schema spider_wta_1 --systems ledgerline --mode record --models anthropic:claude-haiku-5-5 --trials 3 --items evals/v03_roles_seen.json --budget 0.10 --run-id v03-roles-seen
```
78 calls, $0.0427. Report: `evals/reports/v03-roles-seen.md`.

| Trial | Right | Wrong | Refused | Wrong among answered |
|---|---|---|---|---|
| 1 | 18 | 1 | 7 | 1 of 19 (5.3%) |
| 2 | 18 | 1 | 7 | 1 of 19 (5.3%) |
| 3 | 18 | 0 | 8 | 0 of 18 |

- Both bars fail: two trials are above 5%, and spider:906 is wrong in 2 of 3.
- spider:906 asks who "has the greatest number of likes". In trials 1 and 2 the model
  grouped by `highschooler@liked_id` (likes received); the gold groups by `student_id`
  (likes given). Its rephrasing, spider:907, was right in all three. Every student in
  `likes` gives exactly one like, so the gold's top row is also an arbitrary pick from a
  tie; a right answer there matches by the tie order.
- Refused: the 6 questions that need "has none" or a set intersection (spider:894, 896,
  897, 898, 900, 917) every time, and spider:910, 911 and 451 sometimes.
- As the plan says: `compose.prod.yaml` sets `ASKWELL_FEATURES_OFF=link_roles` (tested),
  the result is in ADR-008, and PR-2 still merges. Off, these questions are refused as
  before.

**Existing tests changed**, each in its own commit:
- 67f984c: the f5 fixture in `tests/core/test_pr1_review.py` drops `UNIQUE` from
  `countries.code`, so its declared key is still skipped; no assertion changed.
- 614b4d6: the numeric-text fixture gains rows so `mpg` and `horsepower` exceed
  `CODE_MAX`; the avg, sum, count and filter expectations follow the larger data.
- 946cf72: the CSV fixture's `orders.amount` gains three values; no assertion changed.
- d4e4fcb: the gate-list test expects 26 network_1 and wta_1 items, not 36.

**Review a13dba fixes (8 MEDIUM).**
- f1: a link drawn only because `inferred_links` is on carries `feature: inferred_links`
  in the registry (the new name forms, a declared key to a unique column, and upload
  links adopted by name and evidence). With the switch off the validator and the prompt
  leave it out, so an existing registry behaves as one drafted with the switch off.
  Older inferred links carry no mark. The car_1 and flight_2 hashes change for the mark
  alone; prompts do not show it, so no recording key changes.
- f2: upload containment compares the cells exactly as the loader converts them, so a
  padded `' 1'` never adopts a link that would then fail to load.
- f3: a label key reached by a named link carries that link, so grouping by both ends
  of two links keeps two key columns.
- f4: numbers-as-text detection trims spaces only, as SQL `TRIM()` does on both
  engines; a value padded with a tab or a newline keeps the column text.
- f5: only ASCII digits read as numbers.
- f6: containment leaves NULL target keys out of its `NOT IN`.
- f7: a column whose stored type differs from the target key's (text against integer)
  is never linked, and a containment query that cannot run counts as no evidence
  instead of stopping `registry init` (tested on Postgres).
- f8: an eval run carries every CSV load failure per schema (`RunResult.
  csv_load_failures`), so the report lists tables no scored question reads.

## Phase 3 — grammar v0.3 (PR-3)

**Four switches.** `computed`, `durations`, `has` and `vs_aggregate` join the three of
PR-2 in `askwell/core/features.py`. Off, the validator refuses with `feature_off` and
the prompt lists the feature as out of reach. New refusal codes, each with a named test
and plain text in `askwell/workspace/ask.py`: `feature_off`, `computed_type`,
`duration_type`, `has_link`, `vs_aggregate_scope`.

- **Computed values.** `{op, left, right}` over two numeric fields; its label is its
  alias or a name such as `unit_price_minus_unit_cost`, and an `order_by` can name it.
  It is aggregatable only when both fields are (the fan-out rule applies to each).
- **Durations.** `days_between` is `julianday(end) - julianday(start)` on SQLite and the
  epoch difference over 86400 on Postgres, so fractional days match. `now` is the
  reference time, bound as a value. A duration is always aggregatable: it reads one row.
- **Has / has none.** A correlated `EXISTS` over the named table, reached by a direct
  link, `entity@link` when two point back, or one shortest chain of many-to-one links
  (work orders to sites to customers), which compares base keys. Its `where` follows
  every filter rule, under its own aliases (`h1_…`).
- **Compare with an aggregate.** A scalar subquery over the base table (`t0_agg`) with
  the intent's other filters and date range. Refused as `vs_aggregate_scope` in a
  `grouped_summary`, inside an `any_of` / `all_of` group, on a field off the base, and
  beside a filter on a related entity or a `has`.

**Prompt `interpret-v3`.** `system_prompt(features)` composes the text: each switched-on
feature is described with made-up entities and one example; a switched-off one joins
the out-of-reach list, which always names set operations, comparison with the top row's
value, a distinct count of periods, and window functions. Two general rules are added:
never add a filter the question does not state, and a named span of whole months uses
explicit start and end dates. The Confirm preview and the API send the workspace's
switches (`PromptView.features`).

**Re-recorded live under `interpret-v3` (P3.5: met).** The prompt text and the Intent
JSON schema both changed, so every recording missed. Re-recorded on
`anthropic:claude-haiku-5-5`, cap $0.15:
```
uv run python -m evals.replay_cases record
uv run askwell eval --schema fieldservice --systems ledgerline,oneshot --mode record --models anthropic:claude-haiku-5-5 --trials 1 --budget 0.14 --run-id rerecord-v3-fieldservice
uv run python -m scripts.check_replay_report --write
```
- The canned questions and the Spider init-then-ask case: 10 calls, $0.0051. Every
  canned question answers or refuses as its test expects.
- The fieldservice record run: 134 calls, $0.0669. Report:
  `evals/reports/rerecord-v3-fieldservice.md`. Seen questions, 1 trial: ledgerline 41
  of 43 right, 1 wrong among 42 answered (fs-024, the two-date reading tagged
  gold_issue), fs-037 refused as expected.
- Spend: $0.0720. The replay report reproduces from the new recordings, and
  `./verify.sh` is green.

**O11, no ID column (Cristian, 2026-11-14).** A file with no ID column, other than a
link table, now passes Check with a warning, "No id column found; rows are numbered for
you", and loads with a generated key column `askwell_row` (`askwell_row_2` and so on if
the file already uses the name), numbered from 1. The name starts with a letter because
a field slug must. The drafted registry hides the column, so the prompt never shows it,
and no link is drawn to it. The Prepare page and the README say so.

**P3.1, expressibility: 15 of 22.** Hand-written intents return the gold rows on both
engines (`tests/core/test_expressible_grammar_v03.py`):

| Set | Right | Not expressible |
|---|---|---|
| v0.2 held-out, seen (9) | 8 | ho-014: quantity times (price minus cost) needs three fields; a computed value takes two |
| Spider, seen (13) | 7: 920, 978, 257, 914, 915, 101, 974 | 924, 925: has-none on a sum of related rows. 167, 168: the gold's aggregate is over all rows, not the question's (item 4). 944, 945: the aggregate is of another entity's field (item 4) |

spider:257's gold is rightly empty, and the test allows it.

**P3.2–P3.4.** 11 oracle cases in `tests/core/oracle_cases_v03.py` match their
hand-written references on Postgres and SQLite (a zero-row has-none, a duration to
`now`, a product across a join, an aggregate comparison under a filter and a date
range among them). The sentinel test covers each new value slot, `now` included.
Coverage on the core, workspace and bench suites: `validate.py` 98%, `sqlbuild.py` 98%.

**Report additions** (plan, "How results are reported"). With more than one trial, a
report adds question-level accuracy per schema, system and model: a question is right
when right in most of its trials, with a Wilson interval on distinct questions.
`compare_runs(before, after)` in `askwell/bench/report.py` pairs two runs on the same
questions and gives the exact McNemar p-value. One-trial reports keep their old shape.

**Existing tests changed**, each in its own commit:
- c3defc9: `test_features.py` expects seven features.
- 973196e: the CSV path's all-fail fixture fails on a damaged ID (`bad_value`), since a
  missing ID no longer fails Check.
- b77b893: `test_prompt.py` follows `interpret-v3`; the features now described are
  required in the all-off prompt's out-of-reach list and absent from the all-on one.

**PR-3 review fixes (4 MEDIUM).**
- f1: a `has` filter that names a link (`flights@origin_id`) is refused as
  `feature_off` when `link_roles` is off, and its ambiguous-path refusal then names no
  link. The prompt teaches `entity@link` for `has` only with `link_roles` on. With every
  switch on the prompt is byte for byte the same, so no recording changed; the deployed
  prompt (`link_roles` off) loses that one sentence.
- f2: the two fields of a computed value are cast to a float on both engines. Two
  integer fields made an integer expression, and Postgres compared it with `2.4` as an
  integer (0 rows where 590 were right; tested on both engines).
- f3: a selected computed value's name cannot be a base field's name
  (`alias_collision`) or another column's (`duplicate_alias`); before, an `order_by`
  naming it sorted by the computed column, not the field.
- f4: question-level accuracy counts against the trials each schema planned
  (`RunResult.planned_trials`: every trial on a run of named items, otherwise one for
  Spider), so a missing or pending trial is not right; `compare_runs` does the same.
- Existing test changed in its own commit: c75e9bf, `question_level` takes
  `planned=3`; the expected result is unchanged.
- Fix check, x2: the select-name check collects every output label first, so a
  computed value named `parts__name` clashes with `parts.name` in either order (tested
  both ways).
- Fix check, x1, deferred: a computed value is a float, exact only up to 2^53 (about
  9 × 10^15); business amounts stay far below that.
- Slice 29cc46, f1: an aggregate comparison obeys the registry's aggregatable flag
  (`technicians.id` against its average is `not_aggregatable`), as a metric does.
- Slice 29cc46, f2: a computed value's name cannot be a base field's registered alias
  (`price` on parts, the alias of `unit_price`); refused as `alias_collision`.
- Slice f1b2d4: a floor's written note, cause and next step in `evals/floors.yaml`
  describe the prompt named in its `prompt_version` (`interpret-v2` for both entries).
  A run made with another prompt keeps its computed verdict and gets "with prompt
  interpret-v3" instead. `rerecord-v3-fieldservice` and `replay-fieldservice` were
  regenerated from their recordings and checkpoint, with no model call; only the note
  lines changed.
- Slice d0921d: question-level stats and `compare_runs` count every planned in-schema
  question (`RunResult.planned_items`), so a question whose trials were all deferred or
  never ran counts as not right instead of leaving the denominator.

## Phase 4 — the measurement and the gate

**Setup.**
- Registry hashes for the four untriaged databases under this branch's code: 61129ae.
- `v03-before` (never pushed or merged): main at `4014aa0` plus the `askwell_csv`
  system (PR-2's `csv_path.py` without feature switches, wired into `run.py`), the
  untriaged-Spider items change (bef02b1), the v0.3 gold and ID files, and registry
  hashes for the four databases under that code (8bfd4a6). Its `test_csv_path.py` is
  PR-2's minus the two tests that need numbers-as-text and interpret-v3 recordings.
  The before runs' reports and recordings are committed there (593a895).
- Gold revision 8: `promote()` removed `holdout-v03.jsonl` from `pending` in revision 7
  but never added it to `files`, so it was not hash-checked. Fixed test first (637846c):
  a promoted file joins `files` with its verified hash, and updates and checks keep every
  listed file. Revision 8 (0fe226a) freezes it with the revision-7 hash, 5c4b6fca…7342.
- `python -m askwell.bench.paired <before> <after> [--out <name>]` rebuilds two runs
  from `evals/runs/` and prints the question-level pairing with McNemar's p and each
  run's wrong answers among answered, per trial; `--out` writes `evals/paired/`. No
  model call.

**Runs** (anthropic:claude-haiku-5-5, record mode, every switch on):

| Run | Code | Calls | Spend | Budget |
|---|---|---|---|---|
| v03-holdout-before | v03-before | 720 | $0.3457 | 0.45 |
| v03-spider-new-before | v03-before | 400 | $0.1183 | 0.15 |
| v03-csv-new-before | v03-before | 200 | $0.0513 | 0.10 |
| v03-holdout | accuracy-pr3 | 720 | $0.3998 | 0.45 |
| v03-seen | accuracy-pr3 | 201 | $0.1150 | 0.12 |
| v03-seen-holdout-v02 | accuracy-pr3 | 120 | $0.0747 | 0.10 |
| v03-spider-new | accuracy-pr3 | 200 | $0.0991 | 0.10, then 0.11 |
| v03-csv-new | accuracy-pr3 | 200 | $0.1062 | 0.14 |
| v03-spider-seen | accuracy-pr3 | 250 | $0.1233 | 0.16 |
| v03-spider-new-gated | accuracy-pr3, `has`, `link_roles`, `numeric_text` off | 200 | $0.0925 | 0.12 |
| **Phase 4** | | | **$1.5259** | |

With the $0.0720 re-record, v0.3's live spend is $1.5979 of the $4 cap.
- `v03-spider-new` stopped at its $0.10 cap after 198 of 200: interpret-v3 costs about
  $0.00050 per Spider call against the $0.00036 the plan assumed. The orchestrator
  raised it to $0.11 and the run resumed for the last two; csv-new and spider-seen got
  $0.14 and $0.16 before they ran.
- The first launch of the two Spider before runs passed the `--schema` list as one
  shell word and stopped at argument parsing, before any call.

**Gate: failed on the first read** on tvshow (+10.1 points wrong among answered) and
world_1 (+6.2), and on the CSV path's world_1 (0 of 2 → 4 of 26); the held-out
criterion passes (per trial
4.7%, 4.7%, 3.1% against 7.3%, 7.4%, 7.3%). ADR-008's Result has the full table and
every prediction.

**Triage: which switches the failing runs' wrong answers use.** Each wrong answer's
intent was validated again with each switch off (drafts allowed, as the Spider schemas
are; every intent validates with all switches on). A switch counts as used when the
answer is refused or compiles to different SQL without it.
- v03-spider-new (before → after outcome in brackets): `has` on tvshow 635, 636
  (refused), 637 (wrong), world_1 783 (refused) and student_transcripts 578 (refused,
  with `link_roles`); `numeric_text` on tvshow 613, 615, 616 (right); `link_roles` on
  student_transcripts 583, 584 (refused). No switch: cre 379 (right);
  student_transcripts 531, 533, 534, 535, 536, 541, 579 (wrong), 547, 548 (right);
  world_1 705, 724, 758 (wrong), 740, 741 (right).
- So the rule turns off `has`, `numeric_text` and `link_roles` and repeats the run once
  as `v03-spider-new-gated`.
- v03-csv-new: no wrong answer uses a switch. cre 361; student_transcripts 531, 534,
  535, 536, 541, 579 (wrong before), 547, 548 (right before), 552 (refused); tvshow 615,
  616, 629 (wrong before); world_1 705, 706, 707, 724, refused before because `country`
  and `countrylanguage` failed the upload check (`no_id_column`), now loaded with
  numbered rows (O11). Nothing to turn off, so the CSV world_1 criterion stays failed.
- A first pass of this triage validated without allowing drafts, so every intent was
  refused with and without each switch and none looked used; its conclusion (no
  switch to turn off) was wrong and was corrected before the repeat was decided.

**Held-out misses (v03-holdout; held-out notes may quote the questions).**
- Wrong in at least one trial: h3-065 in 3 of 3, but its answer is the gold's: the
  gold returns 3,649 unordered rows, past the 1,000-row cap, and the scorer cuts it to a
  different 1,000 than Askwell's (all 1,000 of Askwell's values match); refused in every
  trial before. h3-005 in 2 of 3 (a percentage where the question asks a fraction;
  wrong in 3 of 3 before); h3-038 and h3-045 in 1 of 3 (an id without the name the gold
  returns); h3-058 in 1 of 3 (age buckets as columns of one row). h3-065 is the only
  wrong answer that uses a switch (`computed`); the held-out gate passes, so nothing is
  turned off for it. Every held-out miss is tagged in `evals/triage/fieldservice.yaml`.

- Refused in every trial: 31 questions. h3-070 to h3-096 need what the grammar lacks:
  window functions and ranks within groups (h3-077, 080, 081, 084, 085, 086, 089,
  090), medians and percentiles (h3-083, 087, 096), set intersection (h3-092), a
  self-join (h3-093), per-group totals beside each row (h3-070, 095), differences of
  two grouped counts (h3-071, 075), "every site has" (h3-072), first-ever dates per
  entity (h3-074, 088), gaps between consecutive rows (h3-076), matched follow-ups
  (h3-078), pooled comparisons (h3-079, 082), and a computed value of three fields
  (h3-063, as ho-014 in P3.1). h3-091 was cut off at the completion limit in every
  trial. h3-037, h3-050 and h3-060 count per entity keeping the zero rows, which the
  intent cannot do without a fan-out; h3-073 compares with a per-group average, which
  `vs_aggregate` refuses by design; h3-094 needs a per-job sum averaged per technician.
- The record runs on fieldservice added recordings for the same requests, and replay
  reads the newest, so `replay-fieldservice` was rewritten from them
  (`scripts.check_replay_report --write`, no model call): ledgerline 40 of 43 right,
  with fs-022 now wrong in the replayed trial.

**Gated repeat: the gate fails again.** `v03-spider-new-gated` ran with the three
switches off (`ASKWELL_FEATURES_OFF`; the registries are regenerated without them, so
their hashes are not checked against the committed ones). Wrong among answered against
v03-spider-new-before: cre 1 of 47 (+2.1, pass), student_transcripts 10 of 39 (−1.9,
pass), tvshow 0 of 39 (−2.4, pass), world_1 6 of 36 (+8.6, **fail**). world_1's wrong
answers use no switch: 705, 724, 758 were wrong before too; 740 and 741 tie for the most
languages and the gold's single row is one of the tie; 788 is new on the repeat, seven
countries tie for the smallest population and the answer returned all seven
(`gold_issue`, added to `evals/triage/spider_world_1.yaml`). student_transcripts 552
was right in the first run and is wrong on the repeat (its note is updated). Paired:
`evals/paired/v03-spider-new-gated.md`.

The CSV world_1 criterion stays failed on the per-database rule: no switch is involved,
so there is nothing to turn off (2 answered before, because 48 were refused when the
files did not load; 26 answered after, 22 right and 4 wrong). With two criteria failed,
nothing deploys; the result goes to Cristian.

**Plan step 5.** README results table for v0.3 (held-out, seen and untriaged sets
labelled); `evals/floors.yaml` adds `fieldservice-held-out-v03` (gold
`holdout-v03.jsonl`, interpret-v3), and `v03-holdout` was rebuilt in replay mode to show
it; the seen floor stays the v0.2 entry, so v0.3 runs get the note naming their prompt; `docs/failures/` gains a v0.3 section.
The scorer is unchanged: the numeric-text type mismatch is a documented limitation in
ADR-008, with counted-right figures beside the official ones.
