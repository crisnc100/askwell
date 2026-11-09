-- Roles for the fieldservice demo DB. Run as the owner role (ledgerline_owner).
-- Usage: psql -v ro_password=... -f infra/postgres/roles.sql
-- Idempotent: safe to run again.
\set ON_ERROR_STOP on

SELECT format('CREATE ROLE ledgerline_ro LOGIN PASSWORD %L', :'ro_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ledgerline_ro')
\gexec

-- SELECT only: no CREATE, no writes, read-only transactions by default.
SELECT format('GRANT CONNECT ON DATABASE %I TO ledgerline_ro', current_database())
\gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO ledgerline_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ledgerline_ro;
ALTER DEFAULT PRIVILEGES FOR ROLE ledgerline_owner IN SCHEMA public
    GRANT SELECT ON TABLES TO ledgerline_ro;
ALTER ROLE ledgerline_ro SET default_transaction_read_only = on;

-- The app DB holds Ledgerline's own tables (the ask_log audit). The read-only role
-- cannot even connect to it.
SELECT 'CREATE DATABASE ledgerline_app OWNER ledgerline_owner'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'ledgerline_app')
\gexec
REVOKE CONNECT ON DATABASE ledgerline_app FROM PUBLIC;
GRANT CONNECT ON DATABASE ledgerline_app TO ledgerline_owner;
