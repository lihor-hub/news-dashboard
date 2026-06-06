# news-dashboard

Private dashboard for `news.lihor.ro`: a news inbox, reading tracker, source registry, and later summary/AI question layer for Ioachim.

## Product intent

The first useful version is intentionally small:

- Clau/cron jobs collect articles automatically from curated feeds.
- The dashboard stores reading evidence/history: new, read, saved, skipped, archived.
- Each item has source/category metadata plus a short summary/reason.
- Trending stories and GitHub repositories are separated from the curated inbox to avoid noise.
- AI Q&A over saved/read content is a later layer after the corpus exists.

## Source categories

- Python
- AI / LLM / agents
- Cloud / infrastructure
- Engineering
- Trending stories
- Trending repositories

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
npm install
docker compose up -d postgres
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=news_dashboard
export POSTGRES_USER=news_dashboard
export POSTGRES_PASSWORD=news-dashboard-local-password
news-dashboard init
news-dashboard ingest
uvicorn news_dashboard.main:app --reload --app-dir backend
npm run dev
```

Open `http://localhost:5173`.

## Container

```bash
docker compose up --build
```

Open `http://localhost:8080`.

## Durable database

The application uses PostgreSQL. The Kubernetes deployment provisions `postgres:16-alpine` by default, backed by durable host storage on the local single-node cluster:

```text
/home/ioachim-minipc/news-dashboard-postgres-data
```

SQLite is not a runtime database. Existing legacy SQLite data can be migrated into PostgreSQL with:

```bash
news-dashboard-migrate /data/news-dashboard.db
```

## Deployment notes

- The app should be private/auth-protected when exposed publicly.
- `news.lihor.ro` is served by host-level Caddy with Basic Auth.
- GitHub Actions publishes `ghcr.io/ioachim-hub/news-dashboard`.
- For the local Kubernetes cluster, if GHCR pull auth is unavailable, build and push to `localhost:5000/news-dashboard:<tag>` and override Helm image values.
