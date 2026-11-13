# Askwell product brief

## The problem

People want to ask their data a plain question, like "how much did we invoice last
quarter?", and get a number back. Large language models (*models* below) can turn the
question into SQL, the language databases answer in. But model-written SQL can run without
errors and still be wrong: it joins the wrong tables, misses a filter, or counts some rows
twice. The answer looks like any other table of numbers, so nobody notices.

A wrong number that looks right is worse than no number. It goes into a report and a
decision.

## Who it is for

- A small team with its data in a database or in spreadsheets, and no analyst on call.
- The person who will be asked "where did this number come from?" and needs to show the
  query behind it.
- Anyone who must keep some fields (emails, password hashes) away from a model and out of
  answers.

## What it does

1. **You ask a question in plain English.**
2. **The model fills in an intent**, a small typed form: which table, which numbers, which
   filters, which dates. It never writes SQL.
3. **Plain code checks the intent** against a *registry*, a file that lists what the
   database may expose. An unknown field, a hidden field or an unsafe join is refused with
   a reason. The model gets one retry with the reasons.
4. **Code writes the SQL** from the checked intent. Values are sent separately from the SQL
   text, and the query runs on a read-only connection.
5. **You get the rows and the SQL behind them.** The result rows are never sent to the
   model. Every question is written to an audit log.

You can use the demo database, or upload your own CSV files into a private workspace. A
check reads every file first and names the exact fix for each problem. Then you confirm
which fields the model may see.

## What it deliberately does not do

- **It does not run an intent the check rejects.** A rejected intent gets one retry and
  is then refused with a reason, even when a SQL-writing model would have got the
  question right. That costs coverage, and the benchmark counts the cost. It is not a
  guarantee against wrong answers: when a question needs something an intent cannot
  express, the model can still fill in a valid intent for a nearby question, and that
  answer is wrong. In the simulated run this happened on 3 of the 43 fieldservice
  questions that have an answer ([docs/failures/](failures/README.md)).
- **It does not let the model write SQL**, call tools, or see result rows.
- **It does not change data.** Every query is read-only, enforced by the database
  connection, not only by the code.
- **It does not write prose about the answer.** The answer is the table and the SQL. A
  model summary could restate a number wrongly.
- **It is not open to the public.** It runs on your machine, and a hosted beta runs at
  <https://askwell.cristianortega.dev> behind invite codes and a daily spending cap.

## How it is measured

The benchmark questions and their expected answers (the *gold*) were written and frozen
before the code that answers them existed, so the code could not be fitted to them. It
covers fieldservice, a synthetic field-service business with 67 questions, and 5
databases from Spider, a public text-to-SQL benchmark, with 50 questions each.

Askwell is compared with a *one-shot baseline*: the same model writes SQL directly. The
two numbers that matter most:

- **Execution accuracy:** how often the rows match the gold answer.
- **Wrong answers among answered:** how often a returned table is wrong. This is the
  safety number. Askwell should keep it low, even if that means refusing more.

Every rate is shown with a 95% interval, because 50 questions is a small sample. Every
Askwell miss is reviewed and given a cause.

Askwell answers live with Claude Haiku 5.5. On questions held out from its design it
gives fewer wrong answers than the baseline, but misses both of its targets (80% accuracy,
at most 5% wrong answers). The [results page](../README.md#results) has the numbers.
[`docs/failures/`](failures/README.md) walks through four misses from `sim-1`, an earlier
run whose answers came from a stand-in model.
