---
title: Sizing and tuning
sidebar_position: 7
---

# Sizing and tuning

News Dashboard is designed for personal or small-team use. Below are rough
guidelines for a typical instance (1–5 users, ~50 sources, ~500 new articles/day).

## Container Resources

| Component                    | CPU (request / limit) | Memory (request / limit) |
| ---------------------------- | --------------------- | ------------------------ |
| App (news-dashboard)         | 50m / 500m            | 128Mi / 512Mi            |
| Ingest CronJob (if separate) | 100m / 500m           | 256Mi / 512Mi            |
| PostgreSQL                   | 100m / 500m           | 256Mi / 512Mi            |

The app row matches the chart defaults. The ingest and PostgreSQL rows are
example starting values from the chart comments; those resource settings are
unset by default. Measure actual usage and adjust limits: ingestion and body
extraction can produce CPU and memory spikes.

## Storage

| Data                                 | Expected size                            | Notes                                                                                                                                       |
| ------------------------------------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **PostgreSQL (articles + metadata)** | Depends on body size and retention | Article bodies are stored in the database as text. 50 sources × ~10 new articles/day × ~50 KB average body → ~9.1 GB/year for bodies alone before database compression, indexes, or metadata. |
| **PostgreSQL WAL**                   | Temporary; varies                        | Depends on checkpoint settings and ingest cadence. Usually under 1 GB.                                                                      |
| **Analytics events**                 | Pruned automatically                     | Cleaned daily per `ANALYTICS_RETENTION_DAYS`. At ~1 KB/event and ~100 events/user/day, ~18 MB per user retained at 180-day retention, before database overhead.                |

Size persistent volumes from measured database growth and your retention
period. Include space for indexes, WAL, backups, Neo4j when enabled, and `/data`
audio caches; do not rely on a fixed multi-year storage estimate.

## Ingest Cadence

- **Personal use**: every 6 hours is sufficient (the default CronJob schedule).
- **Power user**: every 30 minutes (the in-process scheduler default).
- **Multiple users on one instance**: the default 30-minute interval handles
  dozens of users without issue.

Increase ingest frequency cautiously if sources are API-rate-limited. The app
records source health on each run, so you can monitor which sources start
failing if you push too fast.

## Tuning Guidance

- **Memory**: if the app OOM-kills during ingest, increase the memory limit to
  1 Gi for the app container. Ingest fetches and parses multiple feeds
  concurrently.
- **Database connections**: the app uses a connection pool. For a personal
  instance the defaults are fine. For multi-user deployments, consider raising
  PostgreSQL `max_connections` together with the app
  `DB_POOL_MAX_SIZE` (default 8), accounting for every app process and job.
- **Analytics retention**: reduce `ANALYTICS_RETENTION_DAYS` to 30 if you want
  to minimize database growth. Increase to 365 if you want a full year of
  reading analytics.
