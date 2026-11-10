# Gold changelog

Every change to a file listed in `MANIFEST.json` after P1 needs an entry here with the
reason. Add one only through `uv run python -m evals.gold.manifest --update --reason "..."`,
which bumps the revision and rewrites the hashes; the manifest test checks that the
revisions here run 1..N and match the manifest.

## Revision 1 — 2026-11-09

Initial freeze in P1, before any intent code: the fieldservice gold set (67 items), the
pre-registered Spider ID selection and the selection rule that produced it.
