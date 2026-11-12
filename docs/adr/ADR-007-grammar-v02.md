# ADR-007: Grammar v0.2 — ratios, conditional metrics and two-date series

- **Status:** Proposed. Predictions committed 2026-11-12, after the held-out set's hash
  and before any v0.2 grammar code.
- **Result:** measured 2026-11-12 on five live runs (see Result). 8 predictions held,
  2 missed (4 and 8).

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

## Method notes

**Gold revision 5 (held-out set), before any held-out result.** The held-out file was
revealed unchanged as revision 4, and its SHA-256 matched the pending hash committed
before any v0.2 code (`09451c63…`, `f2e6191`). Revision 5 then changed presentation
only, so that a right answer can match: no rounding, a fraction where the question asks
for one, and periods as dates, as in the seen set. No question text, filter or join
changed. Each edit below appears exactly once in its item's `gold_sql`, and
`tests/test_gold_manifest.py` undoes them and checks that the pending hash comes back.

```text
ho-001  - ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'cancelled') / COUNT(*), 2)
        + 100.0 * COUNT(*) FILTER (WHERE status = 'cancelled') / COUNT(*)
ho-002  - ROUND(100.0 * SUM(amount) FILTER (WHERE status = 'overdue') / SUM(amount), 2)
        + 100.0 * SUM(amount) FILTER (WHERE status = 'overdue') / SUM(amount)
ho-003  - ROUND(100.0 * COUNT(*) FILTER (WHERE priority = 'urgent') / COUNT(*), 2) AS pct_urgent
        + 1.0 * COUNT(*) FILTER (WHERE priority = 'urgent') / COUNT(*) AS share_urgent
ho-004  - ROUND(100.0 * COUNT(*) FILTER (WHERE w.job_type = 'repair') / COUNT(*), 2)
        + 100.0 * COUNT(*) FILTER (WHERE w.job_type = 'repair') / COUNT(*)
ho-005  - ROUND(100.0 * COUNT(*) FILTER (WHERE paid_at <= due_at) / COUNT(*), 2)
        + 100.0 * COUNT(*) FILTER (WHERE paid_at <= due_at) / COUNT(*)
ho-006  - ROUND(100.0 * COUNT(*) FILTER (WHERE segment = 'commercial') / COUNT(*), 2)
        + 100.0 * COUNT(*) FILTER (WHERE segment = 'commercial') / COUNT(*)
ho-007  - to_char(m.month, 'YYYY-MM')
        + date_trunc('month', m.month)::date
ho-008  - to_char(m.month, 'YYYY-MM')
        + date_trunc('month', m.month)::date
ho-009  - to_char(q.quarter, 'YYYY-"Q"Q')
        + date_trunc('quarter', q.quarter)::date
ho-010  - to_char(m.month, 'YYYY-MM')
        + date_trunc('month', m.month)::date
ho-011  - ROUND(AVG(EXTRACT(EPOCH FROM completed_at - opened_at) / 86400)::numeric, 2)
        + AVG(EXTRACT(EPOCH FROM completed_at - opened_at) / 86400)
ho-012  - ROUND(AVG(i.paid_at - i.issued_at), 2)
        + AVG(i.paid_at - i.issued_at)
ho-019  - ROUND((EXTRACT(EPOCH FROM timestamp '2026-06-30 00:00:00' - opened_at) / 86400)::numeric, 1)
        + EXTRACT(EPOCH FROM timestamp '2026-06-30 00:00:00' - opened_at) / 86400
ho-027  - to_char(date_trunc('month', created_at), 'YYYY-MM')
        + date_trunc('month', created_at)::date
```

## Result
Measured on five live runs of `anthropic:claude-haiku-5-5`, with the grammar and prompt
frozen from `4389ca9` before the first of them. "Before" is v0.1 code (`fc97462`) plus
only the `--gold` option, on branch `v02-before`. Both held-out runs score the same gold
file, revision 5.

| Run | Questions | Trials | Right | Wrong among answered | Refusal recall | Spend |
|---|---|---|---|---|---|---|
| [v02-holdout-before](../../evals/reports/v02-holdout-before.md) | held-out, v0.1 | 3 | 12/84 (14.3%) | 37/49 (75.5%) | 36/36 | $0.1131 |
| [v02-holdout](../../evals/reports/v02-holdout.md) | held-out, v0.2 | 3 | 40/84 (47.6%) | 14/54 (25.9%) | 36/36 | $0.1136 |
| [v02-seen](../../evals/reports/v02-seen.md) | seen, v0.2 | 3 | 111/129 (86.0%) | 2/113 (1.8%) | 72/72 | $0.1782 |
| [v02-spider-before](../../evals/reports/v02-spider-before.md) | Spider, v0.1 | 1 | 139/250 | 27/166 (16.3%) | n/a | $0.1325 |
| [v02-spider](../../evals/reports/v02-spider.md) | Spider, v0.2 | 1 | 140/250 | 11/151 (7.3%) | n/a | $0.1540 |

The one-shot baseline on the same held-out questions was right on 51/84 (60.7%) and wrong
on 33/84 (39.3%) with v0.2's run, so on held-out questions it is right more often than
Ledgerline and wrong more often too.

1. **Seen, fs-028 and fs-035 right in at least 2 of 3 trials:** held. Both were right in
   all 3.
2. **Seen, L11:** held. Wrong answers 2/113 (1.8%), below the expected 2–4%; accuracy 111/129 (86.0%), with 38, 37 and 36 right per trial.
3. **Seen, fs-041 right in at least 1 trial, five others still refused:** held. fs-041 was
   right in all 3; fs-025, fs-030, fs-037, fs-039 and fs-042 were refused in all 3.
4. **Held-out wrong answers lower than v0.1's and at most 8%:** missed. The rate fell from
   75.5% to 25.9%, but not to 8%. Of the 14 wrong answers, 12 differ from the gold only in
   form or ties: 9 because the gold also returns an id column (ho-020, ho-024, ho-028), 3
   because the gold breaks a tie by city (ho-022). The id-column convention was fixed
   before the runs and is kept. The other 2 are a misread (ho-010).
5. **Held-out, at least 4 more right than v0.1:** held. 28 more (12 to 40), all from the
   ten share and two-date questions (ho-001 to ho-010), which went from 0 right of 30 in
   v0.1 to 28 of 30.
6. **Held-out, at least 80% of out-of-grammar questions refused:** held. The 10 questions
   that need something v0.2 lacks (ho-011 to ho-019 and ho-025) were refused in all 30
   trials. v0.1 answered ho-017 and ho-019 wrongly in all 3 trials each.
7. **Refusal recall at least 23/24 per trial on seen and 11/12 on held-out:** held. 24/24
   and 12/12 in every trial.
8. **Spider wrong rate no more than 2 points above v0.1's, coverage within 3 points:**
   missed. The wrong rate fell 9 points (16.3% to 7.3%), but coverage fell 6 points
   (166/250 to 151/250, 66.4% to 60.4%). More questions are refused, and accuracy held
   (139 to 140 right). Of the 18 questions v0.2 refused but v0.1 answered, 11 had been
   wrong and 7 right. The guess that little would change on Spider was wrong, most likely
   because the refuse-first rule applies to every question, not only to ratios and series. No Spider miss differs from its gold only in row order, so the NULLS LAST
   default changed no Spider score.
9. **Unreadable answers at most 2% of calls in every v0.2 run:** held. 0 of 122 calls on
   held-out, 0 of 208 on seen, 0 of 279 on Spider, and 0 of 68 in the replay re-record.
   (v0.1 had 1 of 132 on held-out.)
10. **Cost per question up at most 30% from $0.000415, total spend under $1.20:** held.
    $0.000488 on held-out (+18%) and $0.000480 on seen (+16%). On Spider, v0.2 cost
    $0.000445 per question against v0.1's $0.000361 on the same run setup (+23%). Total
    live spend for the re-record ($0.0588) and the five runs ($0.6914) was $0.7502.

Triage of every miss is in `evals/triage/`. The held-out wrong answers are explained
in [docs/failures/](../failures/README.md).
