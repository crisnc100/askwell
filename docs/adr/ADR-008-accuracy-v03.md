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
Not measured yet. It is written from the Phase 4 reports of `builds/v03/plan.md`.
