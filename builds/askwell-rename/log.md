# Askwell rename log

Ledgerline is renamed Askwell (0.2.0). This file lists every place the old name stays,
and why. `git grep -i ledgerline`, excluding evals/runs, evals/recordings, evals/reports
and the gold files, returns only the places below.

## Kept on purpose, in code
- **Bench system id `ledgerline`** (`askwell/bench/run.py` SYSTEMS, `AskwellSystem.name`,
  the comparisons in `askwell/bench/report.py`, the `--systems` default in
  `askwell/cli.py`, `scripts/select_model.py`, `scripts/check_replay_report.py`, the
  `SYSTEMS` label map in `web/src/results.ts`, and the tests that use it). The frozen
  reports in evals/reports and the run checkpoints are recorded under this id, and
  the Results page and floor checks read it. Renaming it would mean reading two ids.
  The display label is "Askwell". The README's eval section and the docs' eval
  commands (`--systems ledgerline,oneshot`) say so.
- **Report headings "Ledgerline misses" and "Where a baseline beat Ledgerline"**
  (`askwell/bench/report.py`). `scripts/check_replay_report.py` compares a fresh
  render byte for byte with the frozen `evals/reports/replay-fieldservice.md`.
- **Invite cookie `ledgerline_invite`** (`askwell/invite.py`). Renaming it would sign
  every beta user out on deploy.
- **The LEDGERLINE_ fallback** (`askwell/config.py`, `tests/test_legacy_env.py`, the
  nested `${LEDGERLINE_*}` defaults in `docker-compose.yml` and `compose.prod.yaml`, and
  the README setup note). It is there for one release; remove it after 0.2.0.

## Kept on purpose, pinned or historical
- **`evals/gold/spider_selection.py`** line 12, "Ledgerline can express". The file is
  a selection rule hash-pinned in `evals/gold/MANIFEST.json`
  (`test_committed_gold_matches_manifest`). It cannot hold a comment either.
- **`registries/fieldservice.yaml`** line 1, "drafted with `ledgerline registry init`".
  `askwell/bench/run.py` hashes the registry file's bytes into every task key, so even
  a comment edit would invalidate existing run checkpoints.
- **`builds/v01/` and `builds/v02/`**: the plans, logs, review findings and prompts of
  past builds, kept as written.
- **Frozen evidence**: evals/runs, evals/recordings, evals/reports, evals/gold/*.jsonl,
  MANIFEST.json. Untouched. No recording contains the name. The prompt text
  (`askwell/pipeline/prompt.py`) has no "Ledgerline", so no replay key changed and
  nothing was re-recorded.

## Changed
- Package `ledgerline/` to `askwell/` (git mv), imports, CLI `askwell`, pyproject
  name and script, version 0.2.0 (pyproject, `askwell/__init__.py`, the API,
  `web/package.json`), `uv.lock`.
- `ASKWELL_*` settings. Compose image `askwell:beta`, volume `askwell-data`,
  Dockerfile user `askwell`. Postgres roles `askwell_owner` and `askwell_ro`, databases
  `askwell` and `askwell_app` (local dev and CI only; the beta runs on SQLite).
- Page titles, the wordmark, README, docs, ADRs, CI. `.secrets.baseline` follows the
  renamed file and the new local-dev credentials, still audited as not secret.
- No GitHub repo URL appeared anywhere before the rename. The README's hosted-beta
  section, its Caddy block and its health check name the live address,
  `https://askwell.cristianortega.dev`.
