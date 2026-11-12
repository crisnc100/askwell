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

## Revision 4 — 2026-11-12

Held-out set for v0.2 revealed in Phase 4, after the grammar and prompt were frozen at 4389ca9. Its SHA-256 equals the pending hash committed in revision 3 (f2e6191) before any v0.2 code, so the questions did not change after the code was written. The file is unchanged; it moves from pending into the frozen files.

## Revision 5 — 2026-11-12

Held-out set, presentation only, before any held-out result. ho-001, ho-002, ho-004, ho-005, ho-006, ho-011 and ho-012 drop ROUND(..., 2), and ho-019 drops ROUND(..., 1), so each returns the full value. ho-003 asks for a fraction, so its gold returns a fraction (1.0 * ... / COUNT(*)) instead of a percent. ho-007, ho-008, ho-010 and ho-027 return their month, and ho-009 its quarter, as date_trunc(...)::date instead of to_char text. This matches the seen set's convention (no rounding, periods as dates), which the scorer compares to within 1e-6 and as ISO dates; as written, a right answer could never match. No question text, filter or join changed. Revision 4 matched the pending hash committed in revision 3 (f2e6191) before any v0.2 code; undoing exactly these edits gives that hash back, which tests/test_gold_manifest.py checks.
