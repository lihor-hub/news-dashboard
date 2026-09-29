# Dataset Storage Statistics and Article Retention

## Context

The administrator-only Stats page currently explains ingest volume and article-handling behavior, but it does not answer operational questions about the dataset itself: how many articles are stored, how far back the dataset reaches, how quickly it is growing, or how much PostgreSQL storage it consumes. Administrators also have no application-level way to cap historical article retention.

This change extends the existing Stats and Scheduler surfaces rather than creating a third overlapping administration page. Stats remains the place for observation. Scheduler becomes the place for configuring and running recurring maintenance.

## Goals

- Show article count, ingestion coverage, growth, and PostgreSQL storage usage.
- Distinguish a typical article payload from the real amortized database cost per article.
- Make historical retention opt-in, instance-wide, and disabled by default.
- Preview the effect of a retention policy before any destructive action.
- Preserve articles that users deliberately retained or that durable content references.
- Run cleanup safely in bounded batches and make scheduled/manual outcomes observable.

## Non-goals

- Shrinking PostgreSQL data files after deletion. Deleted space becomes reusable; ordinary cleanup does not run `VACUUM FULL` or take exclusive table locks.
- Configurable cleanup times or per-user retention policies.
- Retention for ingest history, analytics events, users, sources, briefings, or other non-article domains.
- Exact attribution of shared index and page overhead to individual rows.

## Administrator Experience

### Stats page

The existing `/stats` page gains a **Dataset** section above the current workflow charts. It contains:

- total article count;
- oldest and newest `discovered_at` timestamps;
- dataset coverage expressed as a duration;
- PostgreSQL database size;
- article heap size, auxiliary/TOAST size, index size, and total article-relation size;
- median article row payload using `pg_column_size`;
- amortized article-relation storage (`pg_total_relation_size('articles') / article_count`);
- current cleanup preview: eligible articles, protected old articles, and estimated eligible row payload.

Storage values are returned as bytes and formatted in the browser. The UI explains that row payload is an estimate and that deleting rows makes space reusable without immediately shrinking the database file.

The ingestion chart supports `30 days`, `90 days`, `1 year`, and `All time`. Buckets are daily for 30/90 days, weekly for one year, and monthly for all time. The backend returns zero-filled buckets for bounded ranges; all-time begins with the first stored article.

### Scheduler page

The existing `/feeds/schedule` page gains an **Article retention** card:

- `Keep forever` is the default and maps to a stored null/disabled policy.
- An administrator may choose a positive integer number of days.
- The copy states that age is measured from `articles.discovered_at`.
- The card shows the eligible/protected preview and the fixed `03:30 UTC daily` schedule.
- Saving changes only the policy; it never starts cleanup.
- `Run cleanup now` is disabled while retention is off and requires an explicit confirmation dialog that includes the current eligible count.
- A successful manual cleanup refreshes the preview and job history.

## Data and API Design

The existing PostgreSQL `settings` table stores `article_retention_days`. Absence or an empty value means keep forever. The service validates either null or an integer of at least one day. The API never treats zero or a malformed value as a deletion policy.

Admin-only endpoints are added to the existing stats/scheduler feature modules:

- `GET /api/stats/dataset?range=30d|90d|1y|all` returns dataset/storage metrics, the bucketed ingestion trend, and cleanup preview.
- `GET /api/scheduler/article-retention` returns the saved policy, schedule, and current preview.
- `PUT /api/scheduler/article-retention` validates and stores the policy without deleting rows.
- `POST /api/scheduler/article-retention/run` executes cleanup using the saved policy and returns its summary. It rejects requests while retention is disabled.

Pydantic request/response models define the policy and response contracts. All endpoints inherit authenticated routing and require administrator authorization, matching the existing Stats and Scheduler endpoints.

## Storage Calculations

PostgreSQL-native functions provide storage data:

- `pg_database_size(current_database())` for the whole database;
- `pg_relation_size('articles')` for the main heap;
- `pg_table_size('articles') - pg_relation_size('articles')` for auxiliary table storage, including TOAST and table metadata;
- `pg_indexes_size('articles')` for article indexes;
- `pg_total_relation_size('articles')` for the article relation total;
- `percentile_cont(0.5) WITHIN GROUP (ORDER BY pg_column_size(a.*))` for median logical row payload.

The amortized value divides total article-relation bytes by article count. It intentionally includes article indexes and relation overhead but not rows in related tables. This makes the two per-entry figures complementary rather than presenting either as exact physical attribution.

## Retention Eligibility and Protection

An article is old when:

```text
discovered_at < current UTC time - retention_days
```

An old article is protected when any of these conditions holds:

- any `user_article_state` row is starred;
- it has an `article_highlights` row;
- it has an `article_tags` row (collections use tags);
- it has a `briefing_articles` row;
- it has an `article_shares` row;
- another article identifies it as its canonical article.

The first four rules are the explicitly approved preservation contract. Shares are also deliberate user retention, and canonical references must remain valid. Other per-article rows with cascading foreign keys are derived or transient and may be removed with an eligible article. Foreign keys using `ON DELETE SET NULL` retain their parent record while dropping the article reference.

The preview and deletion use the same shared SQL eligibility predicate so displayed counts cannot drift from cleanup behavior. Preview reports:

- eligible article count;
- protected old article count;
- estimated eligible payload bytes from `SUM(pg_column_size(a.*))`.

## Cleanup Execution

The existing APScheduler process registers `article_retention` at 03:30 UTC, immediately after analytics retention. The job reads the saved policy on every invocation so configuration changes do not require a restart.

If retention is disabled, the scheduled job returns a skipped result and performs no deletion. If enabled, it repeatedly selects at most 500 eligible article IDs ordered by `discovered_at, id`, deletes that batch, commits, and continues until no candidates remain. A fresh eligibility check in each batch avoids relying on a stale preview and bounds lock/transaction duration.

The scheduled path uses the existing scheduled-job history wrapper. Manual execution invokes the same cleanup service and records the same job name so operators can inspect the latest outcome in one place. The summary includes deleted rows, protected old rows observed after cleanup, retention days, and estimated deleted payload bytes. Failures are logged and recorded without disabling future daily runs.

Concurrent manual and scheduled runs are serialized with a PostgreSQL advisory lock. If another cleanup owns the lock, the second invocation returns a skipped/already-running result instead of competing for rows.

## Error Handling and Safety

- Invalid policy values receive a 422 response and are never persisted.
- Retention disabled is represented explicitly; no fallback default can accidentally enable deletion.
- The manual endpoint rejects disabled retention and the UI requires confirmation.
- Storage metric permission/query failures produce the existing page error state and do not affect cleanup configuration.
- Cleanup is idempotent: rerunning it after success deletes zero additional rows until more articles age past the cutoff.
- SQL uses PostgreSQL syntax and psycopg parameters exclusively.

## Testing

Backend PostgreSQL tests cover:

- storage and coverage calculations for empty and populated datasets;
- each trend range and bucket shape;
- policy default, validation, persistence, and admin authorization;
- preview/deletion agreement;
- age based on `discovered_at`;
- every protection rule;
- bounded repeated deletion and idempotency;
- disabled and concurrently locked execution;
- daily scheduler registration and job-history recording.

Frontend tests cover:

- dataset metric rendering and byte formatting;
- range selection and trend reload;
- keep-forever and numeric retention saves;
- preview rendering;
- confirmation before manual cleanup;
- disabled, loading, success, and failure states.

Repository lint, formatting, type checks, the PostgreSQL-backed backend suite, frontend unit tests, and production frontend build must pass before the pull request is queued for merge.
