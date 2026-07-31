# News Dashboard Architecture

This project is a self-hosted, open-source news dashboard. It collects curated technical news feeds, stores articles, lets the owner triage them as `new`, `read`, `saved`, `skipped`, or `archived`, tracks source health, and can send a daily digest email.

The system is not a large microservice platform. It is best understood as a modular monolith with a small number of runtime units:

- `news-dashboard`: the FastAPI backend, which also serves the built React frontend in container and Kubernetes deployments.
- `postgres`: the durable production database.
- `neo4j`: optional graph storage for article/entity relationships.
- `news-dashboard-ingest`: a Kubernetes CronJob batch workload that runs ingestion on a schedule.
- Optional external integrations: RSS/Atom feeds, a scraped Anthropic News page, SMTP, GHCR, GitHub Actions, and Keycloak SSO. Host-level Caddy is a transitional Keycloak migration boundary, not the production application route.

## Database Contract

PostgreSQL is the application database. Runtime code should be written directly for PostgreSQL and psycopg:

- Use `%s` parameters, PostgreSQL functions/operators, and `ON CONFLICT` upserts.
- Do not add SQLite fallbacks, database-type sniffing, placeholder translation, or generic multi-database SQL.
- Configure the app with `DATABASE_URL` or `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.
- SQLite is allowed only as an input format for legacy migration tooling that imports old local data into PostgreSQL.
- PostgreSQL must have the [pgvector](https://github.com/pgvector/pgvector) extension available (the `pgvector/pgvector:pg16` image, or `CREATE EXTENSION vector` on an external instance): article embeddings live in `articles.embedding_vec`, with similarity search (Ask AI, topic map, recommendations) running as SQL `<=>` queries over an HNSW index instead of a Python cosine loop.

Neo4j is optional and scoped to graph-shaped data only. PostgreSQL remains the
source of truth for article visibility, users, sources, workflow state,
embeddings, auth, briefings, scheduler history, and analytics. The backend
selects visible article IDs in PostgreSQL before querying Neo4j, so graph
features inherit the same source ownership, disabled-source, and archived-state
rules as the rest of the app.

## Runtime Topology

```mermaid
flowchart TB
  User["User / Browser"]

  subgraph LocalDev["Local development"]
    Vite["Vite React dev server<br/>localhost:5173"]
    FastAPIDev["FastAPI backend<br/>uvicorn news_dashboard.main:app"]
    PostgresDev["PostgreSQL<br/>DATABASE_URL or POSTGRES_*"]
  end

  subgraph Container["Docker / Production image"]
    App["news-dashboard container<br/>FastAPI + built React static files<br/>port 8080"]
  end

  subgraph Kubernetes["Kubernetes via Helm"]
    Ingress["TLS Ingress<br/>news.lihor.ro"]
    TLS["Kubernetes TLS Secret"]
    Service["K8s Service<br/>ClusterIP"]
    Deployment["news-dashboard Deployment<br/>replicas: 1"]
    CronJob["K8s CronJob<br/>news-dashboard ingest<br/>every 6 hours"]
    PostgresSvc["Postgres Service"]
    Postgres["Postgres StatefulSet<br/>pgvector/pgvector:pg16"]
    PVC["HostPath / PVC storage"]
  end

  subgraph External["External systems"]
    Feeds["RSS / Atom feeds<br/>OpenAI, Python, GitHub, HN, etc."]
    Scraped["Scraped page<br/>Anthropic News"]
    SMTP["SMTP server<br/>optional digest email"]
    GHCR["GitHub Container Registry"]
    Actions["GitHub Actions CI/CD"]
    Keycloak["Existing Keycloak<br/>optional SSO under /keycloak"]
  end

  User --> Vite
  Vite --> FastAPIDev
  FastAPIDev --> PostgresDev

  User --> Ingress
  TLS --> Ingress
  Ingress --> Service --> Deployment
  Ingress --> Keycloak
  Deployment --> App
  App --> PostgresSvc --> Postgres --> PVC
  CronJob --> PostgresSvc
  CronJob --> Feeds
  CronJob --> Scraped

  App --> Feeds
  App --> Scraped
  App --> SMTP

  Actions --> GHCR
  GHCR --> Deployment
```

## Application Modules

```mermaid
flowchart LR
  Browser["React UI<br/>frontend/src/App.tsx"]
  APIClient["API client<br/>frontend/src/api.ts"]

  subgraph Backend["Python backend: backend/news_dashboard"]
    Main["main.py<br/>FastAPI routes + static frontend"]
    Ingest["ingest.py<br/>feed parsing, tagging, scoring, insert"]
    Scraper["scraper.py<br/>custom scraped-page handlers"]
    Sources["sources.py<br/>curated source registry"]
    DB["db.py<br/>PostgreSQL connection + schema"]
    Scheduler["scheduler.py<br/>APScheduler ingest + digest jobs"]
    Digest["digest.py<br/>daily email + mark-read token"]
    CLI["cli.py<br/>init, ingest, articles"]
    Migrate["migrate.py<br/>SQLite to Postgres migration"]
  end

  Database["articles + sources tables<br/>PostgreSQL"]

  Browser --> APIClient --> Main
  Main --> Ingest
  Main --> DB
  Main --> Scheduler
  Main --> Digest

  Scheduler --> Ingest
  Scheduler --> Digest
  CLI --> Ingest
  CLI --> Sources
  Ingest --> Sources
  Ingest --> Scraper
  Ingest --> DB
  Digest --> DB
  DB --> Database
```

## Article Ingestion Flow

```mermaid
sequenceDiagram
  participant Trigger as Trigger<br/>Fetch button / Scheduler / CronJob / CLI
  participant API as FastAPI / CLI
  participant Ingest as ingest_all()
  participant Sources as DEFAULT_SOURCES
  participant Feed as RSS/Atom or Scraper
  participant DB as PostgreSQL
  participant UI as React UI

  Trigger->>API: POST /api/ingest or news-dashboard ingest
  API->>Ingest: ingest_all()
  Ingest->>DB: init_db()
  Ingest->>DB: sync_sources()
  Ingest->>Sources: iterate curated sources

  loop each source
    Ingest->>Feed: fetch RSS/Atom or scrape page
    Feed-->>Ingest: entries
    Ingest->>Ingest: clean HTML
    Ingest->>Ingest: canonicalize URL
    Ingest->>Ingest: infer tags
    Ingest->>Ingest: create summary/reason
    Ingest->>Ingest: calculate importance_score
    Ingest->>DB: INSERT article ON CONFLICT/IGNORE
    Ingest->>DB: update source health
  end

  Ingest-->>API: per-source inserted counts
  API-->>Trigger: inserted total + result map
  UI->>API: GET /api/articles, /api/summary, /api/sources
  API->>DB: query latest data
  API-->>UI: articles, counts, source health
```

## User Flow

```mermaid
flowchart TD
  Open["Open news.lihor.ro"] --> Load["React loads dashboard"]
  Load --> Summary["GET /api/summary"]
  Load --> Articles["GET /api/articles?status=new"]
  Load --> Sources["GET /api/sources"]

  Articles --> Inbox["Inbox tab"]
  Summary --> Counts["Tab counts"]
  Sources --> SourcePanel["Sources health panel"]

  Inbox --> Action{"User action"}
  Action --> Read["Mark read"]
  Action --> Save["Save"]
  Action --> Skip["Skip"]
  Action --> Archive["Archive"]

  Read --> Patch["PATCH /api/articles/:id/status"]
  Save --> Patch
  Skip --> Patch
  Archive --> Patch

  Patch --> DB["Update article status<br/>and timestamp"]
  DB --> Reload["Reload articles + summary"]

  Inbox --> Search["Search box"]
  Search --> SearchAPI["GET /api/search?q=..."]
  SearchAPI --> Results["Results across all statuses"]

  Inbox --> Fetch["Fetch now button"]
  Fetch --> Ingest["POST /api/ingest"]
  Ingest --> Reload
```

## CI/CD Flow

```mermaid
flowchart LR
  Dev["Push to main / PR"] --> CI["GitHub Actions"]

  CI --> Tests["Python tests<br/>pytest"]
  CI --> BuildFrontend["npm run build<br/>TypeScript + Vite"]

  Tests --> Publish{"main branch?"}
  BuildFrontend --> Publish

  Publish --> Image["Docker build<br/>React build stage + Python runtime"]
  Image --> GHCR["Push ghcr.io/lihor-hub/news-dashboard:<sha>"]

  GHCR --> Runner["Self-hosted runner<br/>mini PC"]
  Runner --> Sync["Sync deployment logic<br/>from main"]
  Sync --> Gate{"Ingress cutover<br/>explicitly enabled?"}
  Gate -->|yes| Pull["docker pull image"]
  Pull --> Secret["kubectl create/update<br/>GHCR pull secret"]
  Secret --> Helm["helm upgrade --install"]
  Gate -->|no| Preserve["Leave live release unchanged"]
  Helm --> K8s["Kubernetes namespace<br/>news-dashboard"]
  CI --> Render["PR: lint and render<br/>production values"]
  K8s --> Smoke["main: curl HTTPS hostname<br/>/api/health"]
```

## Important Files

- `frontend/src/App.tsx`: the React dashboard, tabs, filters, article cards, source health panel, search, and manual fetch button.
- `frontend/src/api.ts`: browser-side API wrapper around `/api/...`.
- `backend/news_dashboard/main.py`: FastAPI app, API routes, startup/shutdown hooks, and static frontend serving.
- `backend/news_dashboard/ingest.py`: ingestion pipeline, URL canonicalization, source health updates, summaries, tags, and scoring.
- `backend/news_dashboard/sources.py`: curated source registry.
- `backend/news_dashboard/scraper.py`: custom scraped-page handlers, currently for Anthropic News.
- `backend/news_dashboard/db.py`: PostgreSQL configuration, psycopg connection handling, and schema setup.
- `backend/news_dashboard/scheduler.py`: in-process APScheduler jobs for ingest and digest.
- `backend/news_dashboard/digest.py`: daily digest email and signed mark-read links.
- `backend/news_dashboard/cli.py`: maintenance commands.
- `Dockerfile`: multi-stage build, React frontend first, Python runtime second.
- `docker-compose.yml`: local container topology with app plus Postgres and Neo4j.
- `helm/news-dashboard`: Kubernetes Deployment, Service, CronJob, Postgres StatefulSet, secrets, and storage.
- `.github/workflows/ci.yml`: tests, frontend build, image publish, and mini PC deployment.

## Database Model

The database has two main tables:

- `sources`: source registry and health information, including `last_checked_at`, `last_success_at`, `last_error`, `last_fetched_count`, and `last_inserted_count`.
- `articles`: normalized article records, including source metadata, category, kind, publication/discovery timestamps, status, importance score, summary, reason, tags, and status-specific timestamps.

PostgreSQL adds generated `tsvector` columns and GIN indexes in `backend/news_dashboard/db.py`. User-facing search uses PostgreSQL-native predicates today, with the generated full-text index available for ranked search behavior without adding another runtime database.

## How It Works

On startup, FastAPI syncs the configured sources into the database and starts the background scheduler. The scheduler periodically calls the same ingestion pipeline used by the manual `Fetch now` button and the CLI. In Kubernetes, a separate CronJob also runs `news-dashboard ingest` every six hours.

During ingestion, each source is fetched through either `feedparser` for RSS/Atom feeds or a custom scraper for sources that do not expose a feed. Entries are cleaned, URLs are canonicalized to remove tracking parameters, tags are inferred from keywords, summaries and reasons are generated from available text, and rows are inserted if the URL is new. The source row is then updated with success or error health information.

The React UI reads articles by status and category, displays summary counts, shows source health, and lets the user update article status. Status changes are persisted through `PATCH /api/articles/{article_id}/status`, and the UI reloads articles and counts afterward. Search calls `/api/search` and returns matching articles across statuses.

For production, GitHub Actions tests the Python backend, builds the frontend,
builds a Docker image, pushes it to GHCR, and deploys it on a self-hosted runner
with Helm. Pull requests render `values-production.yaml` without contacting the
appliance. The production Ingress terminates application TLS and routes to the
ClusterIP Service. Main CI builds and publishes but does not apply that overlay
unless the operator sets `INGRESS_CUTOVER_ENABLED` to exactly `true`.
Authentication is enforced by FastAPI through local password sessions or
optional Keycloak SSO; an operator must preserve the existing `/keycloak` route
during the Caddy-to-Ingress cutover. See
[Authentication (Keycloak)](/docs/configuration/authentication) and
[Ingress HTTPS and Caddy migration](/docs/configuration/https-caddy).

## Operational Notes

- PostgreSQL is required in every runtime environment. SQLite is only a legacy migration input for importing old local data into PostgreSQL.
- The React app is served separately only in local development. In the production image, the built frontend is served by FastAPI.
- There are two scheduling mechanisms: in-process APScheduler and the Kubernetes CronJob. If duplicate ingestion is undesirable, configure one of them as the authoritative scheduler.
- Authentication is handled by the app. Local password login is always part of the app model, and production can enable Keycloak SSO with `KEYCLOAK_AUTH_ENABLED=1` plus the related `KEYCLOAK_*` settings documented in `README.md` and [Authentication (Keycloak)](/docs/configuration/authentication).
- The production application Service is ClusterIP-only. The Ingress controller
  must be the sole owner of public ports 80 and 443; Caddy cannot share those
  sockets and remains only as a Keycloak migration/rollback concern.
