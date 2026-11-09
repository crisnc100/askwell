# ADR-005: Replay recordings and a hard per-run budget

- **Status:** Accepted for P1 (gateway built and tested). Prediction committed 2026-11-09.
- **Result:** PENDING (measured after the P4 live run).

## Context
The repo is public and CI never calls a live model. Reviewers and cloners must be able
to run tests, the eval and the demo with no key. Live spending is capped at $50/month in
total, and an eval that loops over hundreds of questions can overspend quickly.

## Decision
- **Replay:** structured calls are recorded in JSONL keyed by hash(model, prompt_version,
  messages, schema); agent baselines are recorded per (system, question_id, model,
  prompt_version) because their messages contain DB rows whose order varies. Modes are
  `record | replay | live`; a replay miss raises and never falls back to live.
- **Budget:** before every live call, a worst-case cost (prompt characters × prompt price
  + `max_tokens` × completion price) is checked against what is left; the run stops hard
  at `--budget`. Actual cost comes from OpenRouter's reported usage cost, else from
  models-endpoint pricing. Results are checkpointed per item, so a stopped run resumes,
  carries its spend forward, and still yields a partial report. 429s back off
  exponentially. The OpenRouter key also has a credit limit as a backstop.

## Prediction (pre-registered)
1. The replay eval reproduces the committed replay report byte for byte in CI, with zero
   replay misses.
2. Total live spend for P4 (fieldservice × 3 systems × 2 models × 3 trials, plus Spider
   5 DBs × 50 × 3 systems × 1 model) is under $5, and no run exceeds its `--budget`.
3. The worst-case pre-check overestimates the actual cost of a call by 3× to 10× (a
   token is usually 3–4 characters, and most completions stop far below `max_tokens`).
4. The sql_agent baseline costs 3× to 8× the Ledgerline pipeline per question.

## Result
PENDING.
