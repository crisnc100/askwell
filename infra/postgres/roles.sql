-- Roles for the fieldservice demo DB. Run as the owner role (askwell_owner).
-- Usage: psql -v ro_password=... -f infra/postgres/roles.sql
-- Idempotent: safe to run again.
\set ON_ERROR_STOP on

SELECT format('CREATE ROLE askwell_ro LOGIN PASSWORD %L', :'ro_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'askwell_ro')
\gexec

-- SELECT only: no CREATE, no writes, read-only transactions by default.
-- Everything from here to COMMIT is one transaction: the table-wide GRANT below briefly
-- covers users.email and users.password_hash until the column restriction is re-applied,
-- and no other session may ever see that state, nor may an interrupted run leave it.
BEGIN;
SELECT format('GRANT CONNECT ON DATABASE %I TO askwell_ro', current_database())
\gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO askwell_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO askwell_ro;
-- Test hook (tests/test_roles.py): fail right after the table-wide grant.
\if :{?askwell_test_fail_after_grant}
SELECT 1 / 0 AS injected_failure_after_grant;
\endif
ALTER DEFAULT PRIVILEGES FOR ROLE askwell_owner IN SCHEMA public
    GRANT SELECT ON TABLES TO askwell_ro;
ALTER ROLE askwell_ro SET default_transaction_read_only = on;

-- The table-wide grant above covers every column, so re-apply the column restriction
-- on users after it (the same list as RO_DENIED_COLUMNS in fieldservice/schema.py;
-- a test keeps them equal). Skipped while users does not exist yet; `askwell seed`
-- applies the same restriction when it creates the table.
SELECT 'REVOKE ALL ON public.users FROM askwell_ro'
WHERE to_regclass('public.users') IS NOT NULL
\gexec
SELECT format(
    'GRANT SELECT (%s) ON public.users TO askwell_ro',
    string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
)
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'users'
  AND column_name NOT IN ('email', 'password_hash')
HAVING count(*) > 0
\gexec
COMMIT;

-- The app DB holds Askwell's own tables (the ask_log audit). The read-only role
-- cannot even connect to it.
SELECT 'CREATE DATABASE askwell_app OWNER askwell_owner'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'askwell_app')
\gexec
REVOKE CONNECT ON DATABASE askwell_app FROM PUBLIC;
GRANT CONNECT ON DATABASE askwell_app TO askwell_owner;
