# Build log: Askwell v0.1

How v0.1 was built, in order: what was decided, what reviews caught, and what changed
because of them. The detailed working notes are in [builds/v01/](../builds/v01/), with the
plan in [plan.md](../builds/v01/plan.md) and per-step notes in
[log.md](../builds/v01/log.md). Each merged pull request (PR) lists its review findings.

A few terms used below:

- **Intent:** the typed form the model fills in instead of writing SQL.
- **Registry:** the file that lists what a database may expose to the model.
- **Gold:** the expected answer to each benchmark question.
- **Review:** a separate model reads the change and reports defects, each with a
  severity (HIGH, MEDIUM, LOW). Every HIGH and MEDIUM gets one round of fixes; what is left
  is written down as deferred.
- **Bounce:** a separate model attacks the plan before any code exists.

## 2026-11-09: the plan, and what its first review changed

The first plan described the system and a benchmark. Its Bounce
([bounce.md](../builds/v01/bounce.md)) found that the build could pass every acceptance
check and still prove nothing: there was no accuracy target, no rule for scoring a result,
and nothing stopped the questions being chosen to suit Askwell.

The plan was rewritten (rev 2) before any code:

- A fixed accuracy target ("floor") for fieldservice: at least 80% of answerable questions
  right, and at most 5% of returned answers wrong.
- Every metric and every comparison rule written down first (how to compare rows, nulls,
  dates and decimals).
- A one-shot baseline (the model writes SQL directly), because that is the comparison a
  sceptical reader asks for.
- A fixed reference date for the seed data, the prompt and the gold, so recordings and
  results reproduce.
- A rule that no test may be skipped: a missing database is a failure, not a pass.

## 2026-11-09: foundations, before any intent code

- **The questions came first.** The fieldservice gold set (67 questions) and the list of
  Spider questions were written and committed before the intent code existed. Spider
  databases were drawn with a fixed random seed, not picked. A hash file and a changelog
  make any later gold change visible.
- **Predictions came first too.** Each design decision got an ADR (decision record) with a
  numeric prediction. ADR-001 predicted that the 80% floor would fail, because 12 of the 43
  answerable fieldservice questions need things the planned intent could not express.
- **The demo database is seeded the same way every time**, and its read-only role cannot
  read the hidden columns (`users.email`, `users.password_hash`) at all. The registry also
  hides them, so they are blocked twice.
- **The intent grammar grew by two things only:** joins up to 3 steps away, and filters
  that compare two columns. Computed values, ratios and "rows with no match" stayed out.
  Those questions stay in the answerable set: a refusal counts as a miss, and an answer to
  a nearby question counts as wrong.

## 2026-11-09: no model key, so answers are simulated

There was no OpenRouter key. Rather than wait, the model step got an export path: each
request is written to a file, a stand-in model (claude-haiku-5-5) answers it as the target
model (`openai/gpt-oss-120b`) would, and the answer is imported with a mark saying who
wrote it. Every result built from those answers says "simulated" on its first line. The
live model test (ADR-004) and the real-cost measurements wait for a key.

## 2026-11-10: PR1, the safe core

The registry, the intent, the validator (one named test per rejection rule), the SQL
builder and the read-only executor with its audit log.

What reviews caught, among others:

- Some true/false filter values were written into the SQL text instead of being sent as
  parameters. Every filter value is now a bound parameter, and the property test that
  checks this now covers every value type.
- Re-running the database role script gave the read-only role back access to the hidden
  columns. The script now re-applies the restriction, and a test runs it twice.
- An OR filter across an optional link dropped rows, because the join was always an inner
  join. A join used only inside an OR group is now a left join.
- A decimal threshold such as "more than 1.5" was rounded on Postgres, and SQLite date
  comparisons dropped microseconds. Both fixed with a failing test first.

Merged 2026-11-10: 7 HIGH findings (3 fixed, 2 deferred, 2 rejected as out of scope), 22
MEDIUM (15 fixed).

## 2026-11-10: PR2, the pipeline and the benchmark

The ask pipeline (interpret, check, one retry, run, show), the HTTP API, the simulation
path and the benchmark.

- **The first simulated run, `sim-1`, found real bugs.** One Spider database stores dates
  as numbers, which crashed the run; such values are now returned as stored. Two dates that
  were equal scored as different (a midnight timestamp against a date); the scoring was
  fixed for every system alike and the report rebuilt from the same recordings.
- **Every miss was given a cause** in `evals/triage/`, and none was left untriaged.
- **Gold questions were not edited after the run**, except one that contradicted the gold's
  own written rules, changed with a reason in the changelog.

What reviews caught:

- Model-written SQL from the baseline could end the read-only transaction. The database
  driver now refuses a second statement, so the baseline cannot leave it.
- Reports could carry Spider data inside refusal text. Spider items are now reported by ID
  and reason code only, and a privacy scan checks every committed report, doc and build
  file.

Merged 2026-11-10 with the fieldservice floor **not met** (76.7% right, 13.2% of answers
wrong), stated as such and not tuned away. Of the 10 misses, 5 were refusals of questions
the intent cannot express. The other 5 were wrong answers: for 3 questions the intent
cannot express (fs-028, fs-035, fs-037), the stand-in model filled in a valid intent for a
nearby question instead of refusing, and 2 were questions that can be read with either of
two dates.

## 2026-11-11: the plan for the product flow

The plan grew a product flow: a stranger prepares CSV files, uploads them, gets a clear
pass or fail, confirms the fields, and asks. Its Bounce
([bounce-p5.md](../builds/v01/bounce-p5.md)) found that Ask could not work without a key,
relative dates used the fixed test date instead of today, and the upload code, the most
security-sensitive part, was bundled with everything else.

Rev 4 split the work into three PRs (your data, results and docs, hosted beta), used the
real clock in each workspace's time zone, dropped three planned extra synthetic databases,
and planned a hosted beta with an invite code and a daily spending cap.

## 2026-11-11: PR3, your data

Workspaces, upload, Check, Confirm and Ask on SQLite, run locally.

- A property test generates valid and messy-but-valid files and proves that everything
  Check accepts loads and reads back exactly.
- Category values (an order's statuses, for example) go to the model only when the person
  ticks a box, because they leave the machine.

What reviews caught:

- Two uploads or Checks at once could lose files or count the same disk space twice. One
  lock per workspace and reserved disk space fixed it.
- A crafted 10,000-digit cell could stall Check. Every pattern now runs in time
  proportional to the cell's length, with a timing test.
- Behind a proxy, a client could get around the per-address limits.
- Stored datetimes lost the year's zero padding on Linux, which failed CI once. They are
  now written with one fixed format.

Merged 2026-11-11. No HIGH findings; 28 MEDIUM (22 fixed). What must close before the beta
goes online is listed in the PR.

## 2026-11-11: PR4, results and docs

- The Results page draws every committed report from its JSON file. The report's shape is
  a committed schema, and a test checks every report against it.
- The ADR results were filled in from `sim-1`. Where nothing could be measured, the ADR
  says "not measured". ADR-002 predicted the graph module would stay under 150 lines; it is
  171, and the ADR says so.
- Five small items filed by PR3's review were fixed, each with a test: a blank column name
  no longer hides a duplicate name in the same Check; long decimals are judged by
  significant digits, not length; no-break spaces in money and percent values are read as
  spaces; the report's floor heading uses plain words; and `verify.sh` gives the same
  Chromium install command as the README.
