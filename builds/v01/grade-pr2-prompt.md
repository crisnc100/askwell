You are grading PR2 (phases P3+P4) of Ledgerline v0.1 in this repo (branch pipeline, diff v01..HEAD). Read builds/v01/plan.md (Definitions, P3, P4, and the 2026-11-09 simulation decision near the end) and the changed files. Evals ran on SIMULATED model answers by decision; the live OpenRouter run (L10) and the sql_agent baseline are deferred and are not criteria here. Your sandbox may not reach Postgres; where a check needs it, read the test and use evals/reports/ and verify.sh wiring as evidence. Grade strictly: PASS or FAIL per criterion with evidence; flag real bugs outside the criteria. Return exactly the JSON specified, no prose.

Criteria:
- L7: POST /ask returns {intent, validation, sql, params, rows, columns, refusal, trace_id, cost_usd}; replay API tests cover answerable, out-of-registry refusal, hidden-field refusal, write refusal, retry-then-success (scripted double, labelled), and init -> ask on a Spider DB; ask_log is written; unrecorded question returns a clear 409.
- PIPE: present is deterministic and no result rows are ever sent to the model (test); relative dates resolved by code; hidden fields never in the prompt; interpret prompt truncation deterministic.
- L9: the replay eval reproduces the committed fieldservice replay report inside verify.sh; docs/rerecord.md (or equivalent) documents re-recording.
- SIMRPT: the report's first line states it is simulated with simulator and target model; notes state sql_agent not run, one target model, trials=1 with reasons; every Ledgerline miss is triaged (no untriaged); Spider items cited by ID only, with no Spider question text or data committed; Spider registries are unedited registry init output checked by hash.
- METRICS: coverage, execution accuracy, accuracy given attempted, false-refusal, wrong-given-answered, refusal recall and Wilson 95% intervals are computed as defined in plan.md Definitions, and result comparison follows the stated rules.
- L11REC: the floor check is computed from the numbers and reported as not met with cause and planned fix; ADR-001 records prediction vs result; the gold change (revision 2) is logged in the CHANGELOG with a reason and the manifest matches.
- EXPORT: gateway export/import validates imported answers against the request schema, records provenance per answer, and a replay miss never calls a live transport.

Output contract:
{"family":"astra","model":"gpt-6-astra","criteria":[{"id":"<criterion id>","criterion":"<exact criterion text>","verdict":"PASS","evidence":"<evidence>"}],"findings":[{"likelihood":5,"impact":5,"protected":false,"trigger":"<trigger>","issue":"<issue>","file":"<path>","line":"<line>","evidence":"<evidence>"}]}
findings optional; likelihood/impact integers 1-10; verdict exactly PASS or FAIL.
