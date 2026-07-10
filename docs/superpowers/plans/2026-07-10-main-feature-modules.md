# Main Feature Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete issue #826 in one pull request by moving every remaining HTTP handler, request model, and domain helper out of `backend/news_dashboard/main.py` into feature-module packages without changing the API contract.

**Architecture:** Preserve the accepted ADR 0003 shape: each HTTP domain owns `router.py`, `service.py`, and `models.py`, and `main.py` mounts routers on the existing public, authenticated, or admin parent router. Existing flat domain modules that conflict with package names move intact to the package's `service.py`; all importers are updated explicitly rather than relying on package re-exports.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, PostgreSQL/psycopg, pytest, ruff, mypy, ty, pyrefly.

## Global Constraints

- Deliver all remaining domains in one branch and one PR, with domain-sized commits.
- Preserve every route path, HTTP method, status code, dependency, response shape, and OpenAPI operation.
- Mount authenticated routers on `api`, public routers on `public_router` or `app`, and admin routers on `admin`; do not duplicate blanket auth dependencies.
- Keep PostgreSQL-specific SQL and psycopg `%s` parameters; add no SQLite runtime fallback.
- Import routers from their submodules; do not re-export a `router` object from package `__init__.py` files.
- End with no FastAPI route-decorated functions or request models in `main.py`.

---

### Task 1: Lock the structural and route contract

**Files:**
- Create: `backend/tests/test_main_feature_modules.py`
- Modify: `backend/news_dashboard/main.py`

**Interfaces:**
- Consumes: `news_dashboard.main.app` and the accepted package list.
- Produces: a source-level invariant that `main.py` has no route decorators or request models and an OpenAPI route manifest captured before extraction.

- [ ] **Step 1: Write the failing structural test**

```python
def test_main_contains_app_assembly_not_route_handlers() -> None:
    source = Path(main.__file__).read_text()
    tree = ast.parse(source)
    decorated_routes = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_route_decorator(decorator) for decorator in node.decorator_list)
    ]
    request_models = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "BaseModel" for base in node.bases)
    ]
    assert decorated_routes == []
    assert request_models == []
```

- [ ] **Step 2: Run the test and verify red**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest backend/tests/test_main_feature_modules.py -q`

Expected: failure listing the route handlers and request models still declared in `main.py`.

- [ ] **Step 3: Capture the resolved OpenAPI method/path manifest in the test**

```python
actual = {
    (method.upper(), path)
    for path, operations in app.openapi()["paths"].items()
    for method in operations
    if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
}
assert actual == EXPECTED_METHOD_PATHS
```

- [ ] **Step 4: Keep the manifest green before extraction**

Run: `PATH="$PWD/.venv/bin:$PATH" pytest backend/tests/test_main_feature_modules.py -q`

Expected: only the structural assertion fails; the OpenAPI manifest passes.

### Task 2: Extract ingest, articles, shares, sources, and watchlists

**Files:**
- Create: `backend/news_dashboard/articles/{__init__.py,models.py,router.py,service.py}`
- Create: `backend/news_dashboard/watchlists/{__init__.py,models.py,router.py,service.py}`
- Move: `backend/news_dashboard/ingest.py` to `backend/news_dashboard/ingest/service.py`
- Move: `backend/news_dashboard/shares.py` to `backend/news_dashboard/shares/service.py`
- Move: `backend/news_dashboard/sources.py` to `backend/news_dashboard/sources/service.py`
- Create beside each moved service: `__init__.py`, `models.py`, `router.py`
- Modify: every importer found by `rg 'news_dashboard\.(ingest|shares|sources)' backend`
- Modify: `backend/news_dashboard/main.py`

**Interfaces:**
- Consumes: existing service function signatures from the flat modules and existing `require_auth`/`require_admin` dependencies.
- Produces: `articles_router`, `articles_public_router`, `ingest_router`, `shares_router`, `sources_router`, and `watchlists_router` mounted by `main.py`.

- [ ] **Step 1: Move request models and domain constants into each `models.py`**
- [ ] **Step 2: Move handler bodies unchanged into each `router.py`, replacing direct flat-module imports with `from news_dashboard.<domain> import service`**
- [ ] **Step 3: Move non-HTTP helpers and database/external work into `service.py`**
- [ ] **Step 4: Mount the routers and run focused article/share/source/watchlist/ingest tests**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests -q -k 'article or share or source or watchlist or ingest'`

Expected: all selected tests pass and the route manifest remains unchanged.

### Task 3: Extract scheduler, stats, and briefings

**Files:**
- Move: `backend/news_dashboard/scheduler.py` to `backend/news_dashboard/scheduler/service.py`
- Move: `backend/news_dashboard/stats.py` to `backend/news_dashboard/stats/service.py`
- Move: `backend/news_dashboard/briefings.py` to `backend/news_dashboard/briefings/service.py`
- Create beside each moved service: `__init__.py`, `models.py`, `router.py`
- Modify: every importer found by `rg 'news_dashboard\.(scheduler|stats|briefings)' backend`
- Modify: `backend/news_dashboard/main.py`

**Interfaces:**
- Consumes: the existing scheduler singleton, run-history helpers, briefing generation/chat/podcast functions, and admin dependencies.
- Produces: authenticated/admin scheduler and stats routers plus authenticated and public briefing routers.

- [ ] **Step 1: Move `IntervalUpdate`, briefing create/chat models, and route constants into models**
- [ ] **Step 2: Move the handler bodies without changing public podcast token semantics**
- [ ] **Step 3: Mount authenticated and public routers on their original parent routers**
- [ ] **Step 4: Run focused scheduler/stats/briefing tests and the route manifest**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests -q -k 'scheduler or stats or briefing or podcast'`

Expected: all selected tests pass.

### Task 4: Extract users/settings, assistant/actions, tags, analytics events, and admin

**Files:**
- Create: `backend/news_dashboard/user_settings/{__init__.py,models.py,router.py,service.py}`
- Create: `backend/news_dashboard/assistant/{__init__.py,models.py,router.py,service.py}`
- Create: `backend/news_dashboard/tags_routes/{__init__.py,models.py,router.py,service.py}`
- Create: `backend/news_dashboard/events/{__init__.py,models.py,router.py,service.py}`
- Create: `backend/news_dashboard/admin_routes/{__init__.py,models.py,router.py,service.py}`
- Modify: `backend/news_dashboard/main.py`

**Interfaces:**
- Consumes: existing account import/export, preferences, notification, push, AI, agent action, tag, analytics, and Keycloak admin services.
- Produces: one router per domain, with admin routes mounted below the existing `/api/admin` prefix.

- [ ] **Step 1: Move all remaining Pydantic request models into their owning `models.py`**
- [ ] **Step 2: Move handlers and their private helpers into the corresponding router/service files**
- [ ] **Step 3: Mount all routers in `main.py` and remove now-unused imports/constants**
- [ ] **Step 4: Run focused tests and confirm the structural test turns green**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests/test_main_feature_modules.py backend/tests -q -k 'settings or notification or assistant or agent_action or tag or admin or analytics'`

Expected: all selected tests pass; `main.py` contains no route handlers or request models.

### Task 5: Verify, review, and ship

**Files:**
- Modify only files required by confirmed review findings.

**Interfaces:**
- Consumes: the complete refactor diff.
- Produces: a rebased, reviewed PR that closes #826 and is queued for squash auto-merge.

- [ ] **Step 1: Format and lint**

Run: `PATH="$PWD/.venv/bin:$PATH" make format && PATH="$PWD/.venv/bin:$PATH" make lint`

Expected: ruff formatting produces no remaining diff on a second run; lint exits zero.

- [ ] **Step 2: Run all type checkers**

Run: `PATH="$PWD/.venv/bin:$PATH" make typecheck`

Expected: mypy, ty, and pyrefly exit zero.

- [ ] **Step 3: Run the full PostgreSQL test suite**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- make test`

Expected: pytest and coverage exit zero.

- [ ] **Step 4: Review the diff once, fix confirmed findings, and repeat affected gates**
- [ ] **Step 5: Rebase on `origin/main`, push, open one PR with `Closes #826`, enable squash auto-merge, watch required CI, and confirm merge/issue closure**
