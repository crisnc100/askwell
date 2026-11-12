# ADR-007: Grammar v0.2 — ratios, conditional metrics and two-date series

- **Status:** Proposed. Predictions committed 2026-11-12, after the held-out set's hash
  and before any v0.2 grammar code.
- **Result:** not measured yet.

## Context
The v0.1 live run on Claude Haiku 5.5 (`select-haiku-2026-11-11`) scored 35/43 correct
and 2 wrong among 37 answered on fieldservice: 5.4% wrong, against a limit of 5% (L11,
published as not met). Both wrong answers were questions the grammar could not express:
fs-028 asks for a percentage, and fs-035 asks for two counts by two different dates in
one monthly table. In each, the model answered a nearby question instead of refusing.
The live run also showed placeholder refusal reasons ("", "none", "None") that the
validator let through as refusals with no reason.

## Decision
- **Placeholder reasons** are rejected with their own code, `placeholder_reason`, on
  every intent type. On an `unanswerable` intent the model must say what is missing. On
  any other intent the message tells it to leave the field out, so the retry can.
- **Conditional metric:** a metric may carry its own `where` conditions and is counted
  or summed only over the rows that match. Its conditions follow every filter rule.
  It compiles to `agg(CASE WHEN … THEN x END)`, which runs the same on Postgres and
  SQLite.
- **Ratio metric:** `agg: "ratio"` divides one metric of the intent by another,
  optionally times 100 (`as_percent`). Division by zero gives NULL, never an error and
  never 0.
- **Series intent:** a new `intent_type`, `date_series`: one calendar grain, one
  optional period, and 1 to 4 series. Each series is a metric counted or summed by its
  own date field. One row per period, one column per series. It is built from one
  grouped subquery per series, left-joined to the union of their periods, so it needs
  neither `FULL OUTER JOIN` nor `generate_series`.
- **Prompt `interpret-v2`** describes the three additions and adds a refuse-first rule:
  when a question needs something the intent cannot express, answer `unanswerable` and
  name what is missing. It also names what is still out: durations between two dates,
  products of fields, "has none" questions and distinct counts of periods.
- **Measured on two question sets.** The 67 seen fieldservice questions, which this
  change was designed from, and a new 40-question held-out set written blind before any
  v0.2 code, committed by hash first. The held-out result is the headline. Every result
  on the seen set is labelled "seen".

## Prediction (pre-registered)
All on `anthropic:claude-haiku-5-5`, 3 trials unless stated.
1. **Seen, fs-028 and fs-035:** each is correct in at least 2 of its 3 trials.
2. **Seen, L11:** wrong-answer rate, pooled over 3 trials, is at most 5% (expected
   2–4%). Accuracy is at least 81.4% (expected 37–39 of 43 per trial).
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
7. **Refusals:** refusal recall is at least 23/24 per trial on seen, and at least 11/12
   per trial on held-out.
8. **Spider (1 trial):** v0.2's wrong-answer rate is no more than 2 points above v0.1's,
   and coverage moves by no more than 3 points either way. Few Spider questions ask for
   ratios or two-date series, so little should change.
9. **Unreadable answers:** at most 2% of calls in every v0.2 run, despite the longer
   schema and prompt.
10. **Cost:** cost per question rises by at most 30% from $0.000415, because the prompt
    is longer. Total live spend for re-recording and the five runs is under $1.20.

## Result
Not measured yet. The five live runs come after the grammar and prompt are frozen.
