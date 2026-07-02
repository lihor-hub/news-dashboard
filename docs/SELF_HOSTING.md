# Self-Hosting

**Note**: The GHCR package must be made public (or accessible via pull secret) for this to work.
> This is a one-time maintainer action: go to the repository's Packages settings,
> select the `ghcr.io/lihor-hub/news-dashboard` package, and change its visibility to Public.

This guide explains how to deploy News Dashboard for production use using the published Docker image from GitHub Container Registry (GHCR).

- [Docker Compose: Dev vs Production](#docker-compose-dev-vs-production)
- [Running with Docker Compose (Production)](#running-with-docker-compose-production)
- [Image Tags and Versioning](#image-tags-and-versioning)
- [Environment Variables](#environment-variables)
- [Healthchecks](#healthchecks)
- [Upgrading](#upgrading)
- [Rolling Back](#rolling-back)
- [Background Jobs](#background-jobs)
- [Sizing](#sizing)
- [Backups](#backups)
- [Next Steps](#next-steps)

## Docker Compose: Dev vs Production

The repository provides two Docker Compose files:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Local development only (builds from source, insecure dev defaults) |
| `docker-compose.prod.yml` | Production deployment (uses published image, requires secure configuration) |

> **Warning**: Never use `docker-compose.yml` for production. It contains insecure defaults suitable only for local development.

## Running with Docker Compose (Production)

### Prerequisites

- PostgreSQL database (version 16+)
- Docker or container runtime
- Required environment variables (see [Configuration](#configuration))

### Step 1: Create Environment File

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
# Edit .env with your secure values
```

See the [.env.example reference](#environment-variables) below for all available options.

### Step 2: Start the Stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

The compose file will fail fast if required secrets (`SESSION_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`) are not set.

### Verifying the Deployment

```bash
# Check service status
docker compose -f docker-compose.prod.yml ps

# Check health endpoint
curl http://localhost:8080/api/health
# Should return: {"status":"ok"}
```

## Image Tags and Versioning

The image is available with the following tags:

- `ghcr.io/lihor-hub/news-dashboard:latest` - Rolling update to the most recent release
- `ghcr.io/lihor-hub/news-dashboard:v<version>` - Specific version (e.g., `v1.21.0`)
- `ghcr.io/lihor-hub/news-dashboard:<commit-sha>` - Exact commit (e.g., `a1b2c3d4e5f6`)

For production deployments, we recommend pinning to a specific version or commit SHA to ensure consistency and prevent unexpected updates.

### Updating docker-compose.prod.yml to Pin a Version

Edit the `image` line in `docker-compose.prod.yml`:

```yaml
services:
  news-dashboard:
    image: ghcr.io/lihor-hub/news-dashboard:v1.21.0  # Pin to specific version
    # ...
```

Then pull and restart:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## Environment Variables

See the [README Configuration section](../README.md#configuration) for the complete list of environment variables.

### Required Variables

| Variable | Description |
|----------|-------------|
| `SESSION_SECRET` | Signed session key. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `BOOTSTRAP_ADMIN_USERNAME` | Initial admin username (created on first run) |
| `BOOTSTRAP_ADMIN_PASSWORD` | Initial admin password |
| `POSTGRES_PASSWORD` | PostgreSQL database password |

### Optional AI Features

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for summaries, insights, TTS |
| `FREE_LLM_API_KEY` | Alternative LLM API key |
| `FREE_LLM_BASE_URL` | Custom LLM endpoint |

### Optional Observability

| Variable | Description |
|----------|-------------|
| `METRICS_ENABLED` | Set to `true` to expose the Prometheus `/metrics` endpoint. Off by default. |

> **Important**: Never commit secrets to version control. Use environment variables or a `.env` file (not committed to Git) to manage sensitive values.

## Healthchecks

News Dashboard exposes several health and readiness endpoints for monitoring and container orchestration.

### Endpoint Reference

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /api/live` | Public | Lightweight liveness — returns `{"status":"ok"}` with no database dependency. Use for Kubernetes `livenessProbe`. |
| `GET /api/ready` | Public | Readiness — checks database connectivity by running `SELECT 1`. Returns 200 on success, 503 on failure. Use for Kubernetes `readinessProbe`. |
| `GET /api/health` | Public | Full health — calls `init_db()` and returns `{"status":"ok"}`. Suitable for load-balancer checks. |
| `GET /api/health/details` | Admin-only | Detailed diagnostics — returns `status`, `database` info, and `next_ingest_at`. Requires admin authentication. |
| `GET /api/sources/health` | Authenticated | Per-source health status for the current user — shows last-checked time, last error, and fetch counts for each source. |
| `GET /api/scheduler/status` | Admin-only | Scheduler state — whether the in-process scheduler is running, its interval, and configured jobs. |
| `GET /metrics` | Public (opt-in) | Prometheus exposition format. Only served when `METRICS_ENABLED=true`; returns 404 otherwise. See [Prometheus Metrics](#prometheus-metrics). |

### Docker Probe Configuration

Add health checks to your `docker-compose.prod.yml` or `docker run`:

```yaml
# docker-compose.prod.yml snippet for the news-dashboard service
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/api/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

If `curl` is not available in the container, use `wget` or the `/api/live` endpoint
which has no dependencies:

```bash
docker run -d \
  --name news-dashboard \
  --health-cmd "wget -qO- http://localhost:8080/api/live" \
  --health-interval 30s \
  --health-timeout 5s \
  --health-retries 3 \
  --health-start-period 30s \
  # ... other options ...
  ghcr.io/lihor-hub/news-dashboard:latest
```

### Kubernetes Probe Configuration

The Helm chart ships with pre-configured probes. If you are writing a raw Deployment manifest:

```yaml
readinessProbe:
  httpGet:
    path: /api/ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10

livenessProbe:
  httpGet:
    path: /api/live
    port: 8080
  initialDelaySeconds: 15
  periodSeconds: 20
```

The Helm chart at `helm/news-dashboard/` already includes these probes. See
`helm/news-dashboard/templates/deployment.yaml` for the full configuration.

### Monitoring

For production monitoring:

- **Liveness**: use `GET /api/live` — a failure means the app process is stuck and should be restarted.
- **Readiness**: use `GET /api/ready` — a failure means the database is unreachable or the connection pool is exhausted.
- **Details**: admin users can check `GET /api/health/details` for an overview of database stats and the next scheduled ingest.
- **Source health**: check `GET /api/sources/health` after an ingest run to see which sources failed.

### Prometheus Metrics

Set `METRICS_ENABLED=true` to expose a `GET /metrics` endpoint in Prometheus
exposition format. It's off by default and unauthenticated when on — treat it
like any other internal-only endpoint and don't expose it directly to the
public internet (put it behind your reverse proxy/network policy, or scrape
it from inside your cluster/VPC).

Metrics exposed:

- `news_dashboard_http_requests_total{method,path,status}` / `news_dashboard_http_request_duration_seconds_sum{method,path}` — request counts and cumulative latency, labeled by route template (e.g. `/api/articles/{article_id}`), never the raw URL.
- `news_dashboard_ingest_runs_total{status}` — ingest run outcomes (`success`/`failure`).
- `news_dashboard_ingest_articles_new_total` — new articles discovered across all ingest runs.
- `news_dashboard_source_health_checks_total{status}` — per-source fetch outcomes (`ok`/`error`) during ingest. No source identity is included in labels, since private-feed names/slugs are user-defined.
- `news_dashboard_scheduler_job_runs_total{job_name,status}` — background job outcomes (`digest`, `briefing`, `recommendations`, `analytics_retention`, `per_user_briefings`).

No article content, URLs, emails, or other PII ever appear in metric labels.

Example scrape config:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: news-dashboard
    metrics_path: /metrics
    static_configs:
      - targets: ["news-dashboard:8080"]
```

## Upgrading

Upgrade safely by following these steps in order.

### Pre-Upgrade Checklist

1. **Read the release notes** — check the [CHANGELOG](../CHANGELOG.md) for any breaking changes, config deprecations, or manual steps.
2. **Back up your database** — a backup is your safety net for rollback. See [PostgreSQL Backup and Restore](https://docs.lihor.ro/docs/configuration/postgres-backup) for backup strategies.
3. **Check the new image tag** — browse available tags on [GHCR](https://ghcr.io/lihor-hub/news-dashboard) or the [releases page](https://github.com/lihor-hub/news-dashboard/releases).

### Docker Compose (Production)

```bash
# 1. Pull the new image
docker compose -f docker-compose.prod.yml pull

# 2. Restart the stack
docker compose -f docker-compose.prod.yml up -d

# 3. Run database migrations if needed
# The app runs init_db() on startup automatically, but if release notes
# mention a manual migration step, run it explicitly:
docker compose -f docker-compose.prod.yml run --rm news-dashboard news-dashboard init
```

### Kubernetes (Helm)

```bash
# 1. Update the image tag and pull policy
helm upgrade news-dashboard ./helm/news-dashboard \
  --set image.tag=v1.22.0 \
  --set image.pullPolicy=Always \
  --reuse-values

# 2. Rollout restarts the deployment automatically.
#    The app runs init_db() on startup.
kubectl -n news-dashboard rollout status deployment/news-dashboard
```

### Migration / Schema Updates

The app calls `init_db()` on every startup, which creates missing tables and
indexes. Schema changes that require a migration step (add column, data
transformation) are documented in the [CHANGELOG](../CHANGELOG.md) release notes
with the exact command to run:

```bash
# Example manual migration step (if release notes call for it):
docker compose -f docker-compose.prod.yml run --rm news-dashboard news-dashboard init
```

If you see a startup error related to a missing column or table, running
`news-dashboard init` (or restarting the container, which calls `init_db`)
typically resolves it.

## Rolling Back

If an upgrade causes issues, roll back using the database backup and the
previous image tag:

```bash
# 1. Stop the new stack
docker compose -f docker-compose.prod.yml down

# 2. Restore the database from your pre-upgrade backup
#    (see https://docs.lihor.ro/docs/configuration/postgres-backup for restore instructions)

# 3. Revert the image tag in docker-compose.prod.yml to the previous version

# 4. Start the previous version
docker compose -f docker-compose.prod.yml up -d
```

For Helm, rollback directly:

```bash
helm rollback news-dashboard 1
```

Rollback is the reason backups are important — always back up the database
**before** starting an upgrade (see the [Pre-Upgrade Checklist](#pre-upgrade-checklist)).

## Background Jobs

News Dashboard runs several background jobs that an operator should be aware of:

| Job | When | What it does |
|-----|------|-------------|
| **Ingest** | Every 30 minutes (configurable via `INGEST_INTERVAL_SCHEDULER_ENABLED` / in-process scheduler, or as a Kubernetes CronJob) | Fetches new articles from all enabled sources, parses feeds, creates article records, fetches full bodies, and scores articles for importance. |
| **Daily Briefing** | Once daily (scheduled time varies) | Generates an AI-summarized briefing of top articles. Skipped when no AI key is configured (`FREE_LLM_API_KEY` / `OPENAI_API_KEY`). |
| **Analytics Cleanup** | Daily | Prunes `user_events` older than `ANALYTICS_RETENTION_DAYS` (default: 180). Configurable with the `ANALYTICS_RETENTION_DAYS` env var. |
| **Recommendation Recalculation** | During ingest + daily full recalculation | Refreshes the article similarity / recommendation model. The ingest-time pass repairs stale scores; the daily pass does a full recalc. |

### In-Process Scheduler vs. Kubernetes CronJob

The app has two scheduling mechanisms. By default, the in-process scheduler runs
ingest every 30 minutes. When deployed via Helm with the `ingestCronJob`
enabled, the in-process scheduler disables itself (set via
`INGEST_INTERVAL_SCHEDULER_ENABLED=false`) and the Kubernetes CronJob runs
ingest every 6 hours instead.

If you see duplicate ingest runs, ensure only one scheduler is active.

### Controlling Background Jobs

- **Disable the in-process scheduler**: set `INGEST_INTERVAL_SCHEDULER_ENABLED=false`
- **Manual ingest**: call `POST /api/ingest` or run `news-dashboard ingest` from the CLI
- **Scheduler admin**: authenticated admin users can pause, resume, and change the ingest interval via the `/api/scheduler/*` endpoints

## Sizing

News Dashboard is designed for personal or small-team use. Below are rough
guidelines for a typical instance (1–5 users, ~50 sources, ~500 new articles/day).

### Container Resources

| Component | CPU (request / limit) | Memory (request / limit) |
|-----------|-----------------------|--------------------------|
| App (news-dashboard) | 50m / 500m | 128Mi / 512Mi |
| Ingest CronJob (if separate) | 100m / 500m | 256Mi / 512Mi |
| PostgreSQL | 100m / 500m | 256Mi / 512Mi |

These are the defaults shipped in the Helm chart. A personal instance usually
runs comfortably at these levels. During ingest, CPU and memory spike briefly as
feeds are fetched and parsed.

### Storage

| Data | Expected size | Notes |
|------|---------------|-------|
| **PostgreSQL (articles + metadata)** | ~1–2 GB per year for a personal instance | Article bodies are stored in the database as text. 50 sources × ~10 new articles/day × ~50 KB average body → ~250 MB/year for bodies alone. |
| **PostgreSQL WAL** | Temporary; varies | Depends on checkpoint settings and ingest cadence. Usually under 1 GB. |
| **Analytics events** | Pruned automatically | Cleaned daily per `ANALYTICS_RETENTION_DAYS`. At ~1 KB/event and ~100 events/user/day, ~50 MB retained at 180-day retention. |

**Total storage estimate**: 5–10 GB should be comfortable for a personal
instance running for several years. A cheap 20 GB volume leaves plenty of headroom.

### Ingest Cadence

- **Personal use**: every 6 hours is sufficient (the default CronJob schedule).
- **Power user**: every 30 minutes (the in-process scheduler default).
- **Multiple users on one instance**: the default 30-minute interval handles
  dozens of users without issue.

Increase ingest frequency cautiously if sources are API-rate-limited. The app
records source health on each run, so you can monitor which sources start
failing if you push too fast.

### Tuning Guidance

- **Memory**: if the app OOM-kills during ingest, increase the memory limit to
  1 Gi for the app container. Ingest fetches and parses multiple feeds
  concurrently.
- **Database connections**: the app uses a connection pool. For a personal
  instance the defaults are fine. For multi-user deployments, consider raising
  `PG_MAX_CONNECTIONS` on the Postgres side.
- **Analytics retention**: reduce `ANALYTICS_RETENTION_DAYS` to 30 if you want
  to minimize database growth. Increase to 365 if you want a full year of
  reading analytics.

## Backups

Regularly back up your PostgreSQL database. See [PostgreSQL Backup and Restore](https://docs.lihor.ro/docs/configuration/postgres-backup) for:

- Enabling the Helm CronJob backup
- Manual backup and restore procedures
- Verifying dump integrity
- Retention policy configuration

> **Always back up before an upgrade** — this is your rollback path.

## Next Steps

- **Set up HTTPS** with a reverse proxy (see [HTTPS with Caddy](https://docs.lihor.ro/docs/configuration/https-caddy))
- Configure optional features like AI capabilities, Keycloak SSO, or Web Push notifications
- Set up regular backups of your PostgreSQL data
