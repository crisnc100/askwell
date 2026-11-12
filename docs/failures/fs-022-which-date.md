# fs-022: which date does "used" mean?

**Question.** "What are the top 5 parts by quantity used over the last 12 months?"

**Expected answer (the gold).** The five parts with the most quantity on work orders
*opened* between 2025-06-30 and 2026-06-30.

**What Askwell did.** The model filtered on the date work orders were *completed*, over
the same 12 months. Four of the five parts are the same, in a slightly different order
with slightly different totals; the fifth differs.

**Why it was scored wrong.** The question does not say which date to use. Parts are
installed when the job is done, so the completion date is a fair reading; the gold picked
the opening date. Both answers are defensible, so the miss says more about the question
than about Askwell.

**Category.** `gold_issue`, scored as a wrong answer.

**What would fix it.** Reword the question to name the date ("on work orders opened in the
last 12 months"). Gold questions are frozen, so that change needs a reason in
`evals/gold/CHANGELOG.md` and is left for a deliberate gold revision. Askwell already
shows the intent it ran, including the date field, so a reader can see which reading it
took.
