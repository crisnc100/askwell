# Gold changelog

Every change to a file listed in `MANIFEST.json` after P1 needs an entry here with the
reason. Add one only through `uv run python -m evals.gold.manifest --update --reason "..."`,
which bumps the revision and rewrites the hashes; the manifest test checks that the
revisions here run 1..N and match the manifest.

## Revision 1 — 2026-11-09

Initial freeze in P1, before any intent code: the fieldservice gold set (67 items), the
pre-registered Spider ID selection and the selection rule that produced it.

## Revision 2 — 2026-11-09

fs-032: the gold excluded void invoices, but the question does not say to. That contradicts evals/gold/README.md, which predates this item and says void is excluded only when the question says so. The filter is removed; nothing else changes. Found while triaging eval run sim-1.

## Revision 3 — 2026-11-12

Pending held-out set for v0.2 (40 items: 28 in_schema, 6 out_of_schema, 6 should_refuse), written blind by a separate writer that never saw the seen questions, the grammar change or the predictions. Only its SHA-256 is recorded here, under 'pending', before any v0.2 code. The file itself is added in Phase 4, after the grammar and prompt are frozen; its hash must match this one.
