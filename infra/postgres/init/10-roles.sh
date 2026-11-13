#!/usr/bin/env bash
# Runs once, when the Postgres data volume is first initialised.
set -euo pipefail
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v ro_password="${ASKWELL_RO_PASSWORD:?ASKWELL_RO_PASSWORD must be set}" \
  -f /askwell/roles.sql
