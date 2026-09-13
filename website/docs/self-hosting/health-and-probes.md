---
title: Health and probes
sidebar_position: 3
---

# Health and probes

News Dashboard exposes several health and readiness endpoints for monitoring and container orchestration.

## Endpoint Reference

| Endpoint                                       | Auth            | Purpose                                                                                                                                                 |
| ---------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /api/live`                                | Public          | Lightweight liveness — returns `{"status":"ok"}` with no database dependency. Use for Kubernetes `livenessProbe`.                                       |
| `GET /api/ready`                               | Public          | Readiness — checks database connectivity by running `SELECT 1`. Returns 200 on success, 503 on failure. Use for Kubernetes `readinessProbe`.            |
| `GET /api/health`                              | Public          | Full health — calls `init_db()` and returns `{"status":"ok"}`. Suitable for load-balancer checks.                                                       |
| `GET /api/health/details`                      | Admin-only      | Detailed diagnostics — returns `status`, `database` info, and `next_ingest_at`. Requires admin authentication.                                          |
| `GET /api/sources/health`                      | Authenticated   | Per-source health status for the current user — shows last-checked time, last error, and fetch counts for each source.                                  |
| `GET /api/scheduler/status`                    | Admin-only      | Scheduler state — whether the in-process scheduler is running, its interval, and configured jobs.                                                       |
| `GET /metrics`                                 | Public (opt-in) | Prometheus exposition format. Only served when `METRICS_ENABLED=true`; returns 404 otherwise. See [Prometheus Metrics](monitoring-and-metrics.md#prometheus-metrics).            |
| `GET /api/config`                              | Public          | Non-sensitive runtime config the SPA needs before login — including the frontend Sentry DSN, if configured. See [Error Tracking](monitoring-and-metrics.md#error-tracking). |
| `GET /docs`, `GET /redoc`, `GET /openapi.json` | Public (opt-in) | Interactive API docs / OpenAPI schema. Only served when `ENABLE_API_DOCS=true`; returns 404 otherwise.                                                  |

## Docker Probe Configuration

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
IMAGE_DIGEST="${IMAGE_DIGEST:?set IMAGE_DIGEST to the published sha256 digest}"
docker run -d \
  --name news-dashboard \
  --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/ready', timeout=5).read()\"" \
  --health-interval 30s \
  --health-timeout 10s \
  --health-retries 3 \
  --health-start-period 30s \
  # ... other options ...
  "ghcr.io/lihor-hub/news-dashboard@${IMAGE_DIGEST}"
```

## Kubernetes Probe Configuration

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
