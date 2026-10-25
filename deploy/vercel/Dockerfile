# Read-only demo backend for Vercel PR previews (the `api` service in
# vercel.json). Same Python build as the production Dockerfile, without the
# frontend (Vercel serves the SPA as the static `app` service), plus a
# throwaway PostgreSQL + pgvector inside the container. The database is
# initialised and seeded with DEMO_MODE data at image build time, so a cold
# start only copies it to /tmp and starts the server. Nothing persists.
# Never use this image outside previews.

FROM rust:1.99.1-slim-bookworm@sha256:a24e292b4af7bdee351a31d3a6379972a5652f0ea22a1b6d6883324ac4f5097c AS rust-toolchain
FROM python:3.15.0-slim-bookworm@sha256:122756f3fe72c4f5d3d71897888204ee85774bc79de952555b8a474e1d0a5d53 AS dependencies
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo RUSTUP_HOME=/usr/local/rustup PATH="/usr/local/cargo/bin:${PATH}"
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY pyproject.toml VERSION CHANGELOG.md ./
COPY backend ./backend
RUN pip wheel --no-cache-dir --wheel-dir=/wheels .

FROM python:3.15.0-slim-bookworm@sha256:122756f3fe72c4f5d3d71897888204ee85774bc79de952555b8a474e1d0a5d53 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PG_BIN=/usr/lib/postgresql/16/bin \
    PGDEMO_SEED=/opt/pgdemo \
    PGDATA=/tmp/pgdata \
    DATABASE_URL=postgresql://news_dashboard@/news_dashboard?host=/tmp \
    DEMO_MODE=1 \
    DATA_DIR=/tmp/news-dashboard-data \
    MCP_SERVER_ENABLED=false \
    INGEST_INTERVAL_SCHEDULER_ENABLED=false
WORKDIR /app
# PostgreSQL 16 + pgvector (HNSW needs pgvector >= 0.5) from the PGDG repo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16 postgresql-16-pgvector \
    && apt-get purge -y curl gnupg \
    && apt-get autoremove -y \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml VERSION CHANGELOG.md ./
COPY backend ./backend
COPY --from=dependencies /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels news-dashboard \
    && rm -rf /wheels \
    && pip check \
    && pip uninstall -y pip
COPY deploy/vercel/demo-entrypoint.sh /usr/local/bin/demo-entrypoint
# Per-image session secret: never committed, shared by every instance of one
# deployment so sessions survive scale-out.
RUN install -d -m 0755 /etc/news-dashboard \
    && head -c 48 /dev/urandom | base64 > /etc/news-dashboard/session_secret \
    && chmod 0444 /etc/news-dashboard/session_secret \
    && demo-entrypoint seed
EXPOSE 80
CMD ["demo-entrypoint", "serve"]
