You are grading PR1 (phases P1+P2) of Ledgerline v0.1 in this repo (branch v01, diff main..HEAD). Read builds/v01/plan.md (Definitions, P1, P2 — plus the orchestrator's P2 additions recorded in builds/v01/log.md: max 3 hops, column-to-column comparison filters, column-level REVOKE on users.password_hash/email) and the changed source files. Grade against this bar. For EACH criterion output PASS or FAIL with specific evidence (file/line or behavior). Be strict: if not clearly met, FAIL. Also flag any real bug outside the criteria. Return exactly the JSON specified below, no Markdown or prose.

Criteria:
- L1a: ./verify.sh runs ruff, pyright (strict on ledgerline/core), pytest with zero skips enforced, per-module branch coverage, detect-secrets; the GitHub Actions workflow runs the same script.
- L2: Per-module branch coverage floors: >=95% validate.py and sqlbuild.py; >=85% executor.py and registry_init.py, enforced per module.
- L3: A named passing test exists for every validator rule in plan P2.4 (incl. fan_out and ambiguous_path), and a test fails if any rule code lacks one.
- L4: The sentinel-value Hypothesis property shows filter values only in bound params, never SQL text; injection fixtures leave the DB unchanged; the 30-intent differential oracle passes on Postgres and SQLite against independent reference queries.
- L5: Writes fail and timeouts fire on both engines (Postgres BEGIN READ ONLY + statement_timeout; SQLite mode=ro + progress-handler interrupt); row cap enforced.
- L6: registry init is deterministic, auto-hides sensitive fields, infers relationships when FKs are missing, and loads, on fieldservice and every sampled Spider DB.
- L8: Gold set meets P1.5 counts (>=60 items, >=35 in_schema with >=10 hard, >=12 out_of_schema, >=10 should_refuse), every in_schema gold executes non-empty and deterministic, manifest matches; gold, Spider IDs and ADR predictions were committed before ledgerline/core/intent.py first appears (check git log).
- L11b: Budget guard does a worst-case pre-check before each call, aborts at the cap with a partial outcome, resumes from checkpoint; a replay miss raises without calling the transport.
- L12: No Spider question text or data is committed; fetch script pins a checksum and states the licence.
- L15: No secrets committed; .env.example documents setting an OpenRouter credit limit.
- TEST-CHANGE: Commit ecdaf95 changes an existing test fixture. Check whether any assertion got weaker or would now pass on broken code. PASS only if the guarded behaviour is unchanged.

Output contract:
{"family":"astra","model":"gpt-6-astra","criteria":[{"id":"<criterion id>","criterion":"<exact criterion text>","verdict":"PASS","evidence":"<file:line or test evidence>"}],"findings":[{"likelihood":5,"impact":5,"protected":false,"trigger":"<concrete normal-use input, command or call path>","issue":"<real bug outside the criteria>","file":"<path>","line":"<line>","evidence":"<evidence>"}]}
family, model and a non-empty criteria array are required. findings optional. verdict is exactly PASS or FAIL. likelihood and impact are integers 1-10.
