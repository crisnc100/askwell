# ADR-008: v0.3 accuracy — stable answers, uncurated schemas, four grammar features

- **Status:** Proposed. Predictions and the deploy gate committed 2026-11-13, after the
  v0.3 held-out set's hash and the untriaged Spider IDs (gold revision 6, `37f85d7`) and
  before any v0.3 code.
- **Result:** not measured yet.

## Context
On the v0.2 held-out questions Askwell was right on 40 of 84 (47.6%, target 80%) and
wrong on 14 of 54 answered (25.9%, target 5%). Of the 14 wrong answers, 6 had the right
names, values and order but not the id column the gold also returned (ho-020, ho-024),
3 differed only in the order of tied rows (ho-022), 3 cut a three-way tie for fifth
place that has no single right answer (ho-028), and 2 were misreads (ho-010). The 30
false refusals were 10 questions needing a duration, a value computed from two fields,
"has none", a distinct count of periods or a comparison with an average. On four of five
Spider databases Askwell refused 40–56% of answerable questions; 62 of those 99
refusals came from two links between the same tables, links `registry init` did not
infer, and numbers stored as text. `builds/v03/plan.md` has the full diagnosis and its
evidence.

Two product bugs sit behind the id-column and tie failures. Grouping by a name groups by
the name only, so two customers called "Garcia Ltd" (ids 56 and 144) are added together.
And rows that tie on the ordering come back in whatever order the engine returns.

## Decision
- **Stable answers.** An entity can declare a label field, "the name of the thing".
  Grouping by it groups by the entity's key and the label, and returns the key. Grouping
  by any other field is unchanged. After the intent's own ordering, SQL orders by the
  group-by columns (or a row list's key), so ties come back the same on Postgres and
  SQLite. A top-N whose next row ties with its last says so (`tied_at_cutoff`).
- **Uncurated schemas.** A link can be named by a role when two links join the same
  tables. `registry init` and the CSV upload check infer more links, but only on a name
  match backed by full value containment and enough distinct values. A TEXT column of
  numbers, with placeholders such as `'null'` read as NULL, is typed numeric.
- **Grammar v0.3:** values computed from two fields, durations in days, "has" and "has
  none" filters, and comparison with an average, minimum or maximum over the same rows
  the question selects. Distinct counts of periods, set operations and comparison with
  the top row's value stay out.
- **Feature switches.** Every feature that can turn a refusal into an answer can be
  switched off with `ASKWELL_FEATURES_OFF`; off, it is refused as before.
- **Measured once, after the code is frozen,** on a new 120-question fieldservice
  held-out set written blind from a scrubbed brief, and on 200 untriaged Spider
  questions from the four Spider dev databases v0.2 never used, through `registry init`
  and through the CSV upload path. The v0.2 held-out set is reported as seen.
- **No scorer change.** The new held-out golds show only the columns a question asks
  for. This convention was chosen after seeing that Askwell failed the v0.2 held-out
  writer's convention of also returning an id; the seen fieldservice golds already used
  it. A gold may not depend on an arbitrary tie order; that rule removes the class of
  question ho-022 and ho-028 belong to, so the Result reports how many drafts it dropped
  or reworded.

## Consequences
- A question about a name's text ("which customer name is most common") gets one row per
  customer once a label is declared.
- Nothing deploys before the gate below is read.
- One new setting, `ASKWELL_FEATURES_OFF`, and a name-column choice on the Confirm page.

## The deploy gate
v0.3 deploys only if its per-trial wrong rate on the v0.3 held-out set is no higher than
that of main at `4014aa0` on the same questions, and, per untriaged Spider database and
for the CSV path, its wrong rate rises by no more than 5 points. If a gate fails, every
switch whose feature appears in a wrong answer of the failing run is turned off, the run
is repeated once, and the gate is read on the repeat. If it still fails, nothing
deploys.

## Prediction (pre-registered)
All on `anthropic:claude-haiku-5-5`; fieldservice 3 trials, Spider 1. Accuracy is
question-level (right in at least 2 of 3 trials, interval on distinct questions); wrong
answers are per trial, among answered. Predictions are not acceptance; the gate is.
1. **v0.3 held-out, accuracy:** question-level at least 70%; expected 70–82%. The 80%
   target is the goal; it is not predicted to be met.
2. **v0.3 held-out, wrong among answered:** per trial at most 8%; expected 3–8%.
3. **Before and after:** v0.3 is right on at least 10 points more of the held-out
   questions than main at `4014aa0`, with McNemar's exact p < 0.05, and its per-trial
   wrong rate is lower.
4. **Refusals:** refusal recall at least 23 of 24 per trial on the v0.3 held-out set.
5. **Seen v0.2 held-out:** at least 63 of 84 right (from 40; ho-017 stays refused), wrong
   at most 4 of answered per trial.
6. **Seen fieldservice:** at or above 81.4% right and at or below 5% wrong (L11).
7. **Link roles, seen:** on the 36 seen Spider questions refused for two links, per-trial
   wrong among answered at most 5%, and no question wrong in more than 1 of 3 trials.
   *Amended 2026-11-13, before the run:* read on 26 of the 36, those of network_1 and
   wta_1. flight_2 stores its airport codes in `flights` with a leading space, so either
   link returns zero rows and its 10 questions cannot show a wrong link; they would only
   add right answers.
8. **Untriaged Spider (`registry init`):** false refusals fall in at least 3 of the 4
   databases; in none does the wrong rate rise by more than 5 points.
9. **Untriaged Spider as CSV uploads:** false refusals fall by at least 3 points in at
   least 2 of the 4 databases, scored on all 200 questions with load failures counted as
   refusals.
10. **Unreadable answers** at most 2% of calls in every run; **cost per question** up at
    most 35% from v0.2's $0.000480.

## Seen checks in PR-2
Seen questions, so neither is a measurement of accuracy.
- **Expressibility:** the plan's target was that hand-written intents return the gold
  rows for at least 55 of the 62 seen Spider refusals caused by two links, missed links
  or numbers as text. 42 do. 8 cannot be written: their golds also need "has none"
  (5) or a set intersection (3). 12 are written and answered but differ from a gold
  that is itself off: 9 car_1 golds compute on the text of a numbers-as-text column
  (`'null'` averaged as 0, `max` returning `'null'`, comparisons by character), one
  inner join drops a model whose maker is missing, and two pick one airline from a tie
  of all of them. No gold was changed.
- **Link-role gate (prediction 7, as amended): failed.** `evals/reports/v03-roles-seen.md`,
  26 questions, 3 trials, $0.043. Wrong among answered per trial: 1 of 19 (5.3%), 1 of 19
  (5.3%), 0 of 18. spider:906 was wrong in 2 of 3 trials: asked who "has the greatest
  number of likes", the model counted likes received (`highschooler@liked_id`), the
  gold counts likes given. So `link_roles` ships switched off (`compose.prod.yaml`), as
  the plan says; with it off those questions are refused as before.

## Result
Measured 2026-11-15 on `anthropic:claude-haiku-5-5`, record mode, every switch on. The
before code is branch `v03-before`: main at `4014aa0` plus only the eval files these runs
read (never merged). Reports are in `evals/reports/`; before and after are paired with
`python -m askwell.bench.paired` (`evals/paired/`). Spend $1.4334, plus $0.0720 for the
interpret-v3 re-record: $1.5054 of the $4 cap.

### The deploy gate: the first read fails; the gated Spider repeat is pending
| Criterion | Before | After | Verdict |
|---|---|---|---|
| v0.3 held-out, wrong among answered, per trial | 7.3%, 7.4%, 7.3% | 4.7%, 4.7%, 3.1% | pass |
| cre_Doc_Template_Mgt, wrong among answered | 0.0% (0/46) | 2.0% (1/50) | pass (+2.0) |
| student_transcripts_tracking | 27.5% (11/40) | 27.3% (12/44) | pass (−0.2) |
| tvshow | 2.4% (1/41) | 12.5% (6/48) | **fail (+10.1)** |
| world_1 | 8.1% (3/37) | 14.3% (6/42) | **fail (+6.2)** |
| CSV path, cre_Doc_Template_Mgt | 2.4% (1/41) | 2.3% (1/44) | pass |
| CSV path, student_transcripts_tracking | 33.3% (11/33) | 24.3% (9/37) | pass |
| CSV path, tvshow | 11.8% (4/34) | 8.8% (3/34) | pass |
| CSV path, world_1 | 0.0% (0/2) | 15.4% (4/26) | **fail (+15.4)** |
| CSV path, all four together | 14.5% (16/110) | 12.1% (17/141) | pass (−2.4) |

Spider runs are one trial. Read as wrong over all 50 questions instead, the verdicts are
the same (tvshow 1 → 6, world_1 3 → 6, CSV world_1 0 → 4). Each database row moves by a
handful of answers, so its interval is wide (tvshow after: 6 of 48, 6–25%).

**What the rule turns off.** Every wrong answer of the two failing runs was validated
again with each switch off; a switch counts as used when the answer is refused or
compiles to different SQL without it.
- `v03-spider-new`: `has` (tvshow 635, 636, 637; world_1 783; student_transcripts 578),
  `numeric_text` (tvshow 613, 615, 616) and `link_roles` (student_transcripts 578, 583,
  584). The other 15 wrong answers use none. Per the rule these three switches are
  turned off and the run is repeated once as `v03-spider-new-gated`; the gate is read on
  the repeat. Pending: the repeat needs its own go.
- `v03-csv-new`: no wrong answer uses a switch. Its world_1 rise comes from the numbered
  rows of O11, which have no switch: `country` and `countrylanguage` now load (48
  questions were refused before because those files failed the upload check; 22 are now
  right and 4 wrong). Turning switches off cannot change this run, so on the rule as
  written the CSV world_1 criterion fails, while the CSV path as a whole improves
  (14.5% → 12.1% wrong among answered).

### Before and after on the held-out set (question-level, paired)
| System | Right before | Right after | Only after | Only before | McNemar p |
|---|---|---|---|---|---|
| Askwell | 51 of 96 (53.1%) | 62 of 96 (64.6%, 55–73%) | 11 | 0 | 0.0010 |
| One-shot baseline | 78 of 96 | 78 of 96 | 3 | 3 | 1.0 |

Pooled over trials: Askwell 64.2% right (185/288), 4.1% wrong among answered (8/193);
the one-shot baseline 81.9% right and 7.5% wrong (19/255).

### Predictions
1. Held-out accuracy at least 70%: **missed**, 64.6% (62 of 96). 31 of the 96 are
   refused in every trial. Most need what the grammar still lacks (window functions and
   ranks within groups, running totals, medians and percentiles, set intersections,
   per-group totals beside rows, a computed value of three fields); a few look
   expressible and were refused anyway (h3-037 and h3-060, counts that keep the zero
   rows; h3-073, an average per group).
2. Held-out wrong among answered at most 8% per trial: **met**, 4.7%, 4.7%, 3.1%.
3. Before and after at least +10 points with p < 0.05 and lower wrong: **met**,
   +11.5 points, p = 0.001, wrong lower in every trial.
4. Refusal recall at least 23 of 24 per trial: **met**, 24 of 24 in each trial.
5. Seen v0.2 held-out at least 63 of 84, wrong at most 4 per trial: **met**, 75 of 84
   right, 3 wrong of 78 answered in all.
6. Seen fieldservice at least 81.4% right, at most 5% wrong: **met**, 94.6% (122/129) and
   3.9% (5/127).
7. Link roles, seen: **missed** in PR-2 (above); `link_roles` stays off.
8. Untriaged Spider: false refusals fall in at least 3 of 4, no wrong rate up more than
   5 points: **half met**. False refusals fell in all 4 (8 → 0, 20 → 12, 18 → 4, 26 → 16
   per 50), but wrong rose 10.1 points on tvshow and 6.2 on world_1.
9. CSV path: false refusals down at least 3 points in at least 2 of 4: **met** in 3
   (cre 18 → 12%, student_transcripts 34 → 26%, world_1 96 → 48%; tvshow 32% both).
   No file fails the upload check now; before, five tables failed on `no_id_column`.
10. Unreadable answers at most 2% of calls, cost per question up at most 35%: **missed**
    on the held-out run, 13 of 381 calls (3.4%): 10 are answers cut off at the completion
    limit (h3-091 in every trial, h3-094 and h3-058 once each); at most 0.5% in the
    others. Cost per
    question **met**: $0.000642 on the held-out set, up 33.8% from $0.000480.

### Seen Spider, one trial
| Database | Right | Wrong among answered | False refusals |
|---|---|---|---|
| car_1 | 60.0% | 31.8% (14/44) | 12% |
| dog_kennels | 50.0% | 28.6% (10/35) | 30% |
| flight_2 | 88.0% | 8.3% (4/48) | 4% |
| network_1 | 92.0% | 6.1% (3/49) | 2% |
| wta_1 | 86.0% | 12.2% (6/49) | 2% |

Seen: the PR-2 and PR-3 changes were written from these questions, so these numbers
show where the fixes landed, not accuracy.
