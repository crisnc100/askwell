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

step "pytest (zero skips, branch coverage)"
rm -f coverage.json
uv run pytest --cov=ledgerline --cov-branch --cov-report=json:coverage.json --cov-report=term:skip-covered

step "per-module branch coverage floors"
uv run python -m scripts.check_coverage coverage.json

step "replay eval reproduces the committed report"
uv run python -m scripts.check_replay_report

step "web: type check, build, browser tests (Playwright, fake model)"
# Needs Node and Playwright's Chromium (once: cd web && npx playwright install chromium).
(cd web && npm ci --silent && npm run build --silent && npx playwright test)

printf '\nverify.sh: all checks passed\n'
