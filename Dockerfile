# The hosted beta's image: the API, the built pages, and the fieldservice demo on SQLite.
# Build: docker build -t askwell .   Run: docker compose -f compose.prod.yaml up -d

FROM node:22.21.1-bookworm-slim@sha256:25b3eb23a00590b7499f2a2ce939322727fcce1b15fdd69754fcd09536a3ae2c AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --silent
COPY web/ ./
RUN npm run build --silent

# Both base images are pinned by digest, so a rebuild gets exactly the same layers.
FROM ghcr.io/astral-sh/uv:0.9.11-python3.12-bookworm-slim@sha256:ef305979f94d4729707a0fc98444ebf1bc0e63a2d2919a62d28fcc3e42957508
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/venv \
    PATH=/venv/bin:$PATH
WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY askwell/ askwell/
COPY config/ config/
COPY registries/ registries/
COPY evals/ evals/
COPY --from=web /web/dist web/dist
RUN uv sync --locked --no-dev

# The demo database is built once here and only ever opened read-only.
RUN mkdir -p demo \
    && askwell seed --db-url sqlite:////app/demo/fieldservice.sqlite \
    && chmod 0444 demo/fieldservice.sqlite

# Everything the app writes (workspaces, the audit log, today's spend) lives in /data.
RUN useradd --system --uid 10001 --home-dir /nonexistent askwell \
    && mkdir /data && chown askwell /data && chmod 0700 /data
# The image's settings go in /app/.env, not ENV: the environment (.env.beta) beats
# .env, so a deployed .env.beta still using LEDGERLINE_ names overrides them.
RUN printf '%s\n' \
    ASKWELL_LLM_MODE=live \
    ASKWELL_DATABASE_RO_URL=sqlite:////app/demo/fieldservice.sqlite \
    ASKWELL_APP_DATABASE_URL=sqlite:////data/app.sqlite \
    ASKWELL_WORKSPACE_DIR=/data/workspaces \
    ASKWELL_SPEND_DB=/data/spend.sqlite \
    > /app/.env && chmod 0444 /app/.env
USER askwell
VOLUME ["/data"]

EXPOSE 8000
# umask 077: files the app or SQLite creates are readable by this account only.
# --no-proxy-headers: Askwell reads X-Forwarded-For itself (ASKWELL_TRUST_PROXY).
CMD ["sh", "-c", "umask 077 && exec uvicorn askwell.api:create_app --factory --host 0.0.0.0 --port 8000 --no-proxy-headers"]
