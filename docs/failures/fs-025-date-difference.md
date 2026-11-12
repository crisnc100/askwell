# fs-025: an average duration, refused

**Question.** "On average, how many days does it take to complete an urgent work order?"

**Expected answer.** About 1.35 days: the average time from `opened_at` to `completed_at`
for completed urgent work orders.

**What Askwell did.** It refused, with this reason from the model: "Average days to
complete needs the elapsed time between work_orders.opened_at and work_orders.completed_at,
and the registry has no way to compute a difference between two date fields."

**Why it refused.** That reason is correct. A metric works on one field; it cannot subtract
one date from another. This is the trade the design makes on purpose: a clear refusal
instead of a guess. It still counts against Askwell's coverage and accuracy, and the
one-shot baseline got this one right.

**Category.** `grammar_gap`, scored as a refusal.

**What would fix it.** A "time between two dates" value in the intent, in days or hours,
that the validator checks (both fields must be dates) and the SQL builder writes the same
way on Postgres and SQLite.
