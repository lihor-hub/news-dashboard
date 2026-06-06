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
NEWS_DASHBOARD_DB=./data/news-dashboard.db news-dashboard init
NEWS_DASHBOARD_DB=./data/news-dashboard.db news-dashboard ingest
NEWS_DASHBOARD_DB=./data/news-dashboard.db uvicorn news_dashboard.main:app --reload --app-dir backend
npm run dev
```

Open `http://localhost:5173`.

Ask AI requires an OpenAI key in the backend environment:

```bash
export OPENAI_API_KEY=...
```

## Container

```bash
docker compose up --build
```

Open `http://localhost:8080`.

For Kubernetes, create a Secret and point Helm at it:

```bash
kubectl create secret generic news-dashboard-ai \
  --from-literal=OPENAI_API_KEY=...

helm upgrade --install news-dashboard ./helm/news-dashboard \
  --set app.ai.existingSecret=news-dashboard-ai
```

## Durable database

The Kubernetes deployment uses PostgreSQL by default, backed by durable host storage on the local single-node cluster:

```text
/home/ioachim-minipc/news-dashboard-postgres-data
```

SQLite remains only a local/test fallback. Existing SQLite data can be migrated with:

```bash
news-dashboard-migrate /data/news-dashboard.db
```

## Deployment notes

- The app should be private/auth-protected when exposed publicly.
- `news.lihor.ro` is served by host-level Caddy with Basic Auth.
- GitHub Actions publishes `ghcr.io/ioachim-hub/news-dashboard`.
- For the local Kubernetes cluster, if GHCR pull auth is unavailable, build and push to `localhost:5000/news-dashboard:<tag>` and override Helm image values.
