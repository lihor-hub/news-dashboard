---
title: Operations
sidebar_position: 7
---

# Operations

Endpoints for monitoring a running instance and administering it. Health and
metrics routes are unauthenticated; everything under `/api/admin` requires an
admin session.

## Health probes

Three probes with different meanings — do not point all of them at the same
check.

| Route | Auth | Use for |
|-------|------|---------|
| `/api/live` | none | Liveness. Is the process up? |
| `/api/ready` | none | Readiness. Can it serve traffic (dependencies reachable)? |
| `/api/health` | none | General health summary. |
| `/api/health/details` | session | Per-dependency detail. |

Wire a Kubernetes `livenessProbe` to `/api/live` and a `readinessProbe` to
`/api/ready`. Using a dependency-checking endpoint for liveness causes the
orchestrator to restart a healthy process when a downstream dependency blips —
restarting fixes nothing and turns a partial outage into a crash loop.

`/api/health/details` requires a session because it reports dependency
topology, which is useful to an operator and useful to an attacker.

## Metrics and version

| Route | Auth | Serves |
|-------|------|--------|
| `/metrics` | none | Prometheus metrics. |
| `/api/version` | session | Running application version. |
| `/api/config` | session | Client-visible runtime configuration. |
| `/api/changelog` | session | Release notes for the running version. |

`/api/version` reads the same `VERSION` file that drives the OpenAPI
`info.version`, so a deployment can be identified unambiguously.

`/api/config` is what the frontend calls at boot to discover which optional
features are enabled — it reports capability, not secrets.

## Statistics

Read-only aggregates backing the dashboard's charts.

| Route | Reports |
|-------|---------|
| `/api/stats/overview` | Headline counts. |
| `/api/stats/articles-over-time` | Article volume over time. |
| `/api/stats/article-counts` | Counts by state. |
| `/api/stats/sources-volume` | Volume per source. |
| `/api/stats/source-quality` | Source quality signals. |
| `/api/stats/triage-metrics` | Triage throughput. |
| `/api/stats/category-mix` | Distribution across categories. |
| `/api/stats/ingested-vs-handled` | Ingested against triaged — your backlog trend. |

`/api/stats/ingested-vs-handled` is the one to watch on a personal instance: a
persistent gap means you are subscribed to more than you read, and
`/api/sources/cleanup-suggestions` is the usual remedy.

### AI statistics

| Route | Reports |
|-------|---------|
| `/api/ai-stats/word-cloud` | Term frequency across your corpus. |
| `/api/ai-stats/embedding-map` | 2-D projection of article embeddings. |
| `/api/ai-stats/knowledge-graph` | Entity/relationship graph data. |

The knowledge graph route depends on the optional Neo4j integration and
degrades rather than failing when it is not configured. See
[Configuration → Neo4j knowledge graph](../configuration/neo4j-knowledge-graph.md).

## Recommendations

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/recommendations/health` | GET | Whether the recommender has enough signal. |
| `/api/recommendations/recalculate-mine` | POST | Recompute for the calling user. |
| `/api/recommendations/recalculate` | POST | Recompute across users. |

Recalculation is expensive. Prefer `recalculate-mine`; the instance-wide
variant is an administrative operation.

## Admin endpoints

Everything below is mounted under `/api/admin` and gated on an admin session.
A non-admin session receives `403`.

### User administration

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/admin/users` | GET | List users. |
| `/api/admin/users` | POST | Create a user. |
| `/api/admin/users/generate` | POST | Generate a user with credentials. |
| `/api/admin/users/{user_id}` | GET | One user. |
| `/api/admin/users/{user_id}/password` | PATCH | Reset a password. |
| `/api/admin/users/{user_id}` | DELETE | Delete a user. |

`/api/admin/users/generate` creates an account with server-generated
credentials — useful for provisioning a guest or demo account without inventing
a password by hand.

### Instance analytics

| Route | Method | Reports |
|-------|--------|---------|
| `/api/admin/analytics` | GET | Instance-wide usage. |
| `/api/admin/ai/metrics` | GET | AI call volume and cost. |
| `/api/admin/ai/quality` | GET | Generation quality signals. |
| `/api/admin/learning-agent/runs` | GET | Learning-agent run history. |

`/api/admin/ai/metrics` is the endpoint to check when generation costs rise
unexpectedly — it attributes usage before you go looking at provider bills.

## Operational guidance

- **Scrape `/metrics`, alert on `/api/ready`.** Metrics tell you how the
  instance behaves; readiness tells you whether it is serving.
- **Watch source health, not just uptime.** A fully healthy instance with a
  broken feed produces no articles and raises no alarm. Poll
  `/api/sources/health`.
- **Generation endpoints are the slow path.** If request latency degrades,
  separate `/api/ask`, briefing, and lesson generation from ordinary reads
  before concluding the instance is undersized.
