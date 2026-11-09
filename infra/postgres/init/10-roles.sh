#!/usr/bin/env bash
# Runs once, when the Postgres data volume is first initialised.
set -euo pipefail
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v ro_password="${LEDGERLINE_RO_PASSWORD:?LEDGERLINE_RO_PASSWORD must be set}" \
  -f /ledgerline/roles.sql
