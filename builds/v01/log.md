# Ledgerline v0.1 — build log

Deliberate choices made while building, and why. Newest at the bottom of each phase.

## P1 — Foundations, gold, pre-registration

### P1.1 Scaffold
- **Build backend: `uv_build`** (not hatchling). A backend is needed so `[project.scripts]` installs the `ledgerline` command; uv is already the fixed toolchain, so this adds no new tool.
- **No `types-pyyaml`.** Pyright bundles typeshed's third-party stubs, so a stub package would be an extra dependency outside the fixed stack for no gain.
- **Pyright:** `standard` mode for the repo, `strict` for `ledgerline/core/` (empty until P2). **Ruff rules:** E, F, W, I, B, UP, SIM, RUF, S (bandit), PT, N, C4; S101 (assert) ignored repo-wide; S105/S106/S608 ignored in tests only; S311 (non-crypto random) ignored in the seeder and the Spider selector, where seeded determinism is the point.
- **Zero skips:** `tests/plugins/zero_skips.py` turns any skipped or xfailed test, including collection-time skips such as `importorskip`, into a failed run. It is loaded from `tests/conftest.py`, so plain `uv run pytest` enforces it too, not just `verify.sh`. `tests/test_zero_skips.py` proves it with pytester.
- **detect-secrets:** `verify.sh` runs `detect-secrets-hook --baseline .secrets.baseline` over every tracked and untracked-not-ignored file. The only baseline entries are the local compose/CI dev DB credentials (in `.env.example`, `ledgerline/config.py` defaults and the CI workflow), each marked `is_secret: false`. Inline `pragma: allowlist` comments were tried and dropped: they push lines over ruff's limit and the `nextline` form was not honoured by this detect-secrets version, so the audited baseline is the record.
- **Host port 55432 for compose Postgres,** not 5432: a local Postgres already listens on 5432 on this Mac, and a clash would silently connect tests to the wrong server.
- **`verify.sh` does not yet run `docker compose build`, coverage or the replay eval** (L1): there is no image to build until the P5 Dockerfile, no core module until P2 and no replay report until P4. Each phase adds its step.
