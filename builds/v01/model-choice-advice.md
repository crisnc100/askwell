## 1. SCOPE VERDICT

**Under-scoped** — "real benchmark decides, ignore the 2/5" is right, but the stop rule is tied to a floor no model can pass, and the length-limit bug sits in the gateway, not the spike.

## 2. ADVISORY

**Keep: do not change models on the spike result.** The report backs this:
- Probes 0 and 4 were missed by all six models, and probes 1–3 by exactly three of six each. A gold that no model from five vendors matches is measuring the gold.
- The report stores no model answer (`spike.py:89-96`), so nobody can say which field differed. Add the returned value to the report; that is the only spike change worth making.
- All three pre-registered predictions held: five models honoured 5/5, glm-5.3-flash failed a probe with invented keys, and spend was $0.001.

**Change the pass bar: L11 cannot select a model.**
- Of the 43 answerable questions, 8 need things the intent grammar cannot express (ratio, date difference, computed value, anti-join; `sim-1.md:40-47`).
- That caps execution accuracy at 35/43 = 81.4% for any model. Clearing 80% needs a perfect score on everything else, including two ambiguous-date questions (fs-022, fs-024).
- "Step up until one passes" therefore walks the whole ladder and ends with no rule. Keep L11 as the product floor, report it honestly, and select on a separate rule.

**Proposed selection rule** (the thresholds are my proposals):
- **Gates:**
  - Unreadable answers are at most 2% of model calls.
  - Refusal recall is at least 23/24 per trial.
  - p50 latency is at most 3 s.
- **Pick:** the cheapest model by measured cost per question that is not clearly worse than the best eligible one. "Clearly worse" means 4 or more questions of 43 behind on accuracy, or the same margin worse on wrong answers.
- **Exhaustion:** if nothing passes the gates, ship the best rung and say so. Never step to frontier.

**The unreadable-answer gate is required, not optional.** An answer that fails to parse twice becomes a refusal (`graph.py:77`), so a model that emits bad JSON scores perfect refusal recall and zero wrong answers. The spike does not cover this:
- Its schema is 670 characters, flat, with every field required.
- `Intent` is 4,998 characters with 20 `anyOf` and 9 `$ref`.
- The transport runs `strict=False` (`gateway.py:210`).

**Run the ladder in one command instead of stepping.** By my arithmetic, not a measurement, one fieldservice trial is about 87 calls of roughly 3k prompt tokens. That is about $0.01 on mistral-small, and under $1 for four models × three trials. Running all four also gives the comparison that defines "clearly worse".

**Fix the length-limit crash in the transport, not the spike.**
- `openai.LengthFinishReasonError` is not an `LLMError`, and it escapes at `gateway.py:256`.
- It aborts the eval (`budget.py:195`), and the API has no handler for it (`api.py:101-105`).
- It is raised before `budget.charge` (`gateway.py:180`), so a call billed at the full token cap is counted as $0. That leaks through PR5's daily cap.
- Catch it in the transport, charge `exc.completion.usage`, and raise `ParseError`. The spike then needs no change (`spike.py:182-191`), and Docket's ADR-001 already describes this behaviour.
- Production `max_tokens` is 1024 (`config.py:69`). The spike crashed at 300 on a five-field task, so gpt-oss on the real prompt may hit it.

**Reasoning models: let the gates decide, and rank by measured cost.**
- gpt-oss-120b cost 6.4× mistral-small on identical probes, with p50 latency of 4.7 s against 0.86 s.
- gpt-oss-20b cost more than 120b ($0.00038 against $0.00021), so list price is not the cost.
- With one retry, 120b can take 16 s per question. The 3 s gate would exclude it without naming it.
- The interim default is still gpt-oss-120b (`config.py:59`), chosen on list price.

**Add the re-record work to PR5.** A new default changes every recording key (`ADR-004:18`), and the CI replay check reads `default_model` (`check_replay_report.py:36`). Run the selection in `--mode record` so it produces the new recordings, then rewrite the replay report.

**Use Spider as the tie-breaker for the two finalists.** Its auto-drafted registries are what uploaded workspaces get; fieldservice's hand-written registry is the easy case. L10 already requires the live Spider run.

**Amend ADR-004 by appending, not editing.**
- Leave the procedure and predictions as written.
- Fill in Result: predictions 3/3 held; step 3 produced no winner, with the best exact score 2/5.
- Record the deviations: the crash at 300 tokens, the rerun at 2000, and the report missing from `evals/spike/`, which does not exist yet. Commit the report there.
- Add a dated amendment with the new rule, ladder and thresholds, and commit it before the live run so `git log` proves the order.

**One rule across the three projects, not one model.**
- Docket uses `strict=True`, a 256-token cap and a per-call enum, pinned to gpt-4o-mini (`docket/llm/gateway.py:71,105`).
- Firstcall has its own floors and a p95 ≤ 6 s condition (`plan.md:365-377`). Its ladder has the same missing exhaustion rule.
- Share the ladder and the rule. Report measured cost per task next to the model id; that is what makes cost figures comparable.

**Cut:**
- Per-field scoring on the triage probes.
- A spike rerun.
- Sequential stepping.
- Any reasoning-effort setting.
- Forcing one model on all three projects.

## 3. QUESTIONS

1. **If the real model also misses L11 (likely, given the 81.4% ceiling), does the hosted beta still ship with "not met" published?** Recommended: yes. The fix is the v0.2 grammar and prompt, not a bigger model.
2. **Is p50 ≤ 3 s the right latency ceiling for the beta?** Recommended: yes. It effectively rules out gpt-oss-120b as the default.
3. **Is a mini-class model (Docket's current gpt-4o-mini tier) the top of the ladder?** Recommended: yes, cap it there. If nothing passes the gates, ship the best rung and report it.
