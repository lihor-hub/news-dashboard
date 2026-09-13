---
title: Monitoring and metrics
sidebar_position: 4
---

# Monitoring and metrics

## Monitoring

For production monitoring:

- **Liveness**: use `GET /api/live` — a failure means the app process is stuck and should be restarted.
- **Readiness**: use `GET /api/ready` — a failure means the database is unreachable or the connection pool is exhausted.
- **Details**: admin users can check `GET /api/health/details` for an overview of database stats and the next scheduled ingest.
- **Source health**: check `GET /api/sources/health` after an ingest run to see which sources failed.

## Prometheus Metrics

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

## Error Tracking

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
