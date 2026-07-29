---
title: Feature modules
sidebar_position: 4
---

# Feature modules

Backend domains are organized as **feature-module packages**. This page is the
practical guide; the reasoning is recorded in
[ADR 0003](https://github.com/lihor-hub/news-dashboard/blob/main/docs/adr/0003-feature-module-packages.md).

## Why

`main.py` had grown to roughly 2,600 lines mounting 117 endpoints across three
routers, with handlers, Pydantic models, and business logic interleaved. It was
a merge-conflict hotspot with no consistent home for a domain's models.

Feature modules give every domain the same shape and collapse `main.py` toward
pure app assembly.

## The shape

```
news_dashboard/<module>/
  __init__.py   # package docstring; do NOT re-export `router`
  router.py     # APIRouter + endpoint handlers; thin, delegates to service
  service.py    # business logic, DB access, external calls
  models.py     # Pydantic request/response models
```

`quizzes/` (reading goals and weekly quizzes) is the reference implementation.
`sources/` is a good second example.

The split is a real boundary, not a filing convention:

- `router.py` handles HTTP — parsing, validation, status codes. It should stay
  thin.
- `service.py` holds the logic and owns database access. It should be callable
  without a request object.
- `models.py` holds the Pydantic models for that domain and nothing else.

## Rules

### The router carries no auth dependency of its own

A feature router is mounted onto an existing router in `main.py` and inherits
that router's gate:

```python
api.include_router(quizzes_router)   # inherits require_auth
```

Do not add a blanket `dependencies=[Depends(require_auth)]` to the feature
router itself. Handlers still declare `Depends(require_auth)` individually
where they need the current user object.

Mount points:

| Router in `main.py` | Gate |
|---------------------|------|
| `api` | `require_auth` — the normal case. |
| `admin` | `require_admin`, prefix `/api/admin`. |
| `public_router` | No session required. Use deliberately. |

### Import the router from the submodule

```python
from news_dashboard.quizzes.router import router as quizzes_router
```

`__init__.py` deliberately does **not** re-export `router`. Re-exporting it
would shadow the `router` submodule name and break this import.

### Migrations are behavior-preserving

When extracting an existing domain out of `main.py`, do not change route paths,
status codes, or auth semantics in the same change. Move the code, keep the
behavior. Functional changes belong in a separate, reviewable commit.

### One domain per pull request

Extract one domain at a time and update its importers and tests in the same PR.

## Adding a new domain

1. Create `backend/news_dashboard/<module>/` with the four files.
2. Define the `APIRouter` in `router.py` with no blanket auth dependency.
3. Put logic and DB access in `service.py`, request/response models in
   `models.py`.
4. Import the router in `main.py` and mount it on `api` (or `admin`).
5. Add tests under `backend/tests/`.
6. Run `make check`.

### Writing the database layer

Runtime SQL is PostgreSQL-specific and uses psycopg `%s` placeholders:

```python
cur.execute(
    "SELECT id, title FROM articles WHERE user_id = %s AND state = %s",
    (user_id, state),
)
```

No SQLite fallbacks, no database-type sniffing, no placeholder translation.
See [ADR 0001](https://github.com/lihor-hub/news-dashboard/blob/main/docs/adr/0001-postgresql-only-runtime.md).

### Returning collections

List endpoints return the standard envelope. Compute `has_more` by fetching one
row past the limit rather than issuing a second `COUNT` query:

```python
items = service.list_things(limit=limit + 1, offset=offset)
return {
    "items": items[:limit],
    "limit": limit,
    "offset": offset,
    "has_more": len(items) > limit,
}
```

Bound `limit` in the signature so out-of-range values are rejected with `422`
by FastAPI rather than reaching the service:

```python
limit: Annotated[int, Query(ge=1, le=500)] = 100,
offset: Annotated[int, Query(ge=0)] = 0,
```

### Bound untrusted input

Anything user-supplied that reaches retrieval, prompt construction, or storage
needs an explicit ceiling, so a malformed client cannot generate oversized LLM
requests. Existing limits to follow as precedent: OPML import is capped at
5 MiB and 1000 outlines; account import at 20 MiB.

## Testing feature modules

Routers mount lazily as `_IncludedRouter` objects. Assertions about routes must
target the **resolved OpenAPI paths**, not `app.routes`:

```python
paths = app.openapi()["paths"]
assert "/api/quizzes/{quiz_id}/submit" in paths
```

Inspecting `app.routes` directly gives misleading results for lazily mounted
routers — this is the single most common surprise when writing route tests
here.
