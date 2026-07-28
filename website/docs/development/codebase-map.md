---
title: Codebase map
sidebar_position: 3
---

# Codebase map

Where to look for what. The goal is to shorten the gap between "I want to
change X" and "I have the right file open".

## Top level

| Path | Contains |
|------|----------|
| `backend/` | The FastAPI application (`news_dashboard` package) and its tests. |
| `frontend/` | The React + TypeScript single-page app. |
| `website/` | The Docusaurus documentation site published at [docs.lihor.ro](https://docs.lihor.ro). |
| `docs/` | Repository-local technical docs and ADRs. |
| `helm/` | The `news-dashboard` Helm chart. |
| `deploy/` | Host-level deployment assets (Caddy config, Keycloak theme). |
| `e2e/` | Playwright end-to-end specs. |
| `scripts/` | Development, release, and CI helper scripts. |
| `android/`, `desktop/` | The mobile and desktop client shells. |
| `.github/workflows/` | CI, release, nightly, and security workflows. |

## Backend

The package is `backend/news_dashboard/`. `main.py` is app assembly — CORS,
middleware, the three top-level routers, and `include_router(...)` calls.

Most domains are **feature-module packages** with the same three-file shape:

```
news_dashboard/<module>/
  __init__.py   # package docstring only
  router.py     # APIRouter + endpoint handlers
  service.py    # business logic and DB access
  models.py     # Pydantic request/response models
```

This convention, and the rules that go with it, are documented in
[Feature modules](feature-modules.md).

### Finding a domain

Module names map onto the API surface, so the fastest route from an endpoint
to its code is the path segment:

| Area | Module |
|------|--------|
| Articles, search, highlights | `articles/` |
| Feeds and sources | `sources/` |
| Ingestion and the scheduler | `ingest/`, `scheduler/` |
| Briefings and email digests | `briefings/`, `briefing_email/` |
| Lessons and learning | `learn_from_link/`, `lesson_recaps/`, `quizzes/` |
| Recaps | `recaps/` |
| Assistant, agent actions | `assistant/` |
| Recommendations, personalization | `recommendations_routes/`, `personalization/` |
| AI memory, feedback, stats | `ai_memory/`, `ai_feedback/`, `ai_stats/` |
| Tags, reading list, watchlists | `tags_routes/`, `reading_list/`, `watchlists/` |
| Sharing | `shares/` |
| Auth and users | `auth.py`, `auth_routes/`, `user_settings/` |
| Admin | `admin_routes/` |
| Health, version, config | `system/` |
| Aggregates for charts | `stats/` |
| MCP and Google Reader | `mcp/`, `greader.py` |
| Onboarding | `onboarding/` |

Cross-cutting modules that are not feature packages:

| File | Responsibility |
|------|----------------|
| `auth.py` | Sessions, Keycloak SSO, `require_auth` / `require_admin`. |
| `graph_store.py` | Neo4j boundary. Optional; faked in tests. |
| `entities.py` | Entity extraction feeding the knowledge graph. |
| `email.py` | Outbound mail. |

### Migration in progress

`main.py` was ~2,600 lines mounting 117 endpoints before the feature-module
split. Extraction is incremental, so `main.py` still holds a mix of extracted
and not-yet-extracted domains. If a route is not in a feature package, it is
still in `main.py` — that is expected, not an oversight.

## Frontend

```
frontend/src/
  api/         # API client functions
  components/  # Reusable components
  contexts/    # React contexts
  hooks/       # Custom hooks
  lib/         # Utilities, i18n setup
  locales/     # Translation resources
  pages/       # Route-level pages (~35)
  types/       # Shared TypeScript types
  __tests__/   # Vitest suites
```

Pages are named for what they render — `InboxPage`, `FeedsPage`,
`LessonDetailPage`, `AdminPage` — so the UI route usually names its own file.

All user-facing strings must be externalized for translation. Add keys to
`frontend/src/locales/en/translation.json` using nested, descriptive names
(`feature.action.label`) and printf-style placeholders for interpolation.
Avoid building sentences by concatenation — it does not survive translation.

## Common tasks

| I want to… | Start at |
|------------|----------|
| Add a feed source or scraper | `backend/news_dashboard/ingest/` |
| Add a backend endpoint | The relevant feature module's `router.py` |
| Add a new backend domain | [Feature modules](feature-modules.md) |
| Work on UI components | `frontend/src/components/`, `frontend/src/pages/` |
| Add or fix translations | `frontend/src/locales/` |
| Write backend tests | `backend/tests/` |
| Change Docker or Helm packaging | `helm/`, `Dockerfile`, `docker-compose.yml` |
| Edit the published docs | `website/docs/` |
| Change CI | `.github/workflows/` |

## CI workflows

| Workflow | Runs |
|----------|------|
| `ci.yml` | The `make check` gate on pull requests. |
| `nightly.yml` | The full suite with coverage. |
| `release.yml` | Version derivation, image build, release publication. |
| `docs.yml` | Builds and deploys the documentation site. |
| `codeql.yml`, `trivy-scan.yml`, `dependency-review.yml` | Security scanning. |
| `android.yml`, `desktop.yml` | Client builds. |

Several `scripts/test_*.py` files test the workflows and packaging themselves —
`test_release_sync_workflow.py`, `test_helm_postgres_backup.py`,
`test_ci_deploy_namespace.py` and others. If you change a workflow or chart,
check whether a script asserts on it.
