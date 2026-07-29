---
title: Development
sidebar_position: 1
---

# Development

Working documentation for people changing the code: how the repository is
organized, how to get a local environment that matches CI, and the conventions
a change is expected to follow.

This complements rather than repeats the other sections:

| If you want to… | Read |
|-----------------|------|
| Submit a change and get it merged | [Contributing](../contributing/index.md) |
| Understand the runtime shape of the system | [Architecture](../architecture/index.md) |
| Run an instance | [Self-hosting](../self-hosting/index.md) |
| Call the HTTP API | [API reference](../api/index.md) |
| Change code | this section |

## Pages

| Page | Covers |
|------|--------|
| [Environment setup](environment-setup.md) | Toolchain, `.env`, the test database, worktrees. |
| [Codebase map](codebase-map.md) | Where things live in backend, frontend, and infra. |
| [Feature modules](feature-modules.md) | The router/service/models convention for backend domains. |
| [Testing](testing.md) | Test lanes, markers, and the failure modes worth recognizing. |
| [Release process](release-process.md) | How versions are derived and released. |

## Shape of the system

News Dashboard is a **modular monolith**, not a microservice platform. One
FastAPI application serves the JSON API and, in container and Kubernetes
deployments, also serves the built React frontend. Scheduled ingestion runs as
a separate batch workload.

That has direct consequences for development:

- There is one backend process to run locally. You do not need a service mesh
  or a docker-compose stack of interdependent services to work on a feature.
- Backend domains are separated by **package boundaries**, not network
  boundaries — see [Feature modules](feature-modules.md).
- The frontend talks to the same API documented in the
  [API reference](../api/index.md). There is no private back channel, so
  anything the UI can do can be reproduced with `curl`.

## Two constraints worth knowing before you start

Both are enforced in review and encoded in tooling. They are stated here so
they do not come as a surprise mid-change.

### PostgreSQL only, at runtime

Runtime database code must be written for PostgreSQL and psycopg: `%s`
parameters, PostgreSQL functions and operators, `ON CONFLICT` upserts.

Do not add SQLite fallbacks, database-type sniffing, placeholder translation
layers, or generic multi-database SQL. SQLite appears in this repository only
as an *input format* for legacy migration tooling that reads an old local
database and writes into PostgreSQL.

This is recorded as
[ADR 0001](https://github.com/lihor-hub/news-dashboard/blob/main/docs/adr/0001-postgresql-only-runtime.md).
PostgreSQL must also have the [pgvector](https://github.com/pgvector/pgvector)
extension available — embeddings live in `articles.embedding_vec` and
similarity search runs as SQL `<=>` queries over an HNSW index.

### `make check` is the gate

```bash
make check
```

runs lint, type checking, tests, and the production frontend build — the same
set CI runs. If it passes locally, CI should be green.

Individual lanes are documented in [Testing](testing.md).

## Where decisions are recorded

Significant technical decisions live in
[`docs/adr/`](https://github.com/lihor-hub/news-dashboard/tree/main/docs/adr)
as Architecture Decision Records. Read the relevant ADR before proposing a
change that contradicts one — the record states the context and the
alternatives that were rejected, which is usually the fastest way to find out
whether your case is genuinely new.

Current records:

| ADR | Decision |
|-----|----------|
| 0001 | PostgreSQL-only runtime. |
| 0002 | LLM gateway with fallback. |
| 0003 | Feature-module packages (`router` / `service` / `models`). |

Adding one: copy `docs/adr/0000-template.md`, number it sequentially, and
include it in the PR that implements the decision.
