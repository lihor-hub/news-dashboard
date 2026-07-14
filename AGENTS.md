# Agent Notes

## Infrastructure Knowledge

- The application database is PostgreSQL.
- Runtime code must use PostgreSQL-specific SQL and psycopg parameter style.
- Do not add SQLite runtime fallbacks, database-type sniffing, placeholder translation layers, or generic multi-database SQL.
- `DATABASE_URL` must point to PostgreSQL, or the app must be configured with `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`.
- SQLite may appear only in legacy import/migration tooling that reads an old SQLite database and writes into PostgreSQL.

## Local Test Environment

- Backend pytest needs the dedicated podman container `nd-test-pg` (postgres:16) on host port **55432**; check it with `podman ps --filter name=nd-test-pg`. Both `DATABASE_URL` and `TEST_DATABASE_URL` in `.env` must point at `localhost:55432/news_dashboard_test` as role `news_dashboard` — never at the unrelated native Postgres on 5432 (wrong-instance runs surface as `InsufficientPrivilege`/ownership errors, not connection failures).
- Run backend tests as `source .env && make test`.
- For the full suite, disable parallel query workers first: `export PGOPTIONS='-c max_parallel_workers_per_gather=0'` — otherwise leaked shared-memory segments in the container's `/dev/shm` cause `DiskFull` errors and can crash Postgres into recovery mode, failing 100+ unrelated tests.
- If **every** DB-backed test fails in the truncate fixture with `UndefinedTable`, orphaned tables from an abandoned branch are stuck in the shared container; drop them (they are empty) or reset the container.

## Git Workflow

- Before starting work, fetch and rebase on `origin/main`.
- Keep working branches fast-forwardable with `origin/main`; resolve divergence by rebasing rather than merging.
- Do not use `git push --no-verify` when pushing changes.

## Agent Skills

- Keep Claude and Codex skill access synchronized at all times.
- `.agents/skills` must point at `.claude/skills` so Codex agents see the same project skills without maintaining duplicate copies.
- `CLAUDE.md` must be a symlink to `AGENTS.md` so Claude Code loads these instructions too; edit `AGENTS.md` only.

## Worktrees

- Fresh worktrees lack `.venv`, `node_modules`, and the ignored `.env`; run `scripts/bootstrap-worktree.sh` before testing or committing, and keep `.venv/bin` on `PATH` so pre-commit hooks find their tools.
