# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Hiring managers and business leaders or owners.** Cristian is looking for applied-AI and forward-deployed roles, and offers his services as an AI consultant. These visitors decide in a few minutes whether the method is sound and whether he can build trustworthy AI systems.
- **Small teams with their data in a database or spreadsheets** who want to ask it questions. They can upload their own CSV files and try it.

## Product Purpose

Askwell answers plain-English questions about a database and shows the SQL behind every answer. It exists because model-written SQL can run without errors and still be wrong, and a wrong number that looks right ends up in a decision. Success is a visitor who understands how AI is used here, what it is deliberately not used for, and what the method achieves, and who trusts the answers because they can check them.

## Positioning

The AI never sees your data and never writes SQL. The model only fills in a small typed form (an *intent*) from the table and column names, each column's type and short description, and the allowed labels of category columns. Hidden columns are never shown. Plain code checks that form against a list of what the database may expose, then writes the SQL itself and runs it read-only. Result rows never go to the model. When the question can't be expressed safely, Askwell says so instead of guessing.

## Operating Context

- Live public demo at https://askwell.cristianortega.dev, open to anyone, with a daily spending cap and per-visitor limits that stay hidden until hit ("try again tomorrow").
- Flow: Prepare, Upload CSVs, Check (each problem names the file, row, column and fix), Confirm (shows exactly what the model will be sent; any field can be hidden), Ask (rows plus the SQL).
- A demo database (fieldservice, made-up data) with recorded starter questions that answer with no key.
- A Results page with the measured accuracy, and a Value page that estimates hours saved against running cost.
- Runs locally with Docker; the hosted beta runs on one server.

## Capabilities and Constraints

- Model: Claude Haiku 5.5. The model fills in an intent and never sees result rows.
- Read-only queries, enforced by the database connection.
- No prose summaries of answers: the answer is the table and the SQL.
- CSVs with no id column get hidden row numbers ("No id column found; rows are numbered for you").
- Some features are switched off in the deployed settings (`link_roles`).
- Terminology to translate for visitors: intent, registry, refusal, held-out questions, one-shot baseline.

## Brand Commitments

- The name Askwell. Nothing visual is binding.

## Evidence on Hand

Measured v0.3 results (docs/adr/ADR-008-accuracy-v03.md, evals/reports/):
- On 96 questions held out from its design: 62 right (51 before v0.3); wrong among answered 4.1% (7.3% before), about 1 in 25 against 1 in 14; it refused all 72 questions it should refuse.
- A one-shot baseline (the same model writing SQL directly) gets more right (78 of 96) but is wrong more often among its answers (7.5%).
- One gate criterion failed on a public test database (world_1); Cristian approved the deploy anyway, recorded in ADR-008.
- Total cost of the v0.3 measurement: $1.64.
No customers, testimonials or case studies exist. Never invent them.

## Product Principles

- Show how the AI is used and how it is not. The method is the product.
- A refusal beats a confident wrong answer, and the page says so plainly.
- Every number on the site can be traced to its SQL or its measurement.
- Plain language first. Research terms live behind a fold, never in headlines.
- Less is more.
