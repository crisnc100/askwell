# fs-035: two monthly series, merged into one

**Question.** "For each month of 2026 so far, how many work orders were opened and how many
were completed?"

**Expected answer.** Six rows, one per month. "Opened" counts work orders by the month they
were opened. "Completed" counts them by the month they were completed. January: 240 opened,
230 completed.

**What Askwell did.** The model grouped work orders by the month they were opened, and
counted both the orders and the ones that have a completion date. So "completed" became
"orders opened this month that were later completed". January came out as 240 and 231.
Every month's second number was off, by up to 31 (June: 182 instead of 213).

**Why it was wrong.** The question needs two counts, each on its own date field, in one
table. An intent can group by both dates, but all its metrics share one grouping and one
set of rows, so it cannot count opened orders by one date and completed orders by the
other. The numbers look reasonable, which is what makes this kind of answer dangerous.

**Category.** `grammar_gap`, scored as a wrong answer.

**What would fix it.**
- Refuse first, as for [fs-028](fs-028-percentage.md).
- Or let an intent hold two series, each with its own grouping and date field, joined on
  the month.

**v0.2.** The grammar gained a series intent: one row per month, each series counted by
its own date field (ADR-007). In the live run `v02-seen` the model answered fs-035 with
one and was right in all 3 trials. This is a seen question: v0.2 was designed from it.
