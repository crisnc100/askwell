# ADR-002: LangGraph orchestrates one linear graph; nothing more

- **Status:** Proposed. Prediction committed 2026-11-09 (P1).
- **Result:** recorded 2026-11-11 from the simulated run `sim-1` (see Result).

## Context
The pipeline is interpret → validate → (one retry with the typed errors) → execute →
present. That is a loop with one branch. Agent frameworks invite tool-calling LLMs,
LLM-written summaries of result rows, and hidden state, each of which would weaken the
governance claim (rows sent to a third party, numbers paraphrased by a model).

## Decision
LangGraph is the orchestration layer and nothing else: a fixed graph with typed state.
The only LLM call is `interpret`. `present` is deterministic (columns, rows, formatted
SQL); no result rows are ever sent to OpenRouter. No node gives the model tools.

## Prediction (pre-registered)
1. The graph module stays under 150 lines, and replacing it with a plain Python loop
   would change no eval number (the graph adds no behaviour of its own).
2. The single retry turns 25–50% of first-attempt validation failures into valid intents
   on fieldservice, and adds at most 20% to mean cost per question.
3. A second retry would add under 3 points of execution accuracy (checked once, offline,
   by replaying first-retry failures), which is why the graph allows only one.

## Result
Measured on the eval run `sim-1` ([evals/reports/sim-1.md](../../evals/reports/sim-1.md)). Its model answers were **simulated**: claude-haiku-5-5 answered every request as a stand-in for `openai/gpt-oss-120b`, because there is no OpenRouter key yet. A simulated run tests the pipeline and the scoring; it does not measure the target model. One trial.

1. **The graph module stays under 150 lines:** wrong. `askwell/pipeline/graph.py` is
   171 lines. About 35 of them declare the typed state the nodes pass along (each attempt's
   answer, intent, issues and where the answer came from), which the trace view and the
   audit log need. The graph still has five fixed nodes, one model call and no tools.
   **A plain Python loop would change no eval number:** not measured. No loop version was
   built to compare.
2. **The retry fixes 25–50% of first-attempt failures:** on fieldservice, 3 of 3 first
   answers that failed the check were valid on the retry, and all 3 then matched the gold
   (fs-033, fs-034, fs-038). That is above the predicted range, but 3 cases say little. On
   the 5 Spider databases, 6 of 41 retries became valid intents (15%, below the range):
   5 correct and 1 wrong. **Cost added by the retry:** not measured. Simulated answers cost
   nothing.
3. **A second retry would add under 3 points:** not measured. The replay of first-retry
   failures was not run.
