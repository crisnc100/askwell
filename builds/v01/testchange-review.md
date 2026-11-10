**No existing assertion was weakened. One new assertion has a boolean-type loophole:** `[1] == [True]` passes, confirmed with Python. The strengthened property catches that loophole independently.

| Assertion | Verdict and evidence |
|---|---|
| Sentinel: valid plan exists | **PASS** — unchanged; invalid generated filters still fail. |
| Sentinel: value absent from SQL | **PASS** — retains previous checks; adds boolean literals and both datetime separators. |
| Sentinel: value present in bound parameters | **PASS** — boolean identity rejects integer `0/1`; previous nonboolean comparisons remain. |
| Sentinel: parameter count equals filter-value count | **PASS** — adds detection of missing bindings, including repeated boolean values inlined on SQLite. |
| Boolean regression: plan exists | **PASS** — requires successful validation before compilation. |
| Boolean regression: `list(params.values()) == [True]` | **FAIL** — accepts `[1]`; use length plus `params` value `is True` to enforce the stated exact-boolean contract. This is a new weakness, not weakening of an existing assertion. |
| Boolean regression: no `"true"` in SQL | **PASS** — rejects PostgreSQL’s inline boolean literal. |
| Boolean regression: no `"= 1"` in SQL | **PASS** — rejects the SQLite inline form produced by the original builder. |
| Temporal comparison: plan exists | **PASS** — both operand orders must validate. |
| Temporal comparison: exact expected IDs | **PASS** — checks six operators, both operand orders and engines; midnight equality and later-that-day inequality distinguish proper normalization from date truncation. |
| Alias collision: metric/group collision | **PASS** — requires exactly `["alias_collision"]`, rejecting silent acceptance. |
| Alias collision: duplicate group labels | **PASS** — qualified and unqualified references must produce exactly `["alias_collision"]`. |
| Default labels: group remains `["count"]` | **PASS** — prevents resolving the collision by renaming the group. |
| Default labels: metric becomes `["count_2"]` | **PASS** — rejects the original colliding metric label. |
| First resume: calls are `["q2", "q3"]` | **PASS** — requires retaining earlier progress and completing only missing items. |
| First resume: spend is approximately `0.4` | **PASS** — includes original and resumed work. |
| Second resume: calls are `["q4", "q5"]` | **PASS** — detects unreadable first-resume appends and repeated work. |
| Second resume: resumed count is `4` | **PASS** — requires recovering all four completed entries. |
| Second resume: records equal first six items | **PASS** — checks complete, ordered results. |
| Second resume: spend is approximately `0.6` | **PASS** — requires cumulative accounting across resumes. |
| Fresh checkpoint load: six keys | **PASS** — independently checks durable progress after reopening. |
| Fresh checkpoint load: spend approximately `0.6` | **PASS** — independently checks durable cumulative spend. |
| Append without load: three keys | **PASS** — detects appends stranded behind the torn line. |
| Append without load: spend approximately `0.6` | **PASS** — requires all three persisted costs. |
| Roles: hidden-column queries raise permission denial | **PASS** — tests the read-only connection after two script executions; original blanket grants violate this. |
| Roles: username count equals `25` | **PASS** — prevents blanket access revocation from satisfying the denial checks. |
| Roles: exclusion clause exists | **PASS** — original script lacks the required clause. |
| Roles: excluded columns equal seed denylist | **PASS** — exact set equality rejects missing or extra exclusions. |

Generator coverage retains every original branch; the registry fixture and direct load use the same file. Reviewed source at the specified commit; did not run the test suite.
