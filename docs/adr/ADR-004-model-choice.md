# ADR-004: Default and second model, chosen by a live spike

- **Status:** Spike PENDING. The spike command exists (`ledgerline spike`); it has not run
  because no `OPENROUTER_API_KEY` was available when P1 was built. No model is chosen yet,
  and no result below is filled in.
- **Result:** not measured (see Result).

## Interim target (2026-11-09)
There is no OpenRouter key yet, so no real model runs. Until there is, a Claude model
writes the model's answers instead ("simulated answers"; see [docs/rerecord.md](../rerecord.md)).
Each simulated answer is recorded as standing in for one target model:
`openai/gpt-oss-120b`. It is the `LEDGERLINE_DEFAULT_MODEL` default.

Why this one: it is cheap, and OpenRouter lists it as supporting structured output.
That listing is a claim, not a measurement. The spike below still has to run once a key
exists, and it may pick a different default.

Changing the target changes every recording key, so the recordings must be made again.
That costs nothing while answers are simulated.

The simulated eval uses this one target only. The plan's second model also waits for a
key: simulating a "different vendor" with the same Claude stand-in would be fake
diversity.

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
Not measured, as of 2026-11-11. The spike needs a live model and there is no OpenRouter key
yet, so no candidate has run and no model is chosen.

1. **At least two candidates honour json_schema on 5/5 probes:** not measured.
2. **At least one advertising candidate fails a probe:** not measured.
3. **The spike spends under $0.05:** not measured.

Every result in this repo uses the interim target, `openai/gpt-oss-120b`, with simulated
answers. The spike runs once a key exists, and the recordings are made again if it picks a
different default.

## Amendment 1 (2026-11-11): spike result, and a new selection rule

This amendment is added below the original text, which stays as written. It was
committed before any live selection run, so `git log` shows the rule came first.

### Spike result
The spike ran on 2026-11-11 with six candidates. The report is
[evals/spike/spike-2026-11-11T201030Z.json](../../evals/spike/spike-2026-11-11T201030Z.json).

| Candidate | Honoured | Exact | Cost (USD) | p50 latency |
|---|---|---|---|---|
| openai/gpt-oss-120b | 5/5 | 1/5 | 0.000205 | 4.7 s |
| openai/gpt-oss-20b | 5/5 | 1/5 | 0.000379 | 3.5 s |
| z-ai/glm-5.3-flash | 4/5 | 2/5 | 0.000216 | 1.8 s |
| mistralai/mistral-small-24b-instruct-2501 | 5/5 | 2/5 | 0.000032 | 0.9 s |
| google/gemma-4-26b-a4b-it | 5/5 | 2/5 | 0.000049 | 0.6 s |
| meta-llama/llama-3.1-8b-instruct | 5/5 | 1/5 | 0.000132 | 0.5 s |

"Honoured" means the provider returned a parse that validates. "Exact" means every field
matched the expected answer.

- **Prediction 1 held:** five candidates honoured json_schema on 5/5 probes.
- **Prediction 2 held:** glm-5.3-flash advertises structured output and still returned
  an answer that failed validation on one probe.
- **Prediction 3 held:** the spike spent $0.001.
- **Step 3 picked no model.** It needs 5/5 exact, and the best exact score was 2/5.
  Probes 0 and 4 were missed by all six models, so the expected answers are the likely
  problem, not the models. The report did not store the answers, so it cannot show which
  field differed. It stores them now.

### Deviations from the procedure
- The first run used `max_tokens` 300 and crashed. A reasoning model's answer hit the
  limit, and the SDK error escaped the gateway. The spike was run again at 2000.
  The gateway now charges such an answer and treats it as unreadable.
- The report was not written to `evals/spike/`, which did not exist yet. It is committed
  there now.

### Why the spike cannot choose
The spike's schema is small and flat. The real answer schema, `Intent`, is far larger
and nested, so a model that passes the spike can still fail on it. The choice moves to
the fieldservice benchmark, where the real prompt and schema are used.

The benchmark's accuracy floor (L11, 80%) cannot choose either. Eight of the 43
answerable questions need things the intent grammar cannot express, so no model can
score above 35/43 (81.4%). L11 stays as the product floor and is reported as it is.

### New rule
1. **One live pass** on the fieldservice benchmark in record mode, so it also writes
   the new recordings: one trial, the `ledgerline` and `oneshot` systems.
2. **Candidates,** cheapest first:
   - `mistralai/mistral-small-24b-instruct-2501`
   - `google/gemma-4-26b-a4b-it`
   - `openai/gpt-oss-120b`
   - `openai/gpt-4o-mini`, the top of the ladder. It is in OpenRouter's "mini" price
     tier ($0.15 per million prompt tokens, $0.60 per million completion tokens), its
     listing includes `structured_outputs`, and it is not a frontier model. It does not
     reason before answering, so its latency is not inflated by hidden thinking. It is
     also the model Docket uses, so cost per question compares across the projects.
3. **Gates.** A candidate is eligible only if it passes all three:
   - **Unreadable answers** are at most 2% of model calls. An unreadable answer is one
     that fails to parse, including one cut off at `max_tokens`. It is counted
     directly, because an answer that fails to parse twice becomes a refusal, which
     would otherwise look like a correct refusal.
   - **Refusal recall** is at least 23 of the 24 refusal questions.
   - **Median (p50) latency** per question is at most 3 seconds.
4. **Pick.** Among eligible candidates, find the best: the most correct answers on the 43
   answerable questions. The default is the cheapest eligible candidate, by measured
   cost per question, that is not clearly worse than the best. "Clearly worse" means 4
   or more questions behind on correct answers, or 4 or more more wrong answers.
5. **Tie-break.** If two candidates are equal on cost, the live Spider run (L10)
   decides between them.
6. **Second model:** the best eligible candidate from a different vendor than the
   default.
7. **If no candidate passes the gates,** ship the best one and say so. Never step up to
   a frontier model.
8. **Budget:** $3 in total for every live run in PR5, enforced by the budget guard.

The result is added to this ADR as Amendment 2.
