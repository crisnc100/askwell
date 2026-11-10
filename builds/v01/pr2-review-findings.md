## slice 2026-11-10-13-49-02-7c4d83 f1 (medium) ledgerline/pipeline/service.py:226
Concurrent asks replace each other's budget guard. FastAPI shares one AskService across request threads, so a second request can reset the guard between the first request's initial attempt and retry. Using a fake transport and the real gateway, I reproduced an ask completing with cost_usd=0.04 despite its 0.03 per-ask cap. Charges are also attributed to the other request's guard.
Trigger: Two concurrent /ask requests in record or live mode overlap while one request retries.
Evidence: 

## slice 2026-11-10-13-49-02-7c4d83 f2 (medium) ledgerline/core/sqlbuild.py:153
Calendar grains silently collapse YYYYMMDD integer dates into NULL. This storage pattern is documented for the selected wta_1 database in spider:479's triage. Reproducing it with registry init on an in-memory SQLite database, three rows dated 20010203, 20010204 and 20010204 validated successfully but grouped into [(None, 3)] instead of two date groups. LenientDate prevents decoding failures but does not make SQLite's date functions understand this encoding.
Trigger: An accepted intent groups a YYYYMMDD integer-backed DATE field, such as wta_1.ranking_date, by a calendar grain.
Evidence: 

## slice 2026-11-10-13-49-02-7c4d83 f3 (medium) ledgerline/pipeline/graph.py:70
A retry overwrites the first answer's provenance, and Attempt does not retain it. Consequently, answering the initial export with simulator A and its retry with simulator B makes the trace and eval record credit only B. If the retry has no simulation provenance, the report can omit its simulated banner entirely. A two-attempt graph reproduction with simulated first-answer provenance ended with provenance=None.
Trigger: An initial answer and its retry come from recordings with different provenance, such as separate simulation import rounds.
Evidence: 

## slice 2026-11-10-13-51-10-f09a2c f1 (medium) ledgerline/bench/systems.py:214
A schema-valid oneshot answer containing comment-only SQL aborts the entire eval. I reproduced `ResourceClosedError` with `sql="-- no query can answer this question"` against read-only Spider SQLite. This exception escapes the ExecutionError handler and is re-raised by run_checkpointed instead of becoming an item-level execution error.
Trigger: Import a oneshot answer whose nonempty sql contains only a comment, then run the replay eval.
Evidence: 

## slice 2026-11-10-13-51-10-f09a2c f2 (medium) ledgerline/bench/run.py:57
Checkpoint identity excludes the question and gold SQL, so resuming can silently reuse obsolete scores. I verified that changing both while retaining the item ID produces the same key, and run_checkpointed returns the old outcome without invoking scoring. A gold correction such as revision 2 therefore leaves existing run results stale unless the checkpoint is manually removed.
Trigger: Complete an eval, correct an existing gold question or SQL without changing its ID, then rerun the same run ID.
Evidence: 

## slice 2026-11-10-13-51-10-f09a2c f3 (medium) ledgerline/bench/report.py:51
The acceptance floor is checked against the first Ledgerline model row rather than the configured default model required by L11. Because build sorts rows by model ID, a secondary model can determine whether the release passes. I reproduced opposite verdicts by reversing two model rows with passing and failing accuracy.
Trigger: Run the fieldservice eval with two models whose scores straddle the acceptance floor and whose secondary model ID sorts before the default.
Evidence: 

## slice 2026-11-10-13-51-10-f09a2c f4 (medium) ledgerline/bench/run.py:93
A configured Spider schema bypasses registry regeneration and the committed-hash check entirely. I verified that registering spider_car_1 makes _schemas return it without calling schema_for, with an empty registry_hashes result. An edited registry can consequently influence benchmark results without the required drift rejection or report hash.
Trigger: Register spider_car_1 in config/schemas.yaml for asking questions, edit its registry, then evaluate --schema spider_car_1.
Evidence: 

## slice 2026-11-10-13-51-10-f09a2c s1 (high) ledgerline/bench/systems.py:211
Model-written SQL can escape the read-only transaction and disable the database login. A valid OneShotAnswer can contain `ROLLBACK; BEGIN READ WRITE; ALTER ROLE CURRENT_USER PASSWORD NULL; COMMIT; SELECT 1`. The executor takes its non-streaming path, and psycopg sends the entire batch. PostgreSQL permits ordinary roles to change their own password ([documentation](https://www.postgresql.org/docs/16/sql-alterrole.html)), so SELECT-only table grants do not prevent this. The explicit COMMIT persists the change before the executor's final rollback, blocking subsequent password-authenticated connections for Ledgerline and its users. Schema acceptance, unchanged SQL compilation and simple-protocol dispatch were verified locally. End-to-end execution remains unverified — sandbox networking blocked PostgreSQL access. HIGH because this crosses an exploitable security boundary.
Trigger: An attacker-controlled simulated model answer containing the SQL batch is imported, then executed by the fieldservice one-shot replay evaluation using the configured ledgerline_ro login.
Evidence: 

## slice 2026-11-10-13-40-01-815753 f1 (high) tests/bench/test_run.py:181
monkeypatch.undo() removes the isolated fixture's directory patches as well as PROMPT_VERSION, because they share the same MonkeyPatch instance. I confirmed that RUNS_DIR, EVAL_RECORDINGS and EVAL_PENDING revert to repository paths. The final export therefore uses a different checkpoint and writes fixture requests into the real pending directory. On a clean checkout, its assertions pass even if registry changes do not invalidate checkpointed results.
Trigger: Run test_changing_the_prompt_or_registry_never_resumes_old_results with the seeded database, including through the full test suite.
Evidence: 

