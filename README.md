# News Dashboard

[![CI / CD](https://github.com/lihor-hub/news-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/lihor-hub/news-dashboard/actions/workflows/ci.yml)
[![Release](https://github.com/lihor-hub/news-dashboard/actions/workflows/release.yml/badge.svg)](https://github.com/lihor-hub/news-dashboard/actions/workflows/release.yml)
[![Coverage Status](https://codecov.io/gh/lihor-hub/news-dashboard/branch/main/graph/badge.svg)](https://app.codecov.io/gh/lihor-hub/news-dashboard)
[![CodeQL](https://github.com/lihor-hub/news-dashboard/actions/workflows/codeql.yml/badge.svg)](https://github.com/lihor-hub/news-dashboard/actions/workflows/codeql.yml)
[![Trivy](https://github.com/lihor-hub/news-dashboard/actions/workflows/trivy-scan.yml/badge.svg)](https://github.com/lihor-hub/news-dashboard/actions/workflows/trivy-scan.yml)
[![Version](https://img.shields.io/github/v/tag/lihor-hub/news-dashboard?filter=v*&sort=semver&label=version&color=blue)](https://github.com/lihor-hub/news-dashboard/releases/latest)
[![License: MIT](https://img.shields.io/github/license/lihor-hub/news-dashboard)](LICENSE)
![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)
![Node 26](https://img.shields.io/badge/node-26-339933)
![PostgreSQL 16+ pgvector](https://img.shields.io/badge/postgresql-16%2B%20pgvector-4169E1)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/lihor-hub/news-dashboard)
[![Open in Dev Containers](https://img.shields.io/static/v1?label=Dev%20Containers&message=Open&color=blue&logo=visualstudiocode)](https://vscode.dev/redirect?url=vscode://ms-vscode-remote.remote-containers/cloneInVolume?url=https://github.com/lihor-hub/news-dashboard)

Self-hosted technical news inbox for curated feeds, article triage, source
health, search, briefings, and saved/read history.

The app uses a FastAPI backend, a Vite React frontend, PostgreSQL storage, and
optional OpenAI-compatible AI features. LangChain composes conversational and
structured model calls, while LangGraph orchestrates multi-stage workflows.

![News Dashboard Today feed showing triaged articles with recommendation scores](docs/screenshots/today-feed.webp)

## Features

- Curated Python, AI/LLM, agents, cloud, engineering, trending, and repository feeds.
- RSS/Atom ingestion, GitHub release feeds, Hacker News/GitHub trending feeds, and custom scraped sources.
- Article states: new, read, saved, skipped, archived, starred, and snoozed.
- Source health, ingest run history, dashboard stats, and search.
- Local password auth with first-admin bootstrap.
- Optional Keycloak login.
- Optional OpenAI embeddings, Ask AI, and generated briefings.
- Google Reader-compatible sync API for third-party RSS clients (NetNewsWire, Reeder, Unread, ...).
- Docker, Helm, and GitHub Actions deployment support.

<details>
<summary>Screenshots</summary>

| Article reader                                                                               | AI briefing                                                       |
| -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| ![Article reader view with AI-generated key takeaways](docs/screenshots/article-detail.webp) | ![AI daily briefing landing page](docs/screenshots/briefing.webp) |

| Source management                                                                          |
| ------------------------------------------------------------------------------------------ |
| ![Feeds page listing subscribed sources with health status](docs/screenshots/sources.webp) |

Screenshots are generated from demo-mode seed data by `npm run capture:screenshots`
(see [scripts/capture-screenshots.spec.ts](scripts/capture-screenshots.spec.ts)); no
real account data is shown.

</details>

## Stack

- Backend: Python 3.14, FastAPI, Typer, psycopg, APScheduler, LangChain, LangGraph.
- Frontend: React, TypeScript, Vite, TanStack Query.
- Database: PostgreSQL.
- Tooling: Ruff, mypy, pytest, ESLint, Prettier, Vitest, Playwright.

## Requirements

- Python 3.14+
- Node.js and npm compatible with `package-lock.json`
- PostgreSQL 16+ with the [pgvector](https://github.com/pgvector/pgvector) extension (the `pgvector/pgvector:pg16` image, or install `vector` on an external Postgres)
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
| `TOKEN_SECRET`                                                                                                   | Optional override used to sign one-click digest mark-read tokens. Set this when digest token rotation should be independent from `SESSION_SECRET`.                                                                                                                                                                                                                               |
| `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`                                                           | First local admin account. Used only when no users exist.                                                                                                                                                                                                                                                                                                                        |
| `FREE_LLM_API_KEY`, `FREE_LLM_BASE_URL`                                                                          | Primary API key and base URL for chat, embeddings, Ask AI, and briefings. Use these to point at a self-hosted OpenAI-compatible gateway. Falls back to `OPENAI_API_KEY` / `OPENAI_BASE_URL` when not set.                                                                                                                                                                        |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`                                                                              | OpenAI credentials. Required for TTS/audio (not replaceable by the free LLM gateway). Also used as fallback for all other AI features when `FREE_LLM_API_KEY` is absent.                                                                                                                                                                                                         |
| `OPENAI_BRIEFING_MODEL`                                                                                          | Model name for briefing generation (e.g. `auto` for a routing gateway, or a specific model ID). Defaults to `gpt-4o-mini`.                                                                                                                                                                                                                                                       |
| `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`                                                    | Traces every OpenAI call (embeddings, Ask AI, briefings, insights, TTS, body fetch) in [Langfuse](https://langfuse.com), each tagged with a descriptive name (`ask-ai`, `briefing-generation`, …). Tracing activates only when both keys are set; otherwise the app uses a plain OpenAI client with no tracing. `LANGFUSE_BASE_URL` is accepted as an alias for `LANGFUSE_HOST`. |
| `KEYCLOAK_AUTH_ENABLED`, `KEYCLOAK_SERVER_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | Enables Keycloak. See [Authentication (Keycloak)](https://docs.lihor.ro/docs/configuration/authentication).                                                                                                                                                                                                                                                                      |
| `DIFY_CHAT_ENABLED`, `DIFY_CHAT_BASE_URL`, `DIFY_CHAT_APP_TOKEN`, `DIFY_CHAT_TITLE`                              | Enables the optional host-owned Dify WebApp iframe assistant. Use a separate Dify origin, HTTPS except for supported loopback HTTP development addresses, and a Publish → Embed token—never a Dify service/API key. See [Dify assistant](https://docs.lihor.ro/docs/configuration/dify-assistant).                                                                                   |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`                                                                          | VAPID public and private keys for Web Push notifications. Generate using `npx web-push generate-vapid-keys`.                                                                                                                                                                                                                                                                     |
| `VAPID_EMAIL`                                                                                                    | Contact email address used in VAPID claims mailto link. Defaults to `admin@example.com` if unset.                                                                                                                                                                                                                                                                                |
| `CORS_ORIGINS`                                                                                                   | Comma-separated browser dev origins.                                                                                                                                                                                                                                                                                                                                             |
| `ANALYTICS_RETENTION_DAYS`                                                                                       | Days to retain `user_events` before the daily cleanup job prunes them. Defaults to `180`.                                                                                                                                                                                                                                                                                        |
| `ANALYTICS_ENABLED`                                                                                              | Instance-wide analytics kill switch. Set to `false` to stop ingesting `user_events` for every user regardless of their individual Settings preference. Defaults to `true`. Users can opt out individually from Settings → Privacy.                                                                                                                                               |
| `ENABLE_API_DOCS`                                                                                                | Serves the interactive API docs (`/docs`, `/redoc`, `/openapi.json`) when truthy. Off by default so a public deployment doesn't leak its full API surface.                                                                                                                                                                                                                       |
| `PUBLIC_RENDERER_EGRESS_PROXY`                                                                                   | Credential-free HTTP(S) validating proxy for optional Selenium fallback. Direct browser egress must be blocked; use IP/network allowlisting or external proxy authentication instead of URL userinfo.                                                                                                                                                                             |
| `NEWSLETTER_IMAP_HOST`, `NEWSLETTER_IMAP_PORT`, `NEWSLETTER_IMAP_USERNAME`, `NEWSLETTER_IMAP_PASSWORD`           | Shared IMAP mailbox polled for newsletter emails (`newsletter_ingest.py`). Feature is fully inert unless host, username, and password are all set. Port defaults to `993`.                                                                                                                                                                                                       |
| `NEWSLETTER_IMAP_FOLDER`                                                                                         | Mailbox folder to poll for newsletters. Defaults to `INBOX`.                                                                                                                                                                                                                                                                                                                     |
| `NEWSLETTER_POLL_MINUTES`                                                                                        | Interval in minutes between newsletter mailbox polls. Defaults to `15`.                                                                                                                                                                                                                                                                                                          |
| `NEWSLETTER_MAX_MESSAGE_BYTES`                                                                                   | Max accepted size in bytes for one RFC822 newsletter message. Oversized messages are skipped and marked seen (not retried) before full parsing. Defaults to 5 MiB (`5242880`).                                                                                                                                                                                                   |

SQLite is supported only as a legacy import source for
`news-dashboard-migrate sqlite-to-postgres`.

### AI orchestration and tracing

The backend uses the vanilla LangChain and LangGraph APIs according to the
shape of each AI operation:

- LangChain composes Ask AI, briefing chat, lesson chat, prompts, model calls,
  and structured output parsing.
- LangGraph orchestrates briefing generation, lesson generation, and agent
  action planning and execution. These graphs are compiled without a
  checkpointer. PostgreSQL run and step records remain the source of truth for
  workflow status and history, including idempotency and stale-run recovery
  where those behaviors apply.
- Native provider clients remain in use for embeddings, TTS, image generation,
  and isolated calls that do not need chain or graph orchestration.

Langfuse tracing is optional. When both Langfuse keys are configured,
framework call sites use `langfuse.langchain.CallbackHandler` and
`langfuse.propagate_attributes(...)` directly. Each request or operation still
has its own trace; a Langfuse session groups related traces without replacing
the trace IDs used for feedback.

Managed prompts are fetched by the stable `production` label by default.
Langfuse assigns every saved prompt an immutable version, and the exact fetched
prompt object is linked to its generation in each trace. This makes prompt
version, labels, trace, user, and session available together in Langfuse. The
prompt optimizer writes proposed revisions as new `candidate`-labeled versions;
promoting or rolling back means moving the `production` label in Langfuse, not
deploying application code. Internal callers may also request an exact prompt
version when a reproducible evaluation or rollback requires it.

| Operation              | Langfuse session ID                                                                |
| ---------------------- | ---------------------------------------------------------------------------------- |
| Ask AI                 | Optional client-provided `session_id`; omitted requests remain independent traces. |
| Briefing conversation  | `briefing:{user_id}:{briefing_id}`                                                 |
| Lesson conversation and related lesson work | `lesson:{user_id}:{lesson_id}`                                      |
| Briefing generation    | `briefing-run:{run_id}`                                                            |
| Lesson generation      | `lesson-run:{run_id}`                                                              |
| Agent action lifecycle | `agent-action:{run_id}`                                                            |

`POST /api/ask` accepts the optional field alongside its existing inputs:

```json
{
  "query": "What changed in LangGraph this week?",
  "include_all": false,
  "session_id": "research:langgraph-weekly"
}
```

Session IDs must be ASCII strings of at most 199 characters. Blank strings are
treated as absent; invalid values receive a request validation error. Existing
clients can omit `session_id`.

> **Upgrading an existing deployment:** article embeddings moved from an
> opaque BLOB column to [pgvector](https://github.com/pgvector/pgvector), so
> similarity search (Ask AI, topic map, recommendations) runs in SQL instead
> of Python. Swap your Postgres image to `pgvector/pgvector:pg16` (or install
> the `vector` extension on an external Postgres) before starting the new
> version — the app backfills existing embeddings into the new column
> automatically on first boot. Starting against a Postgres without the
> extension fails fast with a clear error naming it.

## Try the demo

Want to try News Dashboard before self-hosting it? One command runs a
throwaway instance seeded with sample articles and a read-only guest account
— no AI keys, no configuration:

```bash
docker compose -f docker-compose.demo.yml up
```

Open [http://localhost:8080](http://localhost:8080) and log in with:

| Field    | Value   |
| -------- | ------- |
| Username | `guest` |
| Password | `demo`  |

The guest account is **read-only** — write actions (saving, marking read,
adding sources, etc.) are rejected. This compose file uses fixed demo secrets
and is not meant for real deployments; see [Quick Start](#quick-start) below
to self-host for real.

## Quick Start

You can run News Dashboard in two ways:

### Option 1: Build from source (recommended for development)

```bash
docker compose up --build
```

This stack now brings up PostgreSQL, Neo4j, and the app together, so the
knowledge graph is enabled locally by default.

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
  pgvector/pgvector:pg16
```

Then run the application:

```bash
IMAGE_DIGEST="${IMAGE_DIGEST:?set IMAGE_DIGEST to the published sha256 digest}"
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
  -e DATA_DIR=/data \
  -v news-dashboard-data:/data \
  --restart unless-stopped \
  "ghcr.io/lihor-hub/news-dashboard@${IMAGE_DIGEST}"
```

Resolve the digest from the published image or CI build output; a tag or commit
SHA can move or resolve to a different manifest. The
`news-dashboard-data:/data` volume keeps generated audio and other app data
across container recreates; without it, optional TTS and podcast MP3 caches are
lost during upgrades. See [Configuration](#configuration) for all required
environment variables.

If you also want the knowledge graph enabled in a manual `docker run`
deployment, run a Neo4j container and pass `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD`, and optionally `NEO4J_DATABASE=neo4j` to the app container.

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

> **Zero-setup alternative:** Click [Open in GitHub Codespaces](https://codespaces.new/lihor-hub/news-dashboard) or use the [Dev Container](https://code.visualstudio.com/docs/devcontainers/containers) in VS Code to skip all local installation. The devcontainer pre-installs Python, Node.js, and PostgreSQL automatically.

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
  pgvector/pgvector:pg16
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

## Synchronizing managed prompts

The application keeps its 19 managed-prompt fallbacks in
`backend/news_dashboard/prompt_catalog.py`. To verify catalog shape and sync behavior without
contacting Langfuse, run:

```bash
dotenv run -- pytest backend/tests/test_prompt_catalog.py -q
```

To publish changed prompts, provide credentials only through your environment or secret manager:

```bash
export LANGFUSE_HOST="https://your-langfuse-host.example"
export LANGFUSE_PUBLIC_KEY="<public-key>"
export LANGFUSE_SECRET_KEY="<secret-key>"
python scripts/sync_langfuse_prompts.py
```

The command compares every catalog entry with its current `production` version. Matching entries
are left unchanged; changed or missing entries get one new version labeled `production`. Output is
limited to prompt names, versions, and status and never prints credentials or prompt content.

To roll back, open the prompt in Langfuse and move the `production` label from the new version to
the previously known-good version. To disable Langfuse entirely and use the catalog fallbacks,
remove `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` from the application environment and restart
the application.

## Deployment

The production image serves the built frontend through FastAPI on port `8080`.

For Kubernetes:

```bash
(
set -euo pipefail
IMAGE_DIGEST="${IMAGE_DIGEST:?set IMAGE_DIGEST to sha256:<64 lowercase hex>}"
: "${SESSION_SECRET:?set SESSION_SECRET}"
: "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}"
: "${POSTGRES_HOST_PATH:?set POSTGRES_HOST_PATH}"
source ./scripts/production-deploy-lib.sh
production_cutover_enabled || { echo "Ingress cutover is not enabled" >&2; exit 2; }
prepare_production_helm_secret_files

helm upgrade --install news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard --create-namespace \
  --values ./helm/news-dashboard/values-production.yaml \
  --set-string image.digest="${IMAGE_DIGEST}" \
  --set-string postgresql.persistence.hostPath="$POSTGRES_HOST_PATH" \
  --set-file app.auth.sessionSecret="$PRODUCTION_SESSION_SECRET_FILE" \
  --set-file postgresql.password="$PRODUCTION_POSTGRES_PASSWORD_FILE"
)
```

The production values expose the app only through a TLS Ingress backed by a
`ClusterIP` Service. Supply secrets and installation-specific persistence as
runtime overrides; do not commit them to a values file. The shared helper writes
the secrets to mode-0600 temporary files, removes them on exit, and keeps secret
values out of Helm's process arguments. Pull-request CI renders this contract
without requiring access to the production appliance.

Public egress excludes private and other non-global networks. For an external
PostgreSQL, SMTP, Keycloak, or other private/custom endpoint, copy
`deploy/additional-egress-values.example.json` outside the repository and set
`ADDITIONAL_EGRESS_VALUES_FILE` to that path for every manual deployment. CI
operators can instead store the same non-secret strict JSON in the production
environment variable `ADDITIONAL_EGRESS_VALUES`; both inputs are re-applied on
every Helm upgrade. Keep credentials in Kubernetes/GitHub secrets, never in
this policy-only values input. YAML syntax, aliases, merge keys, comments, and
multiple documents are intentionally not accepted.

Automated and local live application of this overlay is disabled until the
operator sets `INGRESS_CUTOVER_ENABLED=true` after completing the readiness
checks in issue #1302. `scripts/deploy-local-k8s.sh --render` remains available
without that activation.

When bundled PostgreSQL is enabled (the default), `postgresql.password` is
required. Helm will fail to render if it is empty. For CI/chart rendering
only, use `scripts/deploy-local-k8s.sh --render`, which supplies protected
temporary dummy files and never applies the result.
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
[Ingress HTTPS and Caddy migration](https://docs.lihor.ro/docs/configuration/https-caddy).
The live DNS/TLS, Keycloak-route, firewall, and rollback rehearsal requires
appliance access and is tracked in
[human rollout issue #1302](https://github.com/lihor-hub/news-dashboard/issues/1302).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions, and how to land your first PR.
Participation is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).

The project is maintainer-led — see [MAINTAINERS.md](MAINTAINERS.md) for who's
involved, [GOVERNANCE.md](GOVERNANCE.md) for how decisions get made, and
[ROADMAP.md](ROADMAP.md) for near-term direction.

New to the project? Browse [good first issues](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aopen+label%3A%22good+first+issue%22) — beginner-friendly tasks with clear scope — or the meatier
[help wanted](https://github.com/lihor-hub/news-dashboard/issues?q=is%3Aopen+label%3A%22help+wanted%22) projects.
The [contributor announcement](https://github.com/lihor-hub/news-dashboard/discussions/1331)
sums up where help is most wanted right now.

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
