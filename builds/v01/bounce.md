**Verdict:** a build can pass all 16 criteria and still disprove the portfolio claim. No criterion sets an accuracy floor, the intent grammar cannot express much of Spider/BIRD, and the scoring rules that decide the headline number are undefined. Fix the eval design before P1; the rest is tractable.

Items marked *(unverified)* rest on my memory of external tools and datasets, not on anything checked this session.

## 1. Eval validity (sinks the claim)

1. **No accuracy threshold.** L9/L10 need only a report that exists and reproduces, so Ledgerline at 5% passes. Misses are not triaged (grammar gap, misread, builder bug, bad gold), so a builder bug hides as model error.
2. **Grammar vs benchmarks.** The intent has no HAVING, subqueries, set ops, OR, neq/gt/lt/like, ratios, computed fields or DISTINCT. Spider and BIRD lean on these *(unverified proportions)*, and every inexpressible question scores as a wrong refusal. Without coverage reported apart from accuracy-given-coverage, the table says "agent wins" and cannot say why.
3. **The subset filter is a loophole.** Every Spider/BIRD question already targets one database, so "answerable from one database" is either a no-op or licence to filter toward what Ledgerline can do. The selection rule, seed and difficulty stratification are not frozen before `intent.py`.
4. **The gold freeze proves little.** P2.3 already publishes the grammar, and the same builder writes both. L8 checks first-commit order only; later edits to the gold file go undetected.
5. **Gold quality is unconstrained.** Nothing requires a difficulty mix, that `gold_sql` executes, or that results are non-empty and deterministic. An empty gold result matches any wrong filter.
6. **Refusal categories are undefined.** The plan does not say how `out_of_schema` differs from `should_refuse`, or what `gold_sql` means for a refusal item. Always-refuse scores 100% on 40% of the set.
7. **The governance metric is missing.** There is no false-refusal rate and no wrong-answer-given-answered rate, the one place a governed system should win.
8. **Baseline scoring is undefined.** The agent returns prose. How a refusal is detected and which SQL and rows get scored decides the comparison.
9. **Result comparison is undecided.** Open cases: extra columns, column matching when order is ignored, ORDER BY questions, Decimal vs float, NULL vs 0, SQLite date strings, and the row cap against unbounded gold. Each moves the number.
10. **Unequal inputs.** The plan does not say whether the baseline sees the curated registry's descriptions and aliases, or whether BIRD evidence hints go to both systems.
11. **Sample size.** With about 27 in-schema fieldservice questions and 50 per benchmark, one question is 2–4 points. There is a single trial, temperature is unstated, and no intervals are reported.
12. **Soft-target baseline.** A LangChain agent on cheap models with weak tool calling reads as a strawman. A one-shot schema-in-prompt baseline, which a sceptical hiring manager will ask for, is absent.
13. **Invalid-SQL rate is meaningless.** It is about 0 for Ledgerline by construction and undefined for a self-retrying agent.
14. **Two claims are unverifiable.** Nothing regenerates or hashes the Spider/BIRD registries to prove "no hand edits". ADR predictions can be written after the results.

## 2. Will break during the build

15. **Replay key fragility.** Today's date in the prompt (needed for "last month") causes a miss tomorrow. There is no frozen "now" for the seeder, the prompt or the gold results.
16. **Baseline replay.** The agent's messages contain DB rows, so unordered rows change the hash and CI flakes. The gateway spec covers structured output only; wrapping the tool-calling path is unspecified and the hardest part.
17. **L9 is a tautology.** It checks scorer determinism, not correctness. Any re-record changes the numbers, and there is no re-record workflow.
18. **Structured output on cheap OpenRouter models.** Support varies by model and upstream provider *(unverified)*. There is no provider pinning and no path for unparseable output.
19. **Budget guard cannot know cost before the call.** It needs a worst-case pre-check; the fake-meter test proves arithmetic only. It also does not cover dev iteration, `/ask` or repeated runs, and no OpenRouter key credit limit is named as a backstop.
20. **Aborted runs are undefined.** There is no partial-report, resume or 429 backoff behaviour. An "equal budget" cuts off the agent first, since it makes several calls per question.
21. **`registry init` on real schemas.** Spider SQLite files often lack declared FKs *(unverified)*, and SQLite dates are TEXT. Identifiers with spaces or dots break `entity.field`, and descriptions are empty.
22. **SQLite has no `statement_timeout`.** L5 does not name an engine, so one cartesian join from the agent hangs the run.
23. **Calendar grains differ by dialect.** Postgres `date_trunc` and SQLite `strftime` disagree on week and quarter, and there is no cross-dialect test.
24. **Fetch and licence.** Official downloads are flaky large archives *(unverified)* with no checksum pin. Listing baseline-win question text commits CC BY-SA content to an Apache repo; cite by ID.
25. **Replay UI.** A cloner with no key who types their own question gets a replay miss. P5 has no canned-question list.
26. **CI cannot run.** There is no remote and `gh` is not logged in, so every "in CI" criterion (L1, L9, L16) is unverifiable at acceptance.
27. **Skipped tests count as passes.** Postgres tests may skip when the DB is absent, and there is no zero-skips rule.
28. **Stack list is already incomplete.** Faker, a YAML parser and an ASGI server are needed but not listed, so the callback rule fires in P1.

## 3. Correctness holes in the core

29. **Fan-out double counting.** `work_orders` is 1–N to both `work_order_parts` and `invoices`, so a sum across that join inflates. The result is validated, auditable and wrong, the worst failure for this product.
30. **Ambiguous join paths.** Multiple FKs between two tables, self-references and competing 2-hop paths have no defined choice.
31. **Validator rule gaps.** Missing rules:
    - value type vs field type (surfaces as a DB error, not a typed one)
    - operator vs type
    - the `filterable`/`aggregatable` flags, which nothing enforces
    - `intent_type` vs populated fields
    - `row_list` has no column list, so "empty select" refers to nothing
    - limit ≤ 0, empty `in`, reversed `between`
    - `date_range` duplicating gte/lte, and which date column it applies to
32. **Free-text values.** "Austin" vs "austin" silently returns empty. The agent can peek at rows; Ledgerline cannot. Stale allowed-value snapshots cause false refusals.
33. **Default data leak.** "≤50 distinct" captures names and emails from small tables into the YAML and every prompt sent to OpenRouter. No field can be hidden, so `password_hash` is queryable.
34. **Read-only role.** `ledgerline_ro` exists only in the seeded DB. On a user's URL the executor runs as whatever role was supplied.
35. **"Auditable" with no audit record.** `trace_id` points at nothing persisted.
36. **Undefined pieces.**
    - `present`: if it is an LLM call, it sends rows to OpenRouter and can hallucinate numbers.
    - `draft: true` has no stated effect.
    - Where view SQL lives is unstated; if in YAML, it breaks the identifiers-only invariant.
    - What "capped by size" drops is unstated.
    - Who resolves "last quarter" is unstated.
    - The `schema_id` → registry + DB URL mapping is unstated.

## 4. Acceptance bar too weak

- **L2:** line coverage only. `--cov-fail-under` applies to the combined total, not per module *(unverified)*. The executor and `registry init` have no bar.
- **L4:** "no filter value appears in SQL text" false-fails on values like `1` (`LIMIT 1`), so the generator will be narrowed until green. There is no semantic oracle for the builder; a wrong join passes L2–L5.
- **L3:** one test per listed rule, so the gaps in item 31 are invisible.
- **L6:** one builder-picked Spider DB. It should cover every sampled DB.
- **L7:** no init → ask test on a foreign DB, which is the developer audience's whole journey.
- **L10:** verified by self-produced artifacts.
- **L13/L15:** absent from `verify.sh`, which only builds.
- **L1:** pyright mode and ruff rules are unspecified.
- **L11:** fake meter only.

## 5. Over-built for solo / $50

- **Next.js + Dockerfile + Playwright** for one read-only trace screen adds a second toolchain. A static page served by FastAPI shows the same thing.
- **BIRD:** given item 2, it adds a near-zero row and the largest download. Spider's five databases already satisfy "≥3 schemas".
- **Small extras:** registry views, a separate `values refresh` command, model tiers, the price-table fallback.
- **Docs volume:** `build-log.md` is a journey doc, against the "docs describe now" rule. Recruiters read the README, the table and perhaps two ADRs.
- **LangGraph** for a linear pipeline with one retry is a for-loop. Keep it only as a keyword, and keep it thin.
- **Not over-built:** replay, budget guard, Hypothesis, secret scan.

## 6. Process

- **One PR:** "phases stack" argues for sequential PRs, not one. P1+P2 merged alone leaves main working. One PR bundles the security core with Next.js and docs, against the "risky apart from routine" rule.
- **Two seed paths:** the quickstart's `uv run ledgerline seed` and the compose seed job.
