# Manual Duplicate Cleanup Design

## Goal

Let an administrator run the existing article deduplication job on demand from
the Schedule page while retaining its hourly schedule. Duplicate articles are
archived and linked to their canonical article; they are never hard-deleted.

## Existing Behavior

`news_dashboard.embedding_dedup.run_embedding_dedup` embeds recent eligible
articles and archives sufficiently similar duplicates. APScheduler invokes it
every 60 minutes by default through the `embedding_dedup` scheduled job and
records the result in `scheduled_job_runs`. The Schedule page exposes ingest
controls and job history, but no manual deduplication control.

## Approaches Considered

1. **Reuse the existing job synchronously (selected).** Add an admin-only POST
   endpoint that invokes the same scheduler wrapper and returns its structured
   result. This keeps one implementation and gives immediate UI feedback. A run
   can take longer when embeddings must be generated, so the button remains in
   a pending state until completion.
2. **Enqueue an immediate APScheduler run.** This returns quickly but requires
   polling job history to discover completion and errors, complicating the UI.
3. **Create a separate cleanup service.** This could optimize manual behavior,
   but would duplicate matching, safety, and history rules and risk divergence.

## Backend Design

Add `POST /api/scheduler/jobs/embedding-dedup/run` to the existing scheduler
router. The route inherits the scheduler router's explicit admin dependency.
It calls a public service function that runs the existing embedding dedup pass,
records the outcome under the existing `embedding_dedup` job name, and returns:

```json
{"status": "success", "embedded": 4, "merged": 2}
```

Failures are recorded by the existing run-history wrapper and returned as an
HTTP 500 response with a stable error message. The hourly APScheduler
registration and `EMBEDDING_DEDUP_INTERVAL_MINUTES` configuration remain
unchanged.

## Frontend Design

Add a typed `runEmbeddingDedup` API helper and a `Remove duplicates` button to
the Schedule page's Controls card. While the request is active, the button is
disabled and reads `Removing duplicates…`. On success, a toast reports how many
duplicates were archived and how many articles were embedded; job history is
refreshed. On failure, a toast reports that duplicate cleanup failed. Existing
ingest and scheduler controls remain independent.

## Safety and Data Rules

- Use PostgreSQL-specific behavior already implemented by `embedding_dedup`.
- Preserve the 7-day candidate window, similarity threshold, source-visibility
  boundaries, and protection for articles with non-`today` user state.
- Archive duplicates and set `canonical_id`; do not delete article rows or
  related user data.
- Require administrator authentication through `require_admin`.
- Do not introduce additional dependencies or configuration.

## Testing

- Backend route test: an admin request invokes the manual service, returns the
  count payload, and the route is present in OpenAPI.
- Backend service test: a manual run records `embedding_dedup` history and
  exposes counts; a failure is recorded and surfaced.
- Frontend API test: the helper sends POST to the exact route.
- Frontend page test: clicking the action invokes the helper, shows pending
  state, reports counts, and refreshes job history.
- Run repository lint, typecheck, test, and build gates before push, then wait
  for required GitHub checks and merge-queue completion.
