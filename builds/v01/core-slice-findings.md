## f1 (medium) ledgerline/core/sqlbuild.py:277
SQLite datetime normalization is skipped outside literal filters. Reproduced: equivalent DATETIME columns compare unequal; MAX over '2026-06-01T09:00:00' and '2026-06-01 12:00:00' returns 09:00; ascending ordering reverses those rows; grouping three representations of the same instant produces three separate groups. DISTINCT aggregates have the same underlying problem.
Trigger: Initialize a registry from an existing SQLite database containing DATETIME values with mixed supported text formats, then compare columns, aggregate, group or order those fields.
Evidence: 

## f2 (medium) ledgerline/core/sqlbuild.py:337
Numeric HAVING thresholds inherit the aggregate's integer binding type. Compilation of count > 1.5 produces count(*) > %(param_1)s::INTEGER with parameter 1.5. PostgreSQL rounds that threshold to 2, incorrectly excluding groups containing two rows. Integer SUM/MIN/MAX thresholds similarly receive BIGINT casts, and large count thresholds can overflow INTEGER.
Trigger: Compile and execute a grouped PostgreSQL intent with a fractional HAVING threshold on count or an integer aggregate, such as count > 1.5.
Evidence: 

## f3 (medium) ledgerline/core/registry_init.py:135
Declared foreign keys are resolved using only a lowercased table name, discarding schema and quoted-case identity. Feeding reflected metadata for orders.customer_id REFERENCES archive.customers(id), with public.customers also introspected, creates a declared relationship to public.customers without warning. A reference to quoted "Customers" is likewise redirected to customers when both exist. Subsequent queries silently join the wrong table.
Trigger: Run registry init against PostgreSQL where a foreign key targets another schema containing a table name also present in the default schema, or where quoted table names differ only by case.
Evidence: 

## f4 (medium) ledgerline/core/executor.py:119
The PostgreSQL row cap is applied after the complete result has been fetched into psycopg's client-side cursor. The installed SQLAlchemy implementation selects that cursor unless streaming is enabled, and a validated row_list without limit compiles without LIMIT. Large results can therefore exhaust client memory despite row_cap=1000; fetchmany only limits conversion of the already buffered result.
Trigger: Execute a PostgreSQL row_list without an explicit limit against a large registered table.
Evidence: 

