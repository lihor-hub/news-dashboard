---
title: Environment setup
sidebar_position: 2
---

# Environment setup

What you need installed, how the local database is expected to be wired, and
the setup mistakes that produce confusing failures later.

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.14+ |
| Node.js | LTS |
| PostgreSQL | 16+ with the [pgvector](https://github.com/pgvector/pgvector) extension |

Use the `pgvector/pgvector:pg16` image rather than stock `postgres:16` — plain
PostgreSQL lacks the `vector` extension, and the failure surfaces late, as a
migration or query error rather than a connection error.

A pre-configured **Dev Container** and **GitHub Codespace** are available and
skip the manual steps below.

## Install

```bash
make install
```

This installs the backend in editable mode with dev extras, installs frontend
dependencies, and registers pre-commit hooks.

Use `make ci-install` when you need reproducibility — it runs `npm ci` against
`package-lock.json` instead of `npm install`, so the lockfile is respected
rather than updated.

## Configuration

Copy `.env.example` to `.env` and fill it in. The database can be configured
two ways:

- `DATABASE_URL` pointing at PostgreSQL, or
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and
  `POSTGRES_PASSWORD`.

`.env` is git-ignored. It is not copied into new worktrees automatically —
see [Worktrees](#worktrees) below.

## The test database

Backend tests need a live PostgreSQL instance. The project convention is a
**dedicated container**, deliberately not the Postgres you might already run
on port 5432:

| Setting | Value |
|---------|-------|
| Container | `nd-test-pg` (`postgres:16`) |
| Host port | **55432** |
| Database | `news_dashboard_test` |
| Role | `news_dashboard` |

Check it is running:

```bash
podman ps --filter name=nd-test-pg
```

Both `DATABASE_URL` and `TEST_DATABASE_URL` in `.env` must point at
`localhost:55432/news_dashboard_test` as role `news_dashboard`.

:::warning Pointing at the wrong instance is the most common setup failure
If these point at an unrelated native PostgreSQL on 5432, tests do **not** fail
with a connection error. They connect successfully and then fail with
`InsufficientPrivilege` or ownership errors, because the role does not own the
objects. If you are seeing permission errors from a database that is clearly
reachable, check the port before anything else.
:::

Run backend tests with the environment loaded:

```bash
source .env && make test
```

## Running the app

The README covers the full local run. In short: the backend serves the API,
and the frontend dev server proxies to it. `make build` produces the
production frontend bundle that the backend serves in container deployments.

## Worktrees

A fresh `git worktree` has no `.venv`, no `node_modules`, and no `.env` —
`.env` is ignored, so git does not carry it across. Bootstrap before testing
or committing:

```bash
scripts/bootstrap-worktree.sh
```

The script copies `.env` from the main checkout, creates the virtualenv with
`uv sync --frozen --all-extras` (which leaves `uv.lock` untouched, unlike
`make install`), runs `npm ci`, and verifies that `DATABASE_URL` and
`TEST_DATABASE_URL` are actually set — failing loudly rather than letting you
discover it during a test run. It is safe to re-run.

Keep `.venv/bin` on `PATH` in the worktree so pre-commit hooks find their
tools — several hooks invoke `.venv/bin/<tool>` directly.

## Pre-commit hooks

`make install` registers the pre-commit stage. Hooks are scoped by file type,
so a docs-only commit does not run mypy or ESLint.

To also gate pushes:

```bash
pre-commit install --hook-type pre-push
```

The pre-push stage re-runs linters and type checkers — so a push is blocked
even if individual commits skipped hooks — and adds the test suites, which are
too slow for every commit.

Do not use `git push --no-verify`.

Run everything manually with:

```bash
pre-commit run --all-files
```
