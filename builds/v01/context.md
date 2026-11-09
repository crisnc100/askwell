# Ledgerline v0.1 — context

## Product
A governed AI data analyst. People ask business questions in plain English and get answers backed by an auditable, parameterized SQL query. The LLM never writes SQL: it fills in a typed intent, plain Python validates every field against a registry, and a query builder writes the SQL.

The portfolio claim to prove is that this works on schemas it was not tuned on (a synthetic business schema, public text-to-SQL benchmark databases, and any user's own database via `registry init`), with an honest comparison against LangChain's SQL agent, including where the agent wins.

## Audience
- Technical recruiters and hiring managers for applied-AI roles. They read the README, eval table and ADRs, and watch a 90-second video.
- Developers who clone it and point it at their own database.

## Environment (checked 2026-11-09)
- uv 0.9.11, Python 3.14 is on the machine, but the project pins Python 3.12 via uv for library compatibility.
- Docker 29 with the daemon up. Node 23. pnpm is not installed, so use npm.
- gh is installed but not logged in. Pushing waits on `gh auth login` (Cristian).
- The repo is a fresh git repo at `~/Documents/Projects/ledgerline`. The worktree is `ledgerline-v01` on branch `v01`, and there is no remote yet.

## Constraints
- **LLM access goes through OpenRouter** (OpenAI-compatible API) via LangChain's `ChatOpenAI` with `base_url`. Cheap models by default. The model id comes from config, never hardcoded in logic.
- **Budget:** $50/month total across both projects' betas. Every live run has a hard per-run budget, and CI never calls a live model.
- **Replay mode:** recorded model responses let tests, CI and demos run with no API key.
- **The repo is public from day one.** Never commit secrets, and keep `.env.example` only.
- **Spider and BIRD data are CC BY-SA** (verify the licences when writing the fetch script). Do not commit them. Fetch them by script.

## Out of scope for v0.1
Documents RAG and Qdrant, MCP server, CSV upload in the hosted beta, auth, deployment, multi-tenancy, the kit extraction.
