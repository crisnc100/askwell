Recheck ONLY these criteria from the earlier PR2 grade of this repo (branch pipeline). Fixes since: 7c509da (tests), c953f37, f0caef1, 8f8945f, 21d1d31, 3ed2b17, a59ad78, 3a22c62 (tests). Read the changed code and tests. PASS or FAIL per criterion with evidence. Be strict. Keep criterion ids and text unchanged. Flag any real bug introduced by the fixes.

Criteria:
- PIPE: present is deterministic and no result rows are ever sent to the model (test); relative dates resolved by code; hidden fields never in the prompt; interpret prompt truncation deterministic.
- L9: the replay eval reproduces the committed fieldservice replay report inside verify.sh; docs/rerecord.md (or equivalent) documents re-recording.
- SIMRPT: the report's first line states it is simulated with simulator and target model; notes state sql_agent not run, one target model, trials=1 with reasons; every Ledgerline miss is triaged (no untriaged); Spider items cited by ID only, with no Spider question text or data committed; Spider registries are unedited registry init output checked by hash.
- METRICS: coverage, execution accuracy, accuracy given attempted, false-refusal, wrong-given-answered, refusal recall and Wilson 95% intervals are computed as defined in plan.md Definitions, and result comparison follows the stated rules.
- EXPORT: gateway export/import validates imported answers against the request schema, records provenance per answer, and a replay miss never calls a live transport.

Return exactly this JSON, no prose:
{"family":"astra","model":"gpt-6-astra","criteria":[{"id":"<id>","criterion":"<exact text>","verdict":"PASS","evidence":"<evidence>"}],"findings":[{"likelihood":5,"impact":5,"protected":false,"trigger":"<trigger>","issue":"<issue>","file":"<path>","line":"<line>","evidence":"<evidence>"}]}
findings optional; likelihood/impact integers 1-10.