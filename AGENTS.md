# Agent Notes

## Infrastructure Knowledge

- The application database is PostgreSQL.
- Runtime code must use PostgreSQL-specific SQL and psycopg parameter style.
- Do not add SQLite runtime fallbacks, database-type sniffing, placeholder translation layers, or generic multi-database SQL.
- `DATABASE_URL` must point to PostgreSQL, or the app must be configured with `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.
- SQLite may appear only in legacy import/migration tooling that reads an old SQLite database and writes into PostgreSQL.

## Git Workflow

- Before starting work, fetch and rebase on `origin/main`.
- Keep working branches fast-forwardable with `origin/main`; resolve divergence by rebasing rather than merging.
- Do not use `git push --no-verify` when pushing changes.
