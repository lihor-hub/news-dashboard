# News Dashboard

Self-hosted technical news inbox for curated feeds, article triage, source
health, search, briefings, and saved/read history.

The app uses a FastAPI backend, a Vite React frontend, PostgreSQL storage, and
optional OpenAI features for embeddings, Ask AI, and briefings.

## Features

- Curated Python, AI/LLM, agents, cloud, engineering, trending, and repository feeds.
- RSS/Atom ingestion, GitHub release feeds, Hacker News/GitHub trending feeds, and custom scraped sources.
- Article states: new, read, saved, skipped, archived, starred, and snoozed.
- Source health, ingest run history, dashboard stats, and search.
- Local password auth with first-admin bootstrap.
- Optional Keycloak login.
- Optional OpenAI embeddings, Ask AI, and generated briefings.
- Docker, Helm, and GitHub Actions deployment support.

## Stack

- Backend: Python 3.14, FastAPI, Typer, psycopg, APScheduler.
- Frontend: React, TypeScript, Vite, TanStack Query.
- Database: PostgreSQL.
- Tooling: Ruff, mypy, pytest, ESLint, Prettier, Vitest, Playwright.

## Requirements

- Python 3.14+
- Node.js and npm compatible with `package-lock.json`
- PostgreSQL 16+
- Docker and Docker Compose for the container flow
- OpenAI API key for AI features

## Configuration

Runtime storage is PostgreSQL only. Set `DATABASE_URL` or the split
`POSTGRES_*` variables.

| Variable | Use |
| --- | --- |
| `DATABASE_URL` | PostgreSQL DSN. |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL connection parts used when `DATABASE_URL` is unset. |
| `SESSION_SECRET` | Signed session key. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD` | First local admin account. Used only when no users exist. |
| `OPENAI_API_KEY` | Enables embeddings, Ask AI, and briefings. |
| `OPENAI_BRIEFING_BASE_URL`, `OPENAI_BRIEFING_API_KEY` | Point briefing generation at an OpenAI-compatible endpoint (e.g. a self-hosted gateway). Optional; falls back to `OPENAI_BASE_URL` / `OPENAI_API_KEY`. Pair with `OPENAI_BRIEFING_MODEL` (use `auto` for a routing gateway). |
| `KEYCLOAK_AUTH_ENABLED`, `KEYCLOAK_SERVER_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | Enables Keycloak. See [docs/KEYCLOAK_AUTH.md](docs/KEYCLOAK_AUTH.md). |
| `CORS_ORIGINS` | Comma-separated browser dev origins. |

SQLite is supported only as a legacy import source for
`news-dashboard-migrate sqlite-to-postgres`.

## Quick Start

Run the container stack:

```bash
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080).

Run ingestion in the app container:

```bash
docker compose exec news-dashboard news-dashboard ingest
```

## Local Development

Install backend and frontend dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
npm install
pre-commit install
```

Start PostgreSQL:

```bash
docker run --rm -d \
  --name news-dashboard-postgres \
  -e POSTGRES_DB=news_dashboard \
  -e POSTGRES_USER=news_dashboard \
  -e POSTGRES_PASSWORD=news-dashboard-local-password \
  -p 5432:5432 \
  postgres:16-alpine
```

Set backend env:

```bash
export DATABASE_URL=postgresql://news_dashboard:news-dashboard-local-password@localhost:5432/news_dashboard
export SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export BOOTSTRAP_ADMIN_USERNAME=admin
export BOOTSTRAP_ADMIN_PASSWORD=change-me
```

Initialize schema and sources:

```bash
news-dashboard init
news-dashboard ingest
```

Run backend and frontend:

```bash
uvicorn news_dashboard.main:app --reload --app-dir backend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Quality Checks

```bash
make lint        # ruff, eslint, prettier checks
make format      # auto-format backend and frontend
make typecheck   # mypy and TypeScript
make test        # backend and frontend tests
make build       # production frontend build
make check       # full CI suite
```

## Project Layout

```text
backend/news_dashboard/   FastAPI app, ingest, auth, scheduler, CLI, database layer
frontend/src/             React app
docs/                     Architecture, product, deployment, and auth notes
helm/news-dashboard/      Kubernetes chart
deploy/                   Deployment files
scripts/                  Maintenance scripts
```

## Deployment

The production image serves the built frontend through FastAPI on port `8080`.

For Kubernetes:

```bash
helm upgrade --install news-dashboard ./helm/news-dashboard
```

Enable auth before exposing an instance outside a trusted network. See
[docs/KEYCLOAK_AUTH.md](docs/KEYCLOAK_AUTH.md) and
[docs/CADDY_HTTPS_SETUP.md](docs/CADDY_HTTPS_SETUP.md).

## Contributing

Issues and PRs are welcome. Run `make check` before opening a PR when local
Python, Node, PostgreSQL, and browser test dependencies are installed.

Keep runtime database code PostgreSQL-specific: psycopg parameters, PostgreSQL
SQL, and existing database helpers. Do not add SQLite runtime fallbacks or
generic multi-database layers.

## Security

Do not commit secrets, API keys, database credentials, or production session
keys. Use environment variables or deployment secrets.

## License

This repository does not include an open-source license.
