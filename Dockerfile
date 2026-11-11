# The hosted beta's image: the API, the built pages, and the fieldservice demo on SQLite.
# Build: docker build -t ledgerline .   Run: docker compose -f compose.prod.yaml up -d

FROM node:22.21.1-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --silent
COPY web/ ./
RUN npm run build --silent

FROM ghcr.io/astral-sh/uv:0.9.11-python3.12-bookworm-slim
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/venv \
    PATH=/venv/bin:$PATH
WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY ledgerline/ ledgerline/
COPY config/ config/
COPY registries/ registries/
COPY evals/ evals/
COPY --from=web /web/dist web/dist
RUN uv sync --locked --no-dev

# The demo database is built once here and only ever opened read-only.
RUN mkdir -p demo \
    && ledgerline seed --db-url sqlite:////app/demo/fieldservice.sqlite \
    && chmod 0444 demo/fieldservice.sqlite

# Everything the app writes (workspaces, the audit log, today's spend) lives in /data.
RUN useradd --system --uid 10001 --home-dir /nonexistent ledgerline \
    && mkdir /data && chown ledgerline /data && chmod 0700 /data
USER ledgerline
VOLUME ["/data"]

ENV LEDGERLINE_LLM_MODE=live \
    LEDGERLINE_DATABASE_RO_URL=sqlite:////app/demo/fieldservice.sqlite \
    LEDGERLINE_APP_DATABASE_URL=sqlite:////data/app.sqlite \
    LEDGERLINE_WORKSPACE_DIR=/data/workspaces \
    LEDGERLINE_SPEND_DB=/data/spend.sqlite

EXPOSE 8000
# umask 077: files the app or SQLite creates are readable by this account only.
# --no-proxy-headers: Ledgerline reads X-Forwarded-For itself (LEDGERLINE_TRUST_PROXY).
CMD ["sh", "-c", "umask 077 && exec uvicorn ledgerline.api:create_app --factory --host 0.0.0.0 --port 8000 --no-proxy-headers"]
