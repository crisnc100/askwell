## f2 (medium) ledgerline/core/sqlbuild.py:288
Unconditional INNER JOINs change OR-filter semantics across nullable relationships. On the actual seeded fieldservice data, counting work orders where priority='urgent' OR technicians.skill_level='senior' validates successfully but returns 1,874 instead of 1,893: the join discards 19 urgent orders without technicians before evaluating the OR.
Trigger: Validate and execute a work_orders summary with any_of containing a base-field predicate and a technicians-field predicate.
Evidence: 

## f3 (medium) ledgerline/core/sqlbuild.py:224
SQLite datetime filters depend on the database having SQLAlchemy's exact timestamp serialization. After registry init on a DATETIME column containing equivalent values '2026-06-01 10:30:00' and '2026-06-01 10:30:00.000000', an equality filter for that instant returns only the latter. A less-than filter incorrectly returns the former because the comparison is textual.
Trigger: Initialize a registry from an existing SQLite database storing DATETIME values without fractional seconds, then filter by an equal datetime or a range boundary.
Evidence: 

## f4 (medium) ledgerline/core/sqlbuild.py:49
All reflected integer types, including BIGINT, become SQLAlchemy Integer. Explicit parameter typing then narrows valid 64-bit values to PostgreSQL's 32-bit INTEGER. A validated id=7000000001 filter compiles as id = %(param_1)s::INTEGER, which cannot represent that value; the same plan successfully retrieves the row on SQLite.
Trigger: Use registry init on a PostgreSQL BIGINT column, then filter by a value outside the signed 32-bit range.
Evidence: 

## f5 (medium) ledgerline/core/registry_init.py:169
Inference runs on columns whose declared foreign keys were deliberately skipped. Reproduced with addresses.code_id REFERENCES countries(code), where code is UNIQUE rather than the primary key, and an unrelated codes table: initialization warns about skipping the declared key, then invents addresses.code_id → codes.id. Validation subsequently accepts queries through that incorrect relationship.
Trigger: Initialize a registry where an unsupported declared foreign key has a source name that also matches another table's inferred naming convention.
Evidence: 

## f6 (medium) ledgerline/core/validate.py:423
Case-insensitive categorical resolution can replace an exact canonical value with a different stored value. registry init permits allowed_values=['A','a']; filtering for 'a' then binds 'A'. In the reproduced database this returns 2 rows instead of the 4 rows actually containing 'a'.
Trigger: Use registry init --values on a case-sensitive categorical column containing distinct values that differ only by case, then filter for the later canonical value.
Evidence: 

## f7 (medium) ledgerline/core/executor.py:104
Connection acquisition happens outside the error wrapper. If the database connection fails, run raises the raw SQLAlchemy OperationalError rather than ExecutionError, so Executor.execute bypasses its error-audit path. Reproducing a failed connection with an enabled AuditLog leaves zero audit records.
Trigger: Execute a validated plan while the configured data database is unavailable or rejects the connection.
Evidence: 

## f8 (medium) ledgerline/core/validate.py:731
HAVING validation checks metric names but not aggregate result types. A grouped min(invoices.issued_at) with a numeric HAVING threshold passes validation, then fails during binding with 'SQLite Date type only accepts Python date objects'. Temporal min/max metrics are supported, so incompatible operands need a typed rejection.
Trigger: Validate a grouped temporal min/max metric with a numeric HAVING value, then execute the accepted plan.
Evidence: 

