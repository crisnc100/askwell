# fs-028: asked for a percentage, got counts

**Question.** "What percentage of the work orders opened last year ended up cancelled?"

**Expected answer.** One number: about 6.42% (159 of the 2,478 work orders opened in 2025).

**What Ledgerline did.** The model returned an intent that counts work orders opened last
year, grouped by status. The check passed it, because every part was valid, and the answer
was a two-row table: cancelled 159, completed 2,319. The counts are right, but the question
asked for a percentage, and nothing in the answer says that the person has to work it out.

**Why it was wrong.** An intent can count, sum and average, but it cannot divide one count
by another. The right move was to refuse and say so. The model answered a nearby question
instead.

**Category.** `grammar_gap`, scored as a wrong answer.

**What would fix it.**
- The prompt tells the model to refuse first when a question needs something the intent
  cannot express (planned for v0.2, and measured on a fresh run).
- Longer term, a "share of rows" metric: the fraction of rows that match a filter, checked
  like any other metric.

The one-shot baseline wrote the right query but rounded the result to two decimals (6.42),
so it did not match the gold's unrounded 6.4165 either.
