# News Dashboard

[![CI](https://github.com/lihor-hub/news-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/lihor-hub/news-dashboard/actions/workflows/ci.yml)
[![Coverage Status](https://codecov.io/gh/lihor-hub/news-dashboard/branch/main/graph/badge.svg)](https://app.codecov.io/gh/lihor-hub/news-dashboard)
[![CodeQL](https://github.com/lihor-hub/news-dashboard/actions/workflows/codeql.yml/badge.svg)](https://github.com/lihor-hub/news-dashboard/actions/workflows/codeql.yml)
[![Version](https://img.shields.io/badge/version-1.21.0-blue)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/github/license/lihor-hub/news-dashboard)](LICENSE)

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

## Screenshots

> TODO: these are placeholders generated without a running instance. Replace
> with real captures of the Today feed and the Ask AI / briefing view.

![Today feed placeholder](docs/assets/screenshot-dashboard.svg)

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
- API key for AI features (`FREE_LLM_API_KEY` or `OPENAI_API_KEY`)

## Configuration

Copy [`.env.example`](.env.example) to `.env` and fill in real values to get
started; it enumerates every variable below plus a few advanced/internal
knobs.

Runtime storage is PostgreSQL only. Set `DATABASE_URL` or the split
`POSTGRES_*` variables.

| Variable                                                                                                         | Use                                                                                                                                                                                                                                                                                                                                                                              |
| ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`                                                                                                   | PostgreSQL DSN.                                                                                                                                                                                                                                                                                                                                                                  |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`                            | PostgreSQL connection parts used when `DATABASE_URL` is unset.                                                                                                                                                                                                                                                                                                                   |
| `SESSION_SECRET`                                                                                                 | Signed session key. Also signs digest mark-read tokens when `TOKEN_SECRET` is unset. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`.                                                                                                                                                                                                                   |
| `TOKEN_SECRET`                                                                                                   | Optional override used to sign one-click digest mark-read tokens. Set this when digest token rotation should be independent from `SESSION_SECRET`.                                                                                                                                                                                                                                |
| `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`                                                           | First local admin account. Used only when no users exist.                                                                                                                                                                                                                                                                                                                        |
| `FREE_LLM_API_KEY`, `FREE_LLM_BASE_URL`                                                                          | Primary API key and base URL for chat, embeddings, Ask AI, and briefings. Use these to point at a self-hosted OpenAI-compatible gateway. Falls back to `OPENAI_API_KEY` / `OPENAI_BASE_URL` when not set.                                                                                                                                                                        |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`                                                                              | OpenAI credentials. Required for TTS/audio (not replaceable by the free LLM gateway). Also used as fallback for all other AI features when `FREE_LLM_API_KEY` is absent.                                                                                                                                                                                                         |
| `OPENAI_BRIEFING_MODEL`                                                                                          | Model name for briefing generation (e.g. `auto` for a routing gateway, or a specific model ID). Defaults to `gpt-4o-mini`.                                                                                                                                                                                                                                                       |
| `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`                                                    | Traces every OpenAI call (embeddings, Ask AI, briefings, insights, TTS, body fetch) in [Langfuse](https://langfuse.com), each tagged with a descriptive name (`ask-ai`, `briefing-generation`, …). Tracing activates only when both keys are set; otherwise the app uses a plain OpenAI client with no tracing. `LANGFUSE_BASE_URL` is accepted as an alias for `LANGFUSE_HOST`. |
| `KEYCLOAK_AUTH_ENABLED`, `KEYCLOAK_SERVER_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | Enables Keycloak. See [Authentication (Keycloak)](https://docs.lihor.ro/docs/configuration/authentication).                                                                                                                                                                                                                                                                                                            |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`                                                                          | VAPID public and private keys for Web Push notifications. Generate using `npx web-push generate-vapid-keys`.                                                                                                                                                                                                                                                                     |
| `VAPID_EMAIL`                                                                                                    | Contact email address used in VAPID claims mailto link. Defaults to `admin@example.com` if unset.                                                                                                                                                                                                                                                                                |
| `CORS_ORIGINS`                                                                                                   | Comma-separated browser dev origins.                                                                                                                                                                                                                                                                                                                                             |
| `ANALYTICS_RETENTION_DAYS`                                                                                       | Days to retain `user_events` before the daily cleanup job prunes them. Defaults to `180`.                                                                                                                                                                                                                                                                                        |

SQLite is supported only as a legacy import source for
`news-dashboard-migrate sqlite-to-postgres`.

## Quick Start

You can run News Dashboard in two ways:

### Option 1: Build from source (recommended for development)

```bash
docker compose up --build
```

### Option 2: Run the published image (recommended for production)

First, start PostgreSQL:
```bash
docker run --rm -d \
  --name news-dashboard-postgres \
  -e POSTGRES_DB=news_dashboard \
  -e POSTGRES_USER=news_dashboard \
  -e POSTGRES_PASSWORD=news-dashboard-local-password \
  -v news-dashboard-postgres-data:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:16-alpine
```

Then run the application:
```bash
docker run -d \
  --name news-dashboard \
  -p 8080:8080 \
  --link news-dashboard-postgres:postgres \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB=news_dashboard \
  -e POSTGRES_USER=news_dashboard \
  -e POSTGRES_PASSWORD=news-dashboard-local-password \
  -e SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  -e BOOTSTRAP_ADMIN_USERNAME=admin \
  -e BOOTSTRAP_ADMIN_PASSWORD=change-me \
  --restart unless-stopped \
  ghcr.io/lihor-hub/news-dashboard:latest
```
**Note**: Replace `latest` with a specific version tag (e.g., `v1.21.0`) or commit SHA for pinned deployments. See [Configuration](#configuration) for all required environment variables.

Open [http://localhost:8080](http://localhost:8080).

Log in with the default local-development credentials:

| Field    | Default value |
| -------- | ------------- |
| Username | `admin`       |
| Password | `change-me`   |

> **These are local-development defaults only.** Before deploying anywhere
> outside your own machine, set `SESSION_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`,
> and `BOOTSTRAP_ADMIN_PASSWORD` to strong, unique values via environment
> variables or a `.env` file — never use these defaults in production.

Run ingestion in the app container:

```bash
docker exec news-dashboard news-dashboard ingest
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

Set backend env (or copy `.env.example` to `.env` and adjust values):

```bash
export DATABASE_URL=postgresql://news_dashboard:news-dashboard-local-password@localhost:5432/news_dashboard
export SESSION_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
# Optional: use a separate secret for digest mark-read links.
export TOKEN_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
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
make test        # backend and frontend tests (everyday development loop)
make build       # production frontend build
make check       # full CI suite
```

### Test lanes

| Command              | What it runs                                                     | When to use                                   |
| -------------------- | ---------------------------------------------------------------- | --------------------------------------------- |
| `make test-smoke`    | Backend `smoke`-marked tests + frontend smoke files              | Quick sanity check, ~seconds                  |
| `make test-backend`  | Full `pytest` suite                                              | Before pushing backend changes                |
| `make test-frontend` | Full Vitest suite                                                | Before pushing frontend changes               |
| `make test-a11y`     | Accessibility smoke tests (axe-core serious/critical violations) | Before pushing UI changes; enforced in CI     |
| `make test-e2e`      | Playwright end-to-end tests                                      | Before pushing UI/routing changes             |
| `make test-full`     | Everything with coverage                                         | Same as nightly CI; use before major releases |

**Local development loop:** run `make test-smoke` during active development, `make test-backend` or `make test-frontend` depending on what you changed, then `make check` before opening a PR.

**Pre-push / pre-release:** run `make test-full` for comprehensive coverage including slow and DB-heavy tests.

Pytest markers:

- `smoke` — fast tests with no external services
- `db` — auto-applied to any test using `pg_url` / `pg_clean`; requires PostgreSQL
- `slow` — expensive tests reserved for the nightly schedule

Run a specific lane with `pytest -m smoke`, `pytest -m "not db"`, or `pytest -m db`.

## Project Layout

```text
backend/news_dashboard/   FastAPI app, ingest, auth, scheduler, CLI, database layer
frontend/src/             React app
docs/                     Architecture, product, deployment, auth, and user guides
helm/news-dashboard/      Kubernetes chart
deploy/                   Deployment files
scripts/                  Maintenance scripts
```

## Getting Started

To begin using News Dashboard as a reader, see the
[Getting Started guide](website/docs/getting-started/index.md) which covers:

- [Install the Android APK](website/docs/getting-started/install-android-apk.md)
  — native Android app wrapping the PWA
- [Create a web account](website/docs/getting-started/create-web-account.md)
  — sign in from any browser
- [Self-host your own instance](#quick-start)
  — run News Dashboard on your own infrastructure

## Documentation

The full documentation site is published at **[docs.lihor.ro](https://docs.lihor.ro)**.

For end-user documentation, see the [User Guide](docs/user-guide/README.md) which covers:
- Concepts and terminology
- The Today Feed and triage workflow
- Managing sources and subscriptions
- Search, briefings, and recommendations
- Saved and read history
- Sharing articles with other users

For technical documentation (architecture, deployment, authentication), see the
[docs index](docs/README.md).

To preview the docs site locally: `cd website && npm install && npm run start`.

## Deployment

The production image serves the built frontend through FastAPI on port `8080`.

For Kubernetes:

```bash
helm upgrade --install news-dashboard ./helm/news-dashboard \
  --set-string postgresql.password=<choose-a-secure-password>
```

When bundled PostgreSQL is enabled (the default), `postgresql.password` is
required. Helm will fail to render if it is empty. For CI/chart rendering
only, pass a dummy value like `--set-string postgresql.password=dummy`.
An existing Kubernetes Secret can be used instead of the Helm value;
see `values.yaml` for the `app.postgresExternal` or `app.databaseUrl` paths.

**Existing deployments:** if you previously deployed with the old default
password (`news-dashboard-local-password`), changing the Helm value or
Kubernetes Secret alone does **not** rotate an already-initialized database
password. You must also run `ALTER USER news_dashboard WITH PASSWORD
'<new-password>'` inside PostgreSQL after updating the secret.

For simple Docker deployments (single-node setups), see the
[Self-Hosting guide](docs/SELF_HOSTING.md) for instructions on running
the published image with persistent storage.

Enable auth before exposing an instance outside a trusted network. See
[Authentication (Keycloak)](https://docs.lihor.ro/docs/configuration/authentication) and
[HTTPS with Caddy](https://docs.lihor.ro/docs/configuration/https-caddy).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions, and how to land your first PR.
Participation is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).

The project is maintainer-led — see [MAINTAINERS.md](MAINTAINERS.md) for who's
involved, [GOVERNANCE.md](GOVERNANCE.md) for how decisions get made, and
[ROADMAP.md](ROADMAP.md) for near-term direction.

New to the project? Browse [good first issues](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aopen+label%3A%22good+first+issue%22) — beginner-friendly tasks with clear scope.

Have a question or an open-ended feature idea? Use
[GitHub Discussions](https://github.com/lihor-hub/news-dashboard/discussions) instead of
opening an issue — see [SUPPORT.md](SUPPORT.md) for details. Issues are reserved for
actionable, specified bugs and feature requests.

Keep runtime database code PostgreSQL-specific: psycopg parameters, PostgreSQL
SQL, and existing database helpers. Do not add SQLite runtime fallbacks or
generic multi-database layers.

## Security

Do not commit secrets, API keys, database credentials, or production session
keys. Use environment variables or deployment secrets.

See [SECURITY.md](SECURITY.md) for the vulnerability-disclosure policy and
supported versions, and [PRIVACY.md](PRIVACY.md) for what data leaves your
instance and how to run fully self-contained.

## License

This project is licensed under the [MIT License](LICENSE).
