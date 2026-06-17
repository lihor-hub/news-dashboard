# News Dashboard

News Dashboard is a self-hosted technical news inbox. It ingests curated
RSS/Atom feeds and selected scraped sources into PostgreSQL, then provides a
React interface for triage, reading state, source health, run history, briefings,
and search.

The project is designed as a small modular monolith: a FastAPI backend, a Vite
React frontend, PostgreSQL for durable storage, and optional OpenAI-powered
features for briefings and question answering over saved or read articles.

## Features

- Curated source registry for Python, AI/LLM, agents, cloud infrastructure,
  engineering, trending stories, and repository feeds.
- Feed ingestion from RSS/Atom, GitHub release feeds, Hacker News/GitHub
  trending feeds, and custom scraped pages.
- Article workflow for new, read, saved, skipped, archived, starred, and
  snoozed items.
- Source health, ingestion run history, dashboard statistics, and search.
- Multi-user authentication with local password bootstrap or optional Keycloak.
- Optional OpenAI integration for article embeddings, Ask AI, and generated
  briefings.
- Docker, Helm, and GitHub Actions support for deployment.

## Stack

- Backend: Python 3.14, FastAPI, Typer, psycopg, APScheduler.
- Frontend: React, TypeScript, Vite, TanStack Query.
- Database: PostgreSQL.
- Tooling: Ruff, mypy, pytest, ESLint, Prettier, Vitest, Playwright.

## Requirements

- Python 3.14 or newer.
- Node.js and npm compatible with the checked-in `package-lock.json`.
- PostgreSQL 16 or newer.
- Docker and Docker Compose for the containerized workflow.
- An OpenAI API key only if you enable AI features.

## Configuration

Runtime database configuration is PostgreSQL-only. Configure either
`DATABASE_URL` or the `POSTGRES_*` variables:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Full PostgreSQL DSN, for example `postgresql://user:pass@localhost:5432/news_dashboard`. |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Split PostgreSQL connection settings used when `DATABASE_URL` is not set. |
| `SESSION_SECRET` | Required for signed login sessions. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD` | Optional first local admin account. Used only when the user table is empty. |
| `OPENAI_API_KEY` | Optional. Enables embeddings, Ask AI, and briefing generation. |
| `KEYCLOAK_AUTH_ENABLED`, `KEYCLOAK_SERVER_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | Optional Keycloak login integration. See [docs/KEYCLOAK_AUTH.md](docs/KEYCLOAK_AUTH.md). |
| `CORS_ORIGINS` | Optional comma-separated origins for browser development. |

SQLite is not a runtime database. It is supported only as a legacy import source
for `news-dashboard-migrate sqlite-to-postgres`.

## Quick Start

Start the full container stack:

```bash
docker compose up --build
```

The app listens on [http://localhost:8080](http://localhost:8080). The Compose
stack includes PostgreSQL and uses the local credentials defined in
`docker-compose.yml`.

To ingest sources inside the running app container:

```bash
docker compose exec news-dashboard news-dashboard ingest
```

## Local Development

Create the Python environment and install frontend dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
npm install
pre-commit install
```

Start a local PostgreSQL database:

```bash
docker run --rm -d \
  --name news-dashboard-postgres \
  -e POSTGRES_DB=news_dashboard \
  -e POSTGRES_USER=news_dashboard \
  -e POSTGRES_PASSWORD=news-dashboard-local-password \
  -p 5432:5432 \
  postgres:16-alpine
```

Configure the backend process:

```bash
export DATABASE_URL=postgresql://news_dashboard:news-dashboard-local-password@localhost:5432/news_dashboard
export SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export BOOTSTRAP_ADMIN_USERNAME=admin
export BOOTSTRAP_ADMIN_PASSWORD=change-me
```

Initialize the schema, sync sources, and optionally ingest articles:

```bash
news-dashboard init
news-dashboard ingest
```

Run the backend and frontend in separate terminals:

```bash
uvicorn news_dashboard.main:app --reload --app-dir backend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Quality Checks

```bash
make lint        # ruff, eslint, prettier checks
make format      # auto-format backend and frontend code
make typecheck   # mypy and TypeScript
make test        # backend and frontend tests
make build       # production frontend build
make check       # lint, typecheck, tests, and build
```

CI runs the same checks on pull requests.

## Project Layout

```text
backend/news_dashboard/   FastAPI app, ingestion, auth, scheduler, CLI, database layer
frontend/src/             React application
docs/                     Architecture, product, deployment, and auth notes
helm/news-dashboard/      Kubernetes chart
deploy/                   Deployment support files
scripts/                  Maintenance and helper scripts
```

## Deployment

The production image serves the built frontend from the FastAPI backend on port
`8080`. For a local container run, use Docker Compose. For Kubernetes, use the
Helm chart:

```bash
helm upgrade --install news-dashboard ./helm/news-dashboard
```

Authentication should be enabled before exposing an instance beyond a trusted
network. Keycloak deployment notes live in
[docs/KEYCLOAK_AUTH.md](docs/KEYCLOAK_AUTH.md), and HTTPS/Caddy notes live in
[docs/CADDY_HTTPS_SETUP.md](docs/CADDY_HTTPS_SETUP.md).

## Contributing

Issues and pull requests are welcome. Before opening a PR, run `make check` when
your local environment has the required Python, Node, PostgreSQL, and browser
test dependencies installed.

Runtime database code should remain PostgreSQL-specific: use psycopg parameter
style, PostgreSQL SQL features, and the existing database helpers. Do not add
SQLite runtime fallbacks or generic multi-database abstraction layers.

## Security

Do not commit secrets, API keys, database credentials, or production session
secrets. Use environment variables or deployment secrets instead.

## License

This repository does not currently include an open-source license.
