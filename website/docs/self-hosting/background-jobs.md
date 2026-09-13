---
title: Background jobs
sidebar_position: 6
---

# Background jobs

News Dashboard runs several background jobs that an operator should be aware of:

| Job                              | When                                                                                                                       | What it does                                                                                                                                   |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Ingest**                       | Every 30 minutes (interval set by `INGEST_INTERVAL_MINUTES` or saved scheduler settings, or as a Kubernetes CronJob) | Fetches new articles from all enabled sources, parses feeds, creates article records, fetches full bodies, and scores articles for importance. |
| **Daily Briefing**               | Once daily (scheduled time varies)                                                                                         | Generates an AI-summarized briefing of top articles. Skipped when no AI key is configured (`FREE_LLM_API_KEY` / `OPENAI_API_KEY`).             |
| **Analytics Cleanup**            | Daily                                                                                                                      | Prunes `user_events` older than `ANALYTICS_RETENTION_DAYS` (default: 180). Configurable with the `ANALYTICS_RETENTION_DAYS` env var.           |
| **Recommendation Recalculation** | During ingest + daily full recalculation                                                                                   | Refreshes the article similarity / recommendation model. The ingest-time pass repairs stale scores; the daily pass does a full recalc.         |

## In-Process Scheduler vs. Kubernetes CronJob

The app has two scheduling mechanisms. By default, the in-process scheduler runs
ingest every 30 minutes. When deployed via Helm with the `ingestCronJob`
enabled, the in-process ingest interval is disabled (set via
`INGEST_INTERVAL_SCHEDULER_ENABLED=false`) and the Kubernetes CronJob runs
ingest every 6 hours instead. Other in-process jobs continue running.

If you see duplicate ingest runs, ensure only one scheduler is active.

## Controlling Background Jobs

- **Disable interval ingest**: set `INGEST_INTERVAL_SCHEDULER_ENABLED=false`
- **Manual ingest**: call `POST /api/ingest` or run `news-dashboard ingest` from the CLI
- **Scheduler admin**: authenticated admin users can pause, resume, and change the ingest interval via the `/api/scheduler/*` endpoints
