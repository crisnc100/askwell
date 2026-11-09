# Ledgerline v0.1 — build log

Deliberate choices made while building, and why. Newest at the bottom of each phase.

## P1 — Foundations, gold, pre-registration

### P1.1 Scaffold
- **Build backend: `uv_build`** (not hatchling). A backend is needed so `[project.scripts]` installs the `ledgerline` command; uv is already the fixed toolchain, so this adds no new tool.
- **No `types-pyyaml`.** Pyright bundles typeshed's third-party stubs, so a stub package would be an extra dependency outside the fixed stack for no gain.
- **Pyright:** `standard` mode for the repo, `strict` for `ledgerline/core/` (empty until P2). **Ruff rules:** E, F, W, I, B, UP, SIM, RUF, S (bandit), PT, N, C4; S101 (assert) ignored repo-wide; S105/S106/S608 ignored in tests only; S311 (non-crypto random) ignored in the seeder and the Spider selector, where seeded determinism is the point.
- **Zero skips:** `tests/plugins/zero_skips.py` turns any skipped or xfailed test, including collection-time skips such as `importorskip`, into a failed run. It is loaded from `tests/conftest.py`, so plain `uv run pytest` enforces it too, not just `verify.sh`. `tests/test_zero_skips.py` proves it with pytester.
- **detect-secrets:** `verify.sh` runs `detect-secrets-hook --baseline .secrets.baseline` over every tracked and untracked-not-ignored file. The only baseline entries are the local compose/CI dev DB credentials (in `.env.example`, `ledgerline/config.py` defaults and the CI workflow), each marked `is_secret: false`. Inline `pragma: allowlist` comments were tried and dropped: they push lines over ruff's limit and the `nextline` form was not honoured by this detect-secrets version, so the audited baseline is the record.
- **Host port 56432 for compose Postgres** (bound to 127.0.0.1, overridable with `LEDGERLINE_DB_PORT`): a local Postgres already holds 5432 and another project's container holds 55432 on this Mac, and a clash would silently connect tests to the wrong server.
- **`verify.sh` does not yet run `docker compose build`, coverage or the replay eval** (L1): there is no image to build until the P5 Dockerfile, no core module until P2 and no replay report until P4. Each phase adds its step.

### P1.2 Compose and seed
- **Roles:** `infra/postgres/roles.sql` is the one role script; compose runs it at volume init (`infra/postgres/init/10-roles.sh`) and CI runs it with `psql`. `ledgerline_ro` gets CONNECT, USAGE and SELECT (including default privileges for future owner tables), `default_transaction_read_only = on`, and no CREATE. A test proves writes and CREATE fail on privileges even with the read-only default switched off.
- **One seed path:** `uv run ledgerline seed`. The compose `seed` service runs exactly that command in the official uv image (repo mounted read-only, venv outside the mount) and runs on `docker compose up`; `docker compose up -d db` starts Postgres alone. No Dockerfile yet; the api image is P5.
- **Seed is drop-and-recreate** and deterministic: `random.Random(20260630)` plus `Faker.seed_instance`, no wall clock, everything relative to `LEDGERLINE_NOW`. The command prints a content SHA-256; the host (macOS) run and the container (Linux) run printed the same hash (`c2aa7b93…df5ce`).
- **Data shape:** 400 customers, 570 sites, 40 technicians, 120 parts, 5,000 work orders over 2024-06-30 → 2026-06-30 (volume grows about 40%), 7,252 part lines, 4,957 invoices (about 8% of invoiced orders get a supplemental invoice, so `work_orders → invoices` really fans out), 25 users with synthetic `email` and `password_hash` (random bytes in a pbkdf2-shaped string, not a hash of any password).
- **Timestamps are naive UTC** in both engines, so SQLite fixtures and Postgres hold identical values; the tests compare the Postgres content hash with a freshly generated SQLite load.
- **Tests never seed Postgres themselves.** The `pg_seeded` fixture fails (never skips) with the exact commands to run when Postgres is unreachable or holds different data, so a test run cannot silently rewrite a dev DB.
