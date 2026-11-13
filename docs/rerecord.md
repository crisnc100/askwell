# Re-recording model answers

Askwell's tests, CI and demo never call a model. They replay **recordings**: saved model
answers, each stored under a key built from the model id, the prompt version, the exact
messages and the response schema. This page explains when the recordings go stale and how
to make new ones.

## When to re-record

A recording is found only if the request is byte-for-byte the same. Re-record after any
change that alters what the model is sent:

- the prompt text or `PROMPT_VERSION` (`askwell/pipeline/prompt.py`, `askwell/bench/systems.py`)
- a registry (`registries/fieldservice.yaml`) or the registry view in the prompt
- the `Intent` or `OneShotAnswer` model, because its JSON schema is part of the request
- the target model (`ASKWELL_DEFAULT_MODEL`)
- a canned example question (`config/schemas.yaml`) or a gold question

You will know: replay mode stops with `ReplayMissError`, and `./verify.sh` fails the step
"replay eval reproduces the committed report".

## Today: answers are simulated

There is no OpenRouter key yet. A Claude model writes each answer instead, standing in for
the target model. Every simulated answer is stored with
`{"simulated_by": ..., "standing_in_for": ...}`, and every report built from them says so on
its first line.

### Eval recordings

1. **Export** every request that has no recording:

   ```sh
   uv run askwell eval --all --systems ledgerline,oneshot --mode export --trials 1 --run-id sim-1
   ```

   Each request lands in `evals/pending/eval/<schema>/<system>/<key>.json`. The command
   prints how many are pending per schema and system.

2. **Answer** each request. For every `<key>.json`, write `<key>.answer.json` next to it:

   ```json
   {"key": "<key>", "simulated_by": "<claude model id>", "response": { ... }}
   ```

   The answerer sees only that request file: the system prompt, the messages and the
   response schema. It never sees the gold, the code or the database. If the honest answer
   is not a JSON object, use `"response_text": "..."`; it replays as a parse error, just like
   a real model's bad output would.

3. **Import** the answers:

   ```sh
   uv run askwell eval --mode import
   ```

   An answer that breaks the response schema is rejected, kept on disk and listed, so it
   can be fixed and imported again.

4. **Export again.** An Askwell answer that failed validation gets one retry, which is a
   new request. Repeat steps 2–3 until the export reports nothing pending. There is never a
   third round: the pipeline retries once.

5. **Replay** and write the report:

   ```sh
   uv run askwell eval --all --systems ledgerline,oneshot --mode replay --trials 1 --run-id sim-1
   ```

   The report lands in `evals/reports/sim-1.md` and `.json`. Delete `evals/runs/sim-1/`
   first if you want a clean re-score (the run resumes from its checkpoint otherwise).

   After changing a prompt or a registry, start a **new run id** (for example `sim-2`).
   A run never reuses a result made with a different prompt version or registry (both
   are part of each checkpoint key), so the old checkpoint would only hold results that
   no longer count.
   Tag every Askwell miss in `evals/triage/<schema>.yaml`.

Spider recordings stay on your machine (`evals/recordings/eval/spider_*/` is gitignored),
because answers can quote Spider data. Only the fieldservice recordings are committed.

### The committed replay report

CI checks that replaying the committed fieldservice recordings reproduces
`evals/reports/replay-fieldservice.md`. After re-recording fieldservice, rewrite it:

```sh
uv run python -m scripts.check_replay_report --write
uv run python -m scripts.check_replay_report   # should print "reproduces"
```

### Demo and API recordings

The canned example questions (`config/schemas.yaml`) and the Spider init → ask test have
their own store, `evals/recordings/interpret.jsonl`:

```sh
uv run python -m evals.replay_cases export   # writes evals/pending/<key>.json
# answer each request as above, then:
uv run askwell replay import
uv run python -m evals.replay_cases export   # again, for any retry requests
```

## Once there is a key: live runs

Set `OPENROUTER_API_KEY` in `.env`. First, set a credit limit on the key at
https://openrouter.ai/settings/keys; it is the backstop if anything else fails. Then use
`--mode record` instead of export/import: it calls OpenRouter and saves each answer as a
recording in one step.

```sh
uv run askwell eval --all --systems ledgerline,oneshot --mode record --trials 1 --budget 2 --run-id live-1
```

`--budget` is a hard cap for the whole run, in US dollars. Before each call, the run checks
that what it has spent plus that call's worst case (prompt bytes × prompt price + the
completion cap × completion price) stays under the cap, and stops cleanly if it would not.
Re-running the same `--run-id` resumes and counts what was already spent.

**What it costs** (estimate, from OpenRouter's listed price for `openai/gpt-oss-120b` on
2026-11-09: $0.15 per million prompt tokens, $0.60 per million completion tokens):

| Run | Calls | Typical cost | If every call hit its caps |
|---|---|---|---|
| One full run like sim-1 (6 schemas, 2 systems, 1 trial) | about 680 | about $0.40 | about $1.50 |
| plan.md's full live run (adds the sql_agent baseline and 3 fieldservice trials) | about 4,500 | about $3 | about $10 |

A typical call sends about 3,000 tokens and gets about 200 back. The sql_agent baseline
makes several calls per question (one per tool step), which is most of the second row.
The plan's second model is not priced here; add its run once it is chosen. Use
`--budget 5` for the full live run, the plan's cap. Check prices on OpenRouter's models
page before a large run; they change.
