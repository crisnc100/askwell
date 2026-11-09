# ADR-004: Default and second model, chosen by a live spike

- **Status:** Spike PENDING. The spike command exists (`ledgerline spike`); it has not run
  because no `OPENROUTER_API_KEY` was available when P1 was built. No model is chosen yet,
  and no result below is filled in.
- **Result:** PENDING.

## Context
All LLM access goes through OpenRouter on a $50/month budget shared across projects, so
the default must be cheap. Ledgerline depends on json_schema structured output, and
support varies by model and by upstream provider.

## Decision procedure
1. Pick 4–6 non-batch candidates that OpenRouter's models endpoint lists with
   `structured_outputs` and a prompt price under $0.50/M tokens.
2. Run `uv run ledgerline spike --models <ids> --budget 0.50` (five fixed probes per model,
   temperature 0, `provider.require_parameters = true`). The JSON report lands in
   `evals/spike/` and is committed.
3. Default = cheapest model with 5/5 `honoured` and 5/5 exact; second = the best model
   from a different vendor family that meets the same bar. Ties go to lower p50 latency.
4. Set them in config (`LEDGERLINE_DEFAULT_MODEL`, `LEDGERLINE_SECOND_MODEL`); model ids
   never appear in logic.

## Prediction (pre-registered)
1. At least two candidates honour json_schema on 5/5 probes.
2. At least one candidate that advertises `structured_outputs` still fails at least one
   probe (no parse, or a parse that does not validate), which is why the spike exists.
3. The whole spike spends under $0.05.

## Result
PENDING. Fill in: candidates run, honoured/exact per model, spend, the chosen default and
second model, and which predictions held.
