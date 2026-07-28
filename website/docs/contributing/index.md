# Contributing

How to set up a development environment, run tests, and submit changes to
News Dashboard.

## Prerequisites

- Python 3.14+
- Node.js LTS
- PostgreSQL 16+ with the [pgvector](https://github.com/pgvector/pgvector) extension
  (use the `pgvector/pgvector:pg16` image)
- A running PostgreSQL instance for backend tests and local development

Start with the root
[README local-development guide](https://github.com/lihor-hub/news-dashboard#local-development)
for the full setup flow, then see
[Development → Environment setup](../development/environment-setup.md) for the
test-database wiring and worktree bootstrap.

:::tip Working on the code
The [Development](../development/index.md) section covers the
[codebase map](../development/codebase-map.md), the
[feature-module convention](../development/feature-modules.md) every backend
domain follows, and [testing](../development/testing.md). The
[API reference](../api/index.md) documents the HTTP surface.
:::

## Quality gate

Run the full check before opening a PR:

```bash
make check
```

Useful smaller lanes:

| Target | What it does |
|--------|--------------|
| `make lint` | Ruff, ESLint, and Prettier checks. |
| `make format` | Auto-format backend and frontend files. |
| `make typecheck` | mypy and TypeScript checks. |
| `make test` | Backend pytest and frontend Vitest suites. |
| `make test-smoke` | Fast smoke tests for active development. |
| `make test-e2e` | Playwright end-to-end tests. |
| `make helm-validate` | Lint and render the Helm chart. |

## Git workflow

- Rebase on `origin/main` before pushing.
- Keep branches fast-forwardable with `main`; resolve divergence by rebasing.
- Do not use `git push --no-verify`.
- Use Conventional Commit titles such as `fix: correct source health status`
  or `docs: refresh self-hosting guide`.

## PostgreSQL runtime rule

Runtime database code must use PostgreSQL-specific SQL and psycopg `%s`
parameters. Do not add SQLite runtime fallbacks, database-type sniffing,
placeholder translation layers, or generic multi-database SQL.

SQLite may appear only in legacy migration tooling that reads an old SQLite
database and writes into PostgreSQL.

## Optional Neo4j graph store

Graph features use Neo4j only when `NEO4J_URI`, `NEO4J_USER`, and
`NEO4J_PASSWORD` are configured. Unit tests fake the graph boundary; do not
require a live Neo4j instance for the normal test suite. When you change graph
behavior, add tests around `backend/news_dashboard/graph_store.py`,
`backend/news_dashboard/entities.py`, or the relevant frontend component, then
run the targeted backend and Vitest suites.

## Opening a PR

1. Pick or create an issue with clear acceptance criteria.
2. Create a branch from an up-to-date `main`.
3. Make the change and add or update tests where behavior changes.
4. Run the relevant quality gate locally.
5. Open a PR with a concise summary and link the issue with `Closes #123`.

See the root
[CONTRIBUTING.md](https://github.com/lihor-hub/news-dashboard/blob/main/CONTRIBUTING.md)
for repository governance, versioning, and internationalization details.
