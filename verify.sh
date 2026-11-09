#!/usr/bin/env bash
# The one local and CI gate. Every step must pass; any skipped test fails pytest.
set -euo pipefail
cd "$(dirname "$0")"

step() { printf '\n==> %s\n' "$1"; }

step "uv sync (locked)"
uv sync --locked --quiet

step "ruff check"
uv run ruff check .

step "ruff format --check"
uv run ruff format --check .

step "pyright (strict on ledgerline/core)"
uv run pyright

step "detect-secrets (against .secrets.baseline)"
# Fails if any secret is found that is not already in the reviewed baseline.
git ls-files -z --cached --others --exclude-standard \
  | xargs -0 uv run detect-secrets-hook --baseline .secrets.baseline

step "pytest (zero skips)"
uv run pytest

printf '\nverify.sh: all checks passed\n'
