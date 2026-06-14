# news-dashboard

Private dashboard for `news.example.com`: a news inbox, reading tracker, source registry, and later summary/AI question layer for the owner.

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
pre-commit install   # optional: run linters automatically on commit
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

## Code quality

Tooling lives in `pyproject.toml` (ruff, mypy, pytest/coverage), `eslint.config.mjs`,
and `.prettierrc.json`. CI runs all of it on every PR.

```bash
make lint        # ruff + eslint + prettier (check only)
make format      # auto-format backend and frontend
make typecheck   # mypy (strict) + tsc
make test        # pytest with coverage
make check       # everything CI runs
```

Pre-commit hooks (`.pre-commit-config.yaml`) run the same checks on staged files;
enable them once with `pre-commit install`.

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
/home/your-runner/news-dashboard-postgres-data
```

SQLite remains only a local/test fallback. Existing SQLite data can be migrated with:

```bash
news-dashboard-migrate /data/news-dashboard.db
```

## Deployment notes

- The app should be private/auth-protected when exposed publicly.
- `news.example.com` uses app-level authentication. The local minipc deployment can
  use Keycloak under `https://news.example.com/keycloak`; see
  [docs/KEYCLOAK_AUTH.md](docs/KEYCLOAK_AUTH.md) for backend env vars, Helm
  values, Caddy routing, and the matching Keycloak login theme.
- `news.example.com` is served by host-level Caddy with automatic Let's Encrypt
  HTTPS. See [docs/CADDY_HTTPS_SETUP.md](docs/CADDY_HTTPS_SETUP.md) for the
  full HTTPS setup guide; the Caddyfile lives at `deploy/Caddyfile`.
- HTTPS is required for PWA install (Chrome/Android "Add to Home Screen" as a
  standalone app) and for service worker registration. The service worker must
  let `/api/*`, `/auth/*`, and `/keycloak/*` bypass SPA navigation fallback so
  Keycloak redirects and API responses reach the backend.
- GitHub Actions publishes `ghcr.io/ioachim-hub/news-dashboard`.
- For the local Kubernetes cluster, if GHCR pull auth is unavailable, build and push to `localhost:5000/news-dashboard:<tag>` and override Helm image values.

## License

Released under the [MIT License](LICENSE).
