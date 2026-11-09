# ADR-002: LangGraph orchestrates one linear graph; nothing more

- **Status:** Proposed. Prediction committed 2026-11-09 (P1).
- **Result:** PENDING.

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
PENDING.
