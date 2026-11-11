# ADR-004: Default and second model, chosen by a live spike

- **Status:** Decided, 2026-11-11. The spike ran but could not choose (Amendment 1); the
  fieldservice benchmark chose under a new rule (Amendment 2). The sections before the
  amendments are the original record and are kept as written.
- **Result:** default `mistralai/mistral-small-24b-instruct-2501`, second
  `google/gemma-4-26b-a4b-it` (Amendment 2).

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

## Amendment 2 (2026-11-11): the selection result

The live pass ran once, as Amendment 1 set out: fieldservice, one trial, the `ledgerline`
and `oneshot` systems, record mode, run id `select-2026-11-11`. It spent $0.100 of its $2
budget. The full report is
[evals/reports/select-2026-11-11.md](../../evals/reports/select-2026-11-11.md), and the
rule applied to it is
[evals/reports/model-selection-select-2026-11-11.md](../../evals/reports/model-selection-select-2026-11-11.md)
(`scripts/select_model.py`).

The scores are for the `ledgerline` system. Cost per question is measured, retries
included. "Unreadable" counts model calls whose answer did not parse.

| Model | Cost per question | Correct (of 43) | Wrong | Refusal recall | Unreadable | p50 latency | Gates |
|---|---|---|---|---|---|---|---|
| mistralai/mistral-small-24b-instruct-2501 | $0.000145 | 21 | 6 | 24/24 | 0/91 (0%) | 1.29 s | pass |
| google/gemma-4-26b-a4b-it | $0.000219 | 23 | 7 | 23/24 | 0/93 (0%) | 1.31 s | pass |
| openai/gpt-oss-120b | $0.000277 | 25 | 4 | 24/24 | 7/84 (8.3%) | 2.48 s | fails unreadable |
| openai/gpt-4o-mini | $0.000319 | 19 | 5 | 24/24 | 4/79 (5.1%) | 1.28 s | fails unreadable |

### The choice
- **Best eligible:** gemma-4-26b-a4b-it, with 23 correct.
- **Default: `mistralai/mistral-small-24b-instruct-2501`.** It is the cheapest eligible
  model. It is 2 correct answers behind the best and has 1 fewer wrong answer, so it is
  not clearly worse (that needs 4 or more).
- **Second: `google/gemma-4-26b-a4b-it`,** the best eligible model from another vendor.
- No tie on cost, so the Spider tie-break was not needed.

### What the numbers say
- **gpt-oss-120b's unreadable answers were all cut off.** Each of the 7 stopped at the
  1,024-token limit (`LEDGERLINE_MAX_TOKENS`), because the model reasons before it
  answers and spent the limit doing so. The rule fixes the production settings, so this
  counts against it. The choice is sensitive to that limit: had gpt-oss-120b passed
  the gate, it would be the best (25), mistral would be exactly 4 behind, and the
  default would be gemma. The rule was applied as approved and not rerun.
- **One trial.** Each model answered each question once, so a difference of a few
  questions between models is within noise. The 95% ranges in the report are wide.
- **The top of the ladder bought nothing.** gpt-4o-mini cost the most per question and
  scored the fewest correct answers. Its 4 unreadable answers parsed as JSON but did
  not match the intent schema.
- **No model reaches the L11 floor** (at least 80% correct, at most 5% wrong among
  answered). The default scores 48.8% correct (21/43) and 22.2% wrong among answered
  (6/27). Eight questions need things the intent grammar cannot express, so 81.4% was
  the ceiling for any model. The floor stays as the product target, reported as not met.
- **Live is well below simulated.** The simulated stand-in scored 33/43 on the same
  questions; the live default scores 21/43. Most of the gap is intents that fail
  validation twice: a placeholder value in `unanswerable_reason` on a normal question,
  a missing `group_by`, or a sort on a field that does not exist. Closing that gap, in
  the prompt and the grammar, is the v0.2 question.

Every recording these numbers come from is committed under
`evals/recordings/eval/fieldservice/`, so `ledgerline eval --mode replay` with run id
`select-2026-11-11` rebuilds the report without a key.

## Amendment 3 (2026-11-11): Claude Haiku 5.5, measured under the same gates

This amendment was committed before Haiku 5.5's live run, so `git log` shows the rule
came first.

**The choice.** Cristian chose Claude Haiku 5.5 (`claude-haiku-5-5`) as the beta's model.
His Claude plan includes monthly Anthropic API credits, which apply only to calls made
directly to the Anthropic API, not through OpenRouter. Within the beta's daily cap, the
model is in effect free. Its list price is $0.10 per million input tokens and $0.50 per
million output tokens (for prompts up to 100,000 tokens), and spend is still measured
and capped at that price.

**How it is measured.** The same way as Amendment 1's candidates: one live pass on the
fieldservice benchmark, record mode, one trial, the `ledgerline` and `oneshot` systems,
and the production settings (`LEDGERLINE_MAX_TOKENS` 1,024). It is called directly
through the Anthropic API, with structured output (`output_config.format`, a JSON
schema), adaptive thinking at effort `low`, and no sampling settings. Its row is reported
next to the four from Amendment 2.

**The rule for this choice.**
- Haiku 5.5 must pass the same three gates: unreadable answers at most 2% of calls,
  refusal recall at least 23 of 24, median latency at most 3 seconds.
- If it passes, it becomes the default, because it is Cristian's explicit choice. The
  "not clearly worse" comparison is reported, but it does not overrule that choice.
- If it fails a gate, nothing changes: the default stays mistral-small, and the numbers
  go back to Cristian.
- gemma-4-26b-a4b-it stays the second model, from a different vendor.
- Hard budget for this amendment's live runs: $1.
