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
