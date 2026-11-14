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
