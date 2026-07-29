---
title: Sources and ingestion
sidebar_position: 4
---

# Sources and ingestion

A **source** is a feed the dashboard polls. **Ingestion** is the scheduled job
that fetches every enabled source and creates articles.

## Managing sources

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/sources` | GET | List configured sources. |
| `/api/sources` | POST | Add a source. |
| `/api/sources/{slug}` | DELETE | Remove a source. |
| `/api/sources/{slug}/enabled` | PATCH | Enable or disable without deleting. |
| `/api/sources/{slug}/priority` | PATCH | Change fetch priority. |

Sources are addressed by **slug**, not numeric ID, so URLs stay readable and
stable across environments.

Disabling is preferable to deleting when you only want to pause a feed —
delete discards the source's configuration, while disable leaves it in place
and simply skips it during ingestion.

## Previewing before you commit

```
POST /api/sources/preview
POST /api/sources/substack/preview
```

Both fetch a candidate feed and return a sample of what would be ingested,
without persisting anything. Use them to validate a URL in the UI before
creating the source.

Substack has its own preview route because Substack publications can be served
from custom domains, and resolving the real feed URL takes provider-specific
logic rather than a generic RSS probe.

## Source health

```
GET /api/sources/health
```

Reports per-source fetch health so broken feeds surface before they silently
stop producing articles.

Two related endpoints help prune dead feeds:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/sources/cleanup-suggestions` | GET | Sources that look dead or duplicated. |
| `/api/sources/cleanup` | POST | Apply a cleanup selection. |

## OPML import and export

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/sources/export.opml` | GET | Export all sources as OPML. |
| `/api/sources/import` | POST | Import an OPML file. |

Import is bounded at **5 MiB and 1000 outlines**. Larger uploads are rejected
rather than streamed, which caps per-request memory and time for oversized or
hostile files. OPML is plain text and real subscription lists sit far below
this ceiling.

## Running ingestion

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/ingest` | POST | Trigger an ingestion run now. |
| `/api/ingest/stream` | GET | Stream progress of a running ingestion. |
| `/api/ingest/runs` | GET | History of ingestion runs. |
| `/api/ingest/runs/{run_id}` | GET | Detail for one run. |

`/api/ingest/stream` is a streaming response intended for a live progress view,
not a polling endpoint — open it once and read events as they arrive.

In Kubernetes deployments, scheduled ingestion runs as a separate CronJob
workload rather than inside the web process. Triggering `/api/ingest` runs it
in-process instead, which is convenient for testing but competes with request
serving on a small instance.

## Scheduler

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/scheduler/status` | GET | Current scheduler state and next run. |
| `/api/scheduler/interval` | POST | Change the ingestion interval. |
| `/api/scheduler/pause` | POST | Pause scheduled ingestion. |
| `/api/scheduler/resume` | POST | Resume it. |
| `/api/scheduler/job-runs` | GET | History across all scheduled jobs. |
| `/api/scheduler/jobs/embedding-dedup/run` | POST | Run embedding de-duplication now. |

Pausing the scheduler stops automatic runs but leaves manual `/api/ingest`
available.

## Watchlists

Watchlists are standing interest definitions evaluated against newly ingested
articles.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/watchlists` | GET | List watchlists. |
| `/api/watchlists` | POST | Create one. |
| `/api/watchlists/{watchlist_id}` | PATCH | Update one. |
| `/api/watchlists/{watchlist_id}` | DELETE | Delete one. |
| `/api/watchlists/preview` | POST | Preview matches before saving. |
| `/api/watchlists/nudges` | GET | Suggestions derived from watchlist activity. |

As with sources, `preview` lets you check a definition against existing
articles before committing it.
