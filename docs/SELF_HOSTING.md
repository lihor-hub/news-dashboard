# Self-Hosting

**Note**: The GHCR package must be made public (or accessible via pull secret) for this to work.

> This is a one-time maintainer action: go to the repository's Packages settings,
> select the `ghcr.io/lihor-hub/news-dashboard` package, and change its visibility to Public.
> If the package stays private, configure the production `GHCR_TOKEN` Actions
> secret with `read:packages` so CI can create the cluster pull secret. Public
> packages do not need `GHCR_TOKEN`; the deploy workflow leaves
> `image.pullSecretName` empty in that mode.

This guide explains how to deploy News Dashboard for production use using the published Docker image from GitHub Container Registry (GHCR).

- [Know Your Role](#know-your-role)
- [Docker Compose: Dev vs Production](#docker-compose-dev-vs-production)
- [Running with Docker Compose (Production)](#running-with-docker-compose-production)
- [Image Tags and Versioning](#image-tags-and-versioning)
- [Environment Variables](#environment-variables)
- [Healthchecks](#healthchecks)
- [Production Kubernetes Ingress](#production-kubernetes-ingress)
- [Upgrading](#upgrading)
- [Rolling Back](#rolling-back)
- [Background Jobs](#background-jobs)
- [Optional Graph Storage](#optional-graph-storage)
- [Sizing](#sizing)
- [Backups](#backups)
- [Next Steps](#next-steps)

## Know Your Role

A **deployment operator** chooses a deployment method, supplies secrets and
environment configuration, operates PostgreSQL and persistent storage,
monitors health, and performs backups and upgrades. An **application
administrator** signs in to manage users and review ingest operations,
statistics, and analytics.

One person can hold both roles, but host or cluster access does not grant
application administrator access. After deployment, continue with
[Administration and operations](user-guide/administration-and-operations.md)
for the in-app controls.

## Docker Compose: Dev vs Production

The repository provides two Docker Compose files:

| File                      | Purpose                                                                     |
| ------------------------- | --------------------------------------------------------------------------- |
| `docker-compose.yml`      | Local development only (builds from source, insecure dev defaults)          |
| `docker-compose.prod.yml` | Production deployment (uses published image, requires secure configuration) |

> **Warning**: Never use `docker-compose.yml` for production. It contains insecure defaults suitable only for local development.

## Running with Docker Compose (Production)

### Prerequisites

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

The compose file will fail fast if required secrets (`SESSION_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`) are not set.

`docker-compose.prod.yml` also mounts the named `news-dashboard-data` volume at
`/data` and sets `DATA_DIR=/data`. Generated article audio and briefing podcast
MP3 caches live under `/data/audio`, so keep that volume backed by persistent
storage in production. If you run the container manually with `docker run`, pass
both `-e DATA_DIR=/data` and `-v news-dashboard-data:/data`; otherwise audio
files are lost when the app container is recreated.

The production Compose stack also starts a bundled `neo4j:5-community`
container and injects `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and
`NEO4J_DATABASE=neo4j` into the app so the knowledge graph is enabled by
default. After first start, backfill existing cached entities:

```bash
docker compose -f docker-compose.prod.yml exec news-dashboard \
  news-dashboard graph-backfill --limit 250 --days 30
docker compose -f docker-compose.prod.yml exec news-dashboard \
  news-dashboard graph-relationship-backfill --limit 50 --days 7
```

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
    image: ghcr.io/lihor-hub/news-dashboard:v1.21.0 # Pin to specific version
    # ...
```

Then pull and restart:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### Verifying Image Provenance and SBOM

Every image pushed to GHCR from a push to `main` is attested with a
[SLSA build provenance](https://slsa.dev/) statement and a signed SBOM
(SPDX), generated in `.github/workflows/ci.yml` and verifiable with the
[GitHub CLI](https://cli.github.com/):

```bash
# Verify the image was built by this repo's CI (build provenance).
gh attestation verify oci://ghcr.io/lihor-hub/news-dashboard:v1.21.0 \
  --owner lihor-hub

# Verify and inspect the SBOM attestation for the same image.
gh attestation verify oci://ghcr.io/lihor-hub/news-dashboard:v1.21.0 \
  --owner lihor-hub --predicate-type https://spdx.dev/Document
```

Both commands exit non-zero if the image digest doesn't match a
signed attestation from this repository, or if the signature can't be
verified against GitHub's Sigstore-backed OIDC identity. Substitute
the tag with a specific commit SHA to verify an exact build.

## Environment Variables

See the [README Configuration section](../README.md#configuration) for the complete list of environment variables.

### Required Variables

| Variable                   | Description                                                                                   |
| -------------------------- | --------------------------------------------------------------------------------------------- |
| `SESSION_SECRET`           | Signed session key. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `BOOTSTRAP_ADMIN_USERNAME` | Initial admin username (created on first run)                                                 |
| `BOOTSTRAP_ADMIN_PASSWORD` | Initial admin password                                                                        |
| `POSTGRES_PASSWORD`        | PostgreSQL database password                                                                  |

### Optional AI Features

| Variable            | Description                                 |
| ------------------- | ------------------------------------------- |
| `OPENAI_API_KEY`    | OpenAI API key for summaries, insights, TTS |
| `FREE_LLM_API_KEY`  | Alternative LLM API key                     |
| `FREE_LLM_BASE_URL` | Custom LLM endpoint                         |

### Optional Email Delivery

Email delivery remains disabled until the deployment provides a complete SMTP
configuration and an absolute, browser-facing `APP_BASE_URL`. Enabling email
controls in a user's settings does not make delivery available by itself.

| Variable       | Description                                                                         |
| -------------- | ----------------------------------------------------------------------------------- |
| `SMTP_HOST`    | SMTP relay hostname.                                                                |
| `SMTP_PORT`    | SMTP relay port.                                                                    |
| `SMTP_USER`    | SMTP login username.                                                                |
| `SMTP_PASS`    | SMTP login password. Store this outside version control.                            |
| `SMTP_FROM`    | Sender address used for outbound messages.                                          |
| `SMTP_TLS`     | Transport mode: `starttls`, `ssl`, or `none`.                                       |
| `APP_BASE_URL` | Absolute public URL used for links in email, independent of Keycloak configuration. |

`SMTP_USERNAME` and `SMTP_PASSWORD` remain supported for legacy OTP email
deployments. OTP-specific `OTP_SMTP_*` values retain precedence when set. With
Helm, configure the non-secret values under `app.email`, set
`app.publicBaseUrl`, and provide credentials through `app.email.existingSecret`;
the chart does not render credential values into the Deployment.

For email links, `APP_BASE_URL` takes precedence over the compatibility
variables `NEWS_DASHBOARD_BASE_URL` and `NEWS_DASHBOARD_URL`, in that order.

### Optional Observability

| Variable              | Description                                                                                                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `METRICS_ENABLED`     | Set to `true` to expose the Prometheus `/metrics` endpoint. Off by default.                                                                                                          |
| `SENTRY_DSN`          | Backend error tracking. Point at a Sentry or GlitchTip-compatible DSN to capture unhandled exceptions. Off by default — no SDK initializes and no network calls are made when unset. |
| `SENTRY_ENVIRONMENT`  | Environment tag attached to backend events (e.g. `staging`, `production`). Defaults to `production` when `SENTRY_DSN` is set.                                                        |
| `SENTRY_DSN_FRONTEND` | Frontend error tracking. Served to the SPA via `GET /api/config`; safe to expose since Sentry DSNs are send-only. Off by default.                                                    |

### Optional Dify assistant

News Dashboard can show an optional host-owned Dify WebApp iframe assistant to
signed-in users. Set `DIFY_CHAT_ENABLED=true`, a browser-reachable
`DIFY_CHAT_BASE_URL`, and the `DIFY_CHAT_APP_TOKEN` from Dify **Publish →
Embed**; `DIFY_CHAT_TITLE` controls the accessible label. Production URLs must
use HTTPS; HTTP is accepted only at `localhost`, `127.0.0.1`, and `[::1]` for
development. Dify must use an origin separate from News Dashboard; same-origin
configuration is rejected to protect the authenticated parent page. The iframe
is additionally sandboxed for Dify's required scripts, origin storage, forms,
downloads, and constrained popups, without top-navigation permission. The
embed token is intentionally sent to the browser, so it is not a service/API
key and cannot secure private Dify tools or data. News Dashboard sends no
username, email, user ID, or page context; Dify's WebApp identity is separate.
For the Dify app choice, self-hosted `ALLOW_EMBED=true`, reverse-proxy
`frame-src` and SSE requirements, Helm values, and verification, see the [Dify
assistant guide](https://docs.lihor.ro/docs/configuration/dify-assistant).

### Privacy

| Variable            | Description                                                                                                                                                                                                                                                                                                                                   |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ANALYTICS_ENABLED` | Instance-wide analytics kill switch. Set to `false` to stop ingesting `user_events` (route views, time-on-app, article dwell, feature usage) for every user regardless of their individual preference. Defaults to `true`. Users can additionally opt out for themselves from Settings → Privacy, enforced server-side in `POST /api/events`. |

### Optional Security

| Variable          | Description                                                                                                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ENABLE_API_DOCS` | Set to `true` to serve the interactive API docs (`/docs`, `/redoc`, `/openapi.json`). Off by default so a public deployment doesn't leak its full API surface to anonymous visitors; enable it for local development or trusted environments. |
| `ENABLE_HSTS`     | Set to `true` to have the app send `Strict-Transport-Security` itself. Off by default, since HSTS is only correct behind HTTPS — leave it unset for local HTTP dev or when the TLS Ingress already sets it. |

> **Important**: Never commit secrets to version control. Use environment variables or a `.env` file (not committed to Git) to manage sensitive values.

### Baseline browser security headers

The app itself sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, and a conservative `Permissions-Policy` on
every response (API and static frontend alike), so this baseline applies
regardless of which front door is used — `docker run`,
`docker-compose.prod.yml`, or Kubernetes Ingress.
`Strict-Transport-Security` stays opt-in via `ENABLE_HSTS` above. The
production Ingress provides the static edge baseline; the application remains
the source of truth for its dynamic Content Security Policy.

### Optional article body extraction (Crawl4AI)

When a reader opens an article, the app fetches and caches the full body text.
The fallback chain is: the built-in static/Selenium extractor first, then
[Crawl4AI](https://github.com/unclecode/crawl4ai) (a deterministic
browser-based Markdown extractor), and finally the token-expensive LLM
extractor as a last resort.

Crawl4AI is an **optional** extra — it pulls in a browser and a large
dependency tree, so it is not installed by default and is intentionally kept
out of the committed `uv.lock` baseline; its dependencies are resolved when you
opt in. When it is absent, the app simply skips that layer and falls back to the
LLM extractor as before.

> **Security note:** Crawl4AI currently pins an older `lxml` that carries a
> known XXE advisory ([GHSA-vfmq-68hx-4jfw](https://github.com/advisories/GHSA-vfmq-68hx-4jfw),
> patched in lxml 6.1.0). Only enable this extra in environments where you are
> comfortable with that transitive dependency, and prefer running it against
> trusted article sources.

To enable it in a dev or self-hosted environment:

```bash
# 1. Install the extra
pip install -e '.[crawl4ai]'      # or: pip install '.[crawl4ai]'

# 2. Install the browser it drives (run once)
crawl4ai-setup                    # or: playwright install --with-deps chromium
```

In containerized/Kubernetes deployments, run the same two commands in the image
build (`RUN pip install '.[crawl4ai]' && crawl4ai-setup`) so the Chromium
browser is baked into the image; the extractor launches a headless browser at
runtime and does not download anything on demand.

Article URLs are still validated by the app's SSRF/scheme safety checks before
Crawl4AI is invoked, so `file://`, loopback, and private-network URLs never
reach the browser.

## Healthchecks

News Dashboard exposes several health and readiness endpoints for monitoring and container orchestration.

### Endpoint Reference

| Endpoint                                       | Auth            | Purpose                                                                                                                                                 |
| ---------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /api/live`                                | Public          | Lightweight liveness — returns `{"status":"ok"}` with no database dependency. Use for Kubernetes `livenessProbe`.                                       |
| `GET /api/ready`                               | Public          | Readiness — checks database connectivity by running `SELECT 1`. Returns 200 on success, 503 on failure. Use for Kubernetes `readinessProbe`.            |
| `GET /api/health`                              | Public          | Full health — calls `init_db()` and returns `{"status":"ok"}`. Suitable for load-balancer checks.                                                       |
| `GET /api/health/details`                      | Admin-only      | Detailed diagnostics — returns `status`, `database` info, and `next_ingest_at`. Requires admin authentication.                                          |
| `GET /api/sources/health`                      | Authenticated   | Per-source health status for the current user — shows last-checked time, last error, and fetch counts for each source.                                  |
| `GET /api/scheduler/status`                    | Admin-only      | Scheduler state — whether the in-process scheduler is running, its interval, and configured jobs.                                                       |
| `GET /metrics`                                 | Public (opt-in) | Prometheus exposition format. Only served when `METRICS_ENABLED=true`; returns 404 otherwise. See [Prometheus Metrics](#prometheus-metrics).            |
| `GET /api/config`                              | Public          | Non-sensitive runtime config the SPA needs before login — currently just the frontend Sentry DSN, if configured. See [Error Tracking](#error-tracking). |
| `GET /docs`, `GET /redoc`, `GET /openapi.json` | Public (opt-in) | Interactive API docs / OpenAPI schema. Only served when `ENABLE_API_DOCS=true`; returns 404 otherwise.                                                  |

### Docker Probe Configuration

The production image is based on `python:3.14-slim` and does not install `curl`
or `wget`, so `docker-compose.yml` and `docker-compose.prod.yml` ship a
healthcheck that calls `/api/ready` with the Python standard library instead:

```yaml
# docker-compose.prod.yml snippet for the news-dashboard service
healthcheck:
  test:
    [
      'CMD',
      'python',
      '-c',
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=5).read()",
    ]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

`/api/ready` was chosen over `/api/live` so `docker compose ps` reflects
database connectivity, not just process liveness. If you only want process
liveness, swap the path for `/api/live` in the snippet above.

For `docker run`, use the same Python-based probe:

```bash
docker run -d \
  --name news-dashboard \
  --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=5).read()\"" \
  --health-interval 30s \
  --health-timeout 10s \
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

- `news_dashboard_http_requests_total{method,path,status}` — request counts, labeled by route template (e.g. `/api/articles/{article_id}`), never the raw URL.
- `news_dashboard_http_request_duration_seconds{method,path}` — HTTP request latency histogram (exposed as `_bucket`, `_sum`, and `_count` series), labeled by route template, never the raw URL.
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
      - targets: ['news-dashboard:8080']
```

### Error Tracking

Optional, opt-in error tracking against a Sentry or GlitchTip-compatible
DSN — pick a self-hosted GlitchTip instance to keep everything in-house, or
a Sentry SaaS project if you prefer.

- `SENTRY_DSN` enables backend exception capture. Unset (default): no SDK
  initializes and no network calls are made.
- `SENTRY_DSN_FRONTEND` enables frontend error capture. It's served to the
  SPA via the public `GET /api/config` endpoint — this is safe because a
  Sentry DSN only lets a client _send_ events, not read any data.

Both are off independently, so you can enable backend-only, frontend-only,
or both. PII is scrubbed before events are sent: `send_default_pii` is
disabled on both SDKs, and the backend additionally strips cookies and
`Authorization`/`Cookie` headers via a `before_send` hook.

## Production Kubernetes Ingress

The production architecture is:

```text
Internet → TLS Ingress → ClusterIP Service → News Dashboard
```

Use `helm/news-dashboard/values-production.yaml`. It enables the hostname and
TLS Ingress, restricts the application Service to `ClusterIP`, and enables
NetworkPolicies for the configured ingress-controller selectors. Caddy is not
the application TLS source of truth. The repository Caddyfile retains only the
legacy same-host Keycloak route so its separate migration boundary stays
visible.

Live appliance installation and cutover are intentionally not automated from
pull-request CI. Complete the DNS/TLS, ingress-controller, firewall, Keycloak,
and rollback rehearsal in
[human rollout issue #1302](https://github.com/lihor-hub/news-dashboard/issues/1302).
Do not add credentials or private inventory to that issue or this repository.
The detailed staged procedure is in
[Ingress HTTPS and Caddy migration](https://docs.lihor.ro/docs/configuration/https-caddy).
Until that procedure is ready, leave `INGRESS_CUTOVER_ENABLED` unset: main CI
will still build, publish, and scan the image but will exit before any live
release or cluster mutation. Set it to exactly `true` only in the approved
cutover window.

Before removing the old application route:

1. Back up PostgreSQL and verify a restore on a separate instance.
2. Save the current Helm revision and live Caddy configuration.
3. Configure the production `POSTGRES_HOST_PATH` runtime variable for the
   existing data directory, then stage the production values. Verify the
   Ingress through its target address while preserving the public hostname and
   TLS validation.
4. Prepare and rehearse rollback to the previous Helm revision and Caddy route.
5. Preserve the existing Keycloak route behind an equivalent higher-priority
   Ingress route. Verify its login and callback flow.
6. Only then make the ingress controller the sole owner of ports 80 and 443.

### Host PostgreSQL controls

When Kubernetes connects to PostgreSQL running on the host, the database must
be reachable from the selected cluster network without becoming a public
service:

- Set PostgreSQL `listen_addresses` to the specific host or cluster-facing
  interface. Avoid `*`; if it is temporarily unavoidable, the firewall and
  `pg_hba.conf` rules below must still restrict every connection.
- Add the narrowest `pg_hba.conf` `hostssl` rule for the application database,
  role, and actual pod or node source CIDR. Use `scram-sha-256`; never use
  `trust` or a public `0.0.0.0/0` rule.
- Restrict the host firewall to TCP 5432 from that same cluster source network.
  Confirm expected connections succeed and connections from an unrelated
  network are denied.
- Enable PostgreSQL TLS with operator-managed server certificates and protect
  the private key with PostgreSQL-readable file permissions. Configure the
  application DSN with certificate verification (`sslmode=verify-full` and the
  trusted CA) when names and certificates are available; do not commit
  certificate material.
- Keep encrypted, access-controlled backups outside the database host and
  define retention for both logical dumps and any WAL/base-backup strategy.
- Perform restore verification regularly: restore a current backup into an
  isolated PostgreSQL instance, run integrity/application queries, and confirm
  `/api/ready` succeeds against the restored copy before calling the backup
  usable.

After the cutover, inspect the PostgreSQL listener, `pg_hba.conf`, firewall,
TLS negotiation, backup job, and most recent restore verification as one
control set. Record sanitized evidence in issue #1302.

## Upgrading

Upgrade safely by following these steps in order.

### Pre-Upgrade Checklist

1. **Read the release notes** — check the [CHANGELOG](../CHANGELOG.md) for any breaking changes, config deprecations, or manual steps.
2. **Back up your database** — a backup is your safety net for rollback. See [PostgreSQL Backup and Restore](https://docs.lihor.ro/docs/configuration/postgres-backup) for backup strategies.
3. **Back up app data** — if audio features are enabled, keep the `/data` volume (`news-dashboard-data` in Docker Compose) with your normal backup set so generated MP3 caches survive container replacement.
4. **Check the new image tag** — browse available tags on [GHCR](https://ghcr.io/lihor-hub/news-dashboard) or the [releases page](https://github.com/lihor-hub/news-dashboard/releases).

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
(
set -euo pipefail
# 1. Update the image tag and pull policy
: "${SESSION_SECRET:?set SESSION_SECRET}"
: "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}"
: "${POSTGRES_HOST_PATH:?set POSTGRES_HOST_PATH}"
source ./scripts/production-deploy-lib.sh
production_cutover_enabled || { echo "Ingress cutover is not enabled" >&2; exit 2; }
prepare_production_helm_secret_files

helm upgrade news-dashboard ./helm/news-dashboard \
  --values ./helm/news-dashboard/values-production.yaml \
  --set image.tag=v1.22.0 \
  --set image.pullPolicy=Always \
  --set-string postgresql.persistence.hostPath="$POSTGRES_HOST_PATH" \
  --set-file app.auth.sessionSecret="$PRODUCTION_SESSION_SECRET_FILE" \
  --set-file postgresql.password="$PRODUCTION_POSTGRES_PASSWORD_FILE" \
  --reuse-values

# 2. Rollout restarts the deployment automatically.
#    The app runs init_db() on startup.
kubectl -n news-dashboard rollout status deployment/news-dashboard
)
```

The `app.config` values in `helm/news-dashboard/values.yaml` expose the
optional runtime env vars above as structured chart values instead of a
manifest overlay: `app.config.metricsEnabled` (`METRICS_ENABLED`),
`app.config.enableApiDocs` (`ENABLE_API_DOCS`),
`app.config.analyticsRetentionDays` (`ANALYTICS_RETENTION_DAYS`), and
`app.config.corsOrigins` (`CORS_ORIGINS`). All default to off/unset, matching
the app's own defaults. Sentry DSNs and other secret-bearing values are
supplied via `app.sentry.existingSecret` (a pre-existing Secret), never
committed to `values.yaml`.

The optional Dify iframe assistant is configured separately under `app.dify`: set
`app.dify.enabled`, `app.dify.baseUrl`, and `app.dify.title`, and provide the
Publish → Embed token via `app.dify.existingSecret` and
`app.dify.appTokenKey`. The chart requires the base URL and Secret when
enabled, and never accepts a Dify service/API key. See the [Dify assistant
guide](https://docs.lihor.ro/docs/configuration/dify-assistant) for an example.

Newsletter IMAP ingest can also be enabled through structured Helm values.
Create a Secret for mailbox credentials, then set the non-secret mailbox
options on `app.newsletter`:

```bash
kubectl -n news-dashboard create secret generic newsletter-imap \
  --from-literal=NEWSLETTER_IMAP_USERNAME='inbox@example.com' \
  --from-literal=NEWSLETTER_IMAP_PASSWORD='replace-with-real-password'

helm upgrade news-dashboard ./helm/news-dashboard \
  --reuse-values \
  --set app.newsletter.imapHost=imap.example.com \
  --set app.newsletter.imapPort=993 \
  --set app.newsletter.imapFolder=INBOX \
  --set app.newsletter.pollMinutes=15 \
  --set app.newsletter.maxMessageBytes=10485760 \
  --set app.newsletter.existingSecret=newsletter-imap
```

When `app.newsletter.imapHost` is empty, the chart does not render newsletter
IMAP env vars and the scheduler does not start the mailbox poller.

Neo4j is available as an optional Helm-managed graph store. See
[Optional Graph Storage](#optional-graph-storage) for the values and backfill
commands.

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

For an application-only Helm revision rollback, restore the recorded revision
while leaving the current edge unchanged, then verify health before changing
traffic. For the Ingress-to-Caddy edge rollback, do not use `helm rollback`
alone: first restore a guard-compatible NodePort backend, verify it locally,
prepare the saved Caddy application route, release the Ingress listener, start
and verify Caddy locally, and only then reverse DNS or port forwarding. Follow
the exact ordered procedure in
[Ingress HTTPS and Caddy migration](https://docs.lihor.ro/docs/configuration/https-caddy#roll-back).

Rollback is the reason backups are important — always back up the database
**before** starting an upgrade (see the [Pre-Upgrade Checklist](#pre-upgrade-checklist)).

## Background Jobs

News Dashboard runs several background jobs that an operator should be aware of:

| Job                              | When                                                                                                                       | What it does                                                                                                                                   |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Ingest**                       | Every 30 minutes (configurable via `INGEST_INTERVAL_SCHEDULER_ENABLED` / in-process scheduler, or as a Kubernetes CronJob) | Fetches new articles from all enabled sources, parses feeds, creates article records, fetches full bodies, and scores articles for importance. |
| **Daily Briefing**               | Once daily (scheduled time varies)                                                                                         | Generates an AI-summarized briefing of top articles. Skipped when no AI key is configured (`FREE_LLM_API_KEY` / `OPENAI_API_KEY`).             |
| **Analytics Cleanup**            | Daily                                                                                                                      | Prunes `user_events` older than `ANALYTICS_RETENTION_DAYS` (default: 180). Configurable with the `ANALYTICS_RETENTION_DAYS` env var.           |
| **Recommendation Recalculation** | During ingest + daily full recalculation                                                                                   | Refreshes the article similarity / recommendation model. The ingest-time pass repairs stale scores; the daily pass does a full recalc.         |

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

## Optional Graph Storage

Neo4j support is off by default. In Helm installs, set `neo4j.enabled=true` to
render a Neo4j StatefulSet, ClusterIP Service, credentials Secret, and
persistent storage. The app still requires PostgreSQL for primary data storage.

The most common values are:

```yaml
neo4j:
  enabled: true
  auth:
    user: neo4j
    password: 'replace-with-a-long-random-password'
  persistence:
    size: 10Gi
    storageClassName: fast-storage
```

Use `neo4j.auth.existingSecret` and `neo4j.auth.passwordKey` when credentials
are managed outside Helm. The Secret must also include `NEO4J_AUTH` in
`<user>/<password>` form so the Neo4j container can initialize authentication.

For a chart-managed Neo4j Secret, pass a password at install or upgrade time:

```bash
helm upgrade news-dashboard ./helm/news-dashboard \
  --reuse-values \
  --set neo4j.enabled=true \
  --set neo4j.auth.user=neo4j \
  --set-string neo4j.auth.password='replace-with-a-long-random-password'
```

For a pre-existing Secret, create the password key used by the app and
`NEO4J_AUTH` used by the Neo4j container:

```bash
kubectl -n news-dashboard create secret generic news-dashboard-neo4j-auth \
  --from-literal=NEO4J_PASSWORD='replace-with-a-long-random-password' \
  --from-literal=NEO4J_AUTH='neo4j/replace-with-a-long-random-password'

helm upgrade news-dashboard ./helm/news-dashboard \
  --reuse-values \
  --set neo4j.enabled=true \
  --set neo4j.auth.existingSecret=news-dashboard-neo4j-auth \
  --set neo4j.auth.user=neo4j \
  --set neo4j.auth.passwordKey=NEO4J_PASSWORD
```

Persistent storage is enabled by default when Neo4j is enabled. Tune it with
`neo4j.persistence.size`, `neo4j.persistence.storageClassName`,
`neo4j.persistence.existingClaim`, or `neo4j.persistence.hostPath`; set
`neo4j.persistence.enabled=false` only for disposable test installs.

## Sizing

News Dashboard is designed for personal or small-team use. Below are rough
guidelines for a typical instance (1–5 users, ~50 sources, ~500 new articles/day).

### Container Resources

| Component                    | CPU (request / limit) | Memory (request / limit) |
| ---------------------------- | --------------------- | ------------------------ |
| App (news-dashboard)         | 50m / 500m            | 128Mi / 512Mi            |
| Ingest CronJob (if separate) | 100m / 500m           | 256Mi / 512Mi            |
| PostgreSQL                   | 100m / 500m           | 256Mi / 512Mi            |

These are the defaults shipped in the Helm chart. A personal instance usually
runs comfortably at these levels. During ingest, CPU and memory spike briefly as
feeds are fetched and parsed.

### Storage

| Data                                 | Expected size                            | Notes                                                                                                                                       |
| ------------------------------------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **PostgreSQL (articles + metadata)** | ~1–2 GB per year for a personal instance | Article bodies are stored in the database as text. 50 sources × ~10 new articles/day × ~50 KB average body → ~250 MB/year for bodies alone. |
| **PostgreSQL WAL**                   | Temporary; varies                        | Depends on checkpoint settings and ingest cadence. Usually under 1 GB.                                                                      |
| **Analytics events**                 | Pruned automatically                     | Cleaned daily per `ANALYTICS_RETENTION_DAYS`. At ~1 KB/event and ~100 events/user/day, ~50 MB retained at 180-day retention.                |

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

- Choose a deployment method in [Quick Start](../README.md#quick-start) or the
  [Deployment](../README.md#deployment) reference.
- Use the [README Configuration section](../README.md#configuration) as the
  canonical environment-variable reference.
- **Set up HTTPS** with the production Ingress (see
  [Ingress HTTPS and Caddy migration](https://docs.lihor.ro/docs/configuration/https-caddy)).
- Configure authentication and optional integrations through the
  [Configuration guides](https://docs.lihor.ro/docs/configuration).
- Sign in as an application administrator and follow
  [Administration and operations](user-guide/administration-and-operations.md).
- Set up and verify regular
  [PostgreSQL backups](https://docs.lihor.ro/docs/configuration/postgres-backup).
