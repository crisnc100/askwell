# ADR-005: Replay recordings and a hard per-run budget

- **Status:** Accepted for P1 (gateway built and tested). Prediction committed 2026-11-09.
- **Result:** recorded 2026-11-11 (see Result). There has been no live run yet.

## Context
The repo is public and CI never calls a live model. Reviewers and cloners must be able
to run tests, the eval and the demo with no key. Live spending is capped at $50/month in
total, and an eval that loops over hundreds of questions can overspend quickly.

## Decision
- **Replay:** structured calls are recorded in JSONL keyed by hash(model, prompt_version,
  messages, schema); agent baselines are recorded per (system, question_id, model,
  prompt_version) because their messages contain DB rows whose order varies. Modes are
  `record | replay | live | export`; a replay miss raises and never falls back to live.
  Export is replay plus one step: a request with no recording is written to
  `evals/pending/` for a simulated answer (see [docs/rerecord.md](../rerecord.md)).
- **Budget:** before every live call, a worst-case cost (prompt bytes × prompt price
  + `max_tokens` × completion price) is checked against what is left. The prompt bytes
  are the UTF-8 size of the messages and the response schema as JSON. Every token covers
  at least one byte, so this bounds the prompt's tokens for any text. In an eval,
  the run stops hard at `--budget`. An API or CLI ask has its own limit
  (`LEDGERLINE_ASK_BUDGET_USD`), and going over it refuses that one question. Actual
  cost comes from OpenRouter's reported usage cost, else from models-endpoint pricing.
  Results are checkpointed per item, so a stopped run resumes, carries its spend
  forward, and still yields a partial report. 429s back off exponentially. The
  OpenRouter key also has a credit limit as a backstop.

## Prediction (pre-registered)
1. The replay eval reproduces the committed replay report byte for byte in CI, with zero
   replay misses.
2. Total live spend for P4 (fieldservice × 3 systems × 2 models × 3 trials, plus Spider
   5 DBs × 50 × 3 systems × 1 model) is under $5, and no run exceeds its `--budget`.
3. The worst-case pre-check overestimates the actual cost of a call by 3× to 10× (a
   token is usually 3–4 characters, and most completions stop far below `max_tokens`).
4. The sql_agent baseline costs 3× to 8× the Ledgerline pipeline per question.

## Result
Recorded 2026-11-11. Every model answer so far is simulated, so nothing here was spent or
measured against a real model.

1. **The replay eval reproduces the committed report byte for byte, with zero misses:**
   held for the Markdown report. `./verify.sh` replays the fieldservice recordings and
   compares the result with `evals/reports/replay-fieldservice.md`. It passed locally and
   in CI on every merged PR. A replay miss raises, so a pass means there were none. The
   JSON report is not compared, because it holds replay latencies, which vary run to run.
2. **Live spend under $5, and no run over its budget:** not measured. There has been no
   live run; total spend is $0.
3. **The worst-case pre-check overestimates a call's cost by 3× to 10×:** not measured. No
   live call has been made. One change since the prediction: the pre-check now counts the
   prompt in UTF-8 bytes, not characters, because one character can be up to 4 bytes and a
   token is never shorter than a byte.
4. **sql_agent costs 3× to 8× the Ledgerline pipeline per question:** not measured. The
   sql_agent baseline is not built yet.
