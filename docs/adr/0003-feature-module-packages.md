# Feature-Module Packages (router / service / models)

- Status: accepted
- Deciders: ioachim-hub
- Date: 2026-07-02

Technical Story: [Issue #825](https://github.com/lihor-hub/news-dashboard/issues/825), [Tracking #826](https://github.com/lihor-hub/news-dashboard/issues/826), [main.py](../../backend/news_dashboard/main.py)

## Context and Problem Statement

`backend/news_dashboard/main.py` had grown to ~2,600 lines and mounted **117
endpoints** across three routers (`public_router`, `api`, `admin`). Route
handlers, Pydantic request/response models, and business logic were interleaved
in a single module, while some domain logic lived in flat sibling modules
(`quiz.py`, `shares.py`, `sources.py`, …). This made `main.py` a merge-conflict
hotspot, blurred the boundary between the HTTP layer and business logic, and
gave no consistent home for a domain's request models.

We need a predictable, per-domain structure that shrinks `main.py` to
app assembly and keeps each feature's HTTP surface, logic, and models together.

## Decision Drivers

- Reviewability — smaller, domain-scoped diffs instead of one giant module.
- Clear separation of the HTTP layer (router) from business logic (service).
- A single, obvious home for each domain's request/response models.
- Behavior preservation — no route paths or auth semantics change during migration.

## Considered Options

- **Option 1: Feature-module packages** — each domain becomes a package
  `news_dashboard/<module>/` with `router.py` (FastAPI `APIRouter` + endpoints),
  `service.py` (business logic / DB access), and `models.py` (Pydantic models).
  `main.py` imports each router and calls `include_router(...)`.
- **Option 2: Flat modules per concern** — keep single-file modules
  (`<module>_router.py`, `<module>_service.py`) without packages.
- **Option 3: Status quo** — keep routes and models in `main.py`, logic in flat
  sibling modules.

## Decision Outcome

Chosen option: **Option 1: Feature-module packages**, because the package
boundary gives every domain the same three-file shape, keeps related code
physically together, and lets `main.py` collapse to app setup plus
`include_router(...)` calls.

Layout:

```
news_dashboard/<module>/
  __init__.py   # package docstring; do NOT re-export `router` (it shadows the submodule)
  router.py     # APIRouter + endpoint handlers; thin, delegates to service
  service.py    # business logic, DB access, external calls
  models.py     # Pydantic request/response models
```

Rules:

- The router carries **no blanket auth dependency of its own**; it is mounted on
  `main`'s existing router (typically the authenticated `api` router) via
  `api.include_router(...)`, inheriting that router's `require_auth` gate.
  Handlers still `Depends(require_auth)` to receive the current user.
- Import the router explicitly from the submodule
  (`from news_dashboard.quizzes.router import router`) — `__init__.py` does not
  re-export it, so the `router` submodule name is never shadowed.
- Migrations are **behavior-preserving**: no route path or status-code changes.
- One domain per pull request; update importers and tests in the same PR.

The `quizzes` package (Reading Goals + weekly quizzes) is the reference
implementation. The remaining ~16 domains are tracked in
[#826](https://github.com/lihor-hub/news-dashboard/issues/826) and follow this
same shape. This constraint is also encoded in the `python-dev` agent skill.

### Consequences

- **Good (Pros)**:
  - `main.py` shrinks toward pure app assembly; domain code is co-located.
  - Smaller, domain-scoped diffs and far fewer merge conflicts.
  - New endpoints have an obvious home; models stop piling up in `main.py`.
- **Bad (Cons)**:
  - More files/directories to navigate for a single domain.
  - The full migration spans many PRs, so `main.py` holds a mix of old-style and
    extracted domains until the tracking issue is complete.
- **Neutral/Other**:
  - Routers mount lazily as `_IncludedRouter` objects, so route assertions in
    tests should target the resolved OpenAPI paths, not `app.routes`.
