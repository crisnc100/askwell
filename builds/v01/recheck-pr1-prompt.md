Recheck ONLY these criteria from the earlier PR1 grade of this repo (branch v01). Fixes were committed since: e82b323 (tests), 4a02324, 7b07d6a, 5dfd720, a1ff012, 7c73c17. Read the changed code and tests. For EACH criterion output PASS or FAIL with specific evidence. Be strict. Keep criterion ids and text unchanged. Also flag any real bug introduced by the fixes.

Criteria:
- L4: The sentinel-value Hypothesis property shows filter values only in bound params, never SQL text; injection fixtures leave the DB unchanged; the 30-intent differential oracle passes on Postgres and SQLite against independent reference queries.
- L8: Gold set meets P1.5 counts (>=60 items, >=35 in_schema with >=10 hard, >=12 out_of_schema, >=10 should_refuse), every in_schema gold executes non-empty and deterministic, manifest matches; gold, Spider IDs and ADR predictions were committed before ledgerline/core/intent.py first appears (check git log).
- L11b: Budget guard does a worst-case pre-check before each call, aborts at the cap with a partial outcome, resumes from checkpoint; a replay miss raises without calling the transport.

Note for L8: your sandbox cannot reach Postgres. The orchestrator ran the gold-executes suite on HEAD in this session; its output is in builds/v01/gold-recheck.txt and the full verify run in builds/v01/verify-recheck.txt. Use those plus reading tests/test_gold.py as evidence.

Return exactly this JSON, no prose:
{"family":"astra","model":"gpt-6-astra","criteria":[{"id":"<id>","criterion":"<exact text>","verdict":"PASS","evidence":"<evidence>"}],"findings":[{"likelihood":5,"impact":5,"protected":false,"trigger":"<trigger>","issue":"<issue>","file":"<path>","line":"<line>","evidence":"<evidence>"}]}
findings optional; likelihood/impact integers 1-10.