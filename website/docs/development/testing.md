---
title: Testing
sidebar_position: 5
---

# Testing

Which lane to run when, and the environment-shaped failures that are worth
recognizing on sight rather than debugging from scratch.

## Lanes

| Command | Runs |
|---------|------|
| `make test` | Backend pytest with coverage + frontend Vitest. The everyday loop. |
| `make test-smoke` | Fast smoke tests — app boot, health, core API paths. |
| `make test-backend` | All backend pytest tests. |
| `make test-frontend` | All frontend Vitest tests. |
| `make test-e2e` | Playwright end-to-end specs. |
| `make test-a11y` | Accessibility checks (axe-core, serious/critical). |
| `make test-nightly` | Full suite with coverage — what nightly CI runs. |
| `make check` | The complete gate: lint, typecheck, test, build. |

`make check` is what CI runs on a pull request. Run it before pushing.

## Static analysis

`make lint` and `make typecheck` run more tools than most projects:

| Tool | Checks |
|------|--------|
| `ruff` | Python lint + format. |
| `mypy`, `ty`, `pyrefly` | Three Python type checkers, all of which must pass. |
| `vulture` | Dead Python code (confidence ≥ 80). |
| `eslint`, `prettier` | Frontend lint and formatting. |
| `knip` | Dead TypeScript exports and unused dependencies. |
| `tsc` | TypeScript types. |

Dead-code detection is part of the gate, not advisory. If `vulture` flags a
symbol you deliberately keep, add it to `backend/vulture_whitelist.py` rather
than disabling the check.

## Markers

Select or exclude backend tests by marker (`--strict-markers` is on, so unknown
markers are an error, not a typo that silently passes):

| Marker | Meaning |
|--------|---------|
| `smoke` | Fast, high-signal: app boot, health, core API paths. No external services. |
| `db` | Requires a live PostgreSQL instance. |
| `postgres` | Alias for `db`. |
| `perf_serial` | Timing-sensitive benchmarks; should run without xdist load. |
| `slow` | Expensive; reserved for the nightly suite. |

```bash
pytest -m smoke -v
pytest -m "not slow"
```

Tests run under `pytest-xdist` (`-n auto`) by default.

## Environment-shaped failures

These three account for most "everything is broken" reports. Each has a
distinctive signature.

### Every DB test fails with `InsufficientPrivilege`

The tests are connected to the **wrong PostgreSQL instance** — typically a
native server on 5432 instead of the dedicated `nd-test-pg` container on
**55432**. The connection succeeds, so this does not look like a configuration
error; it fails on ownership instead.

Check `DATABASE_URL` and `TEST_DATABASE_URL` in `.env`. See
[Environment setup](environment-setup.md#the-test-database).

### `DiskFull` errors, or Postgres drops into recovery

Leaked shared-memory segments in the test container's `/dev/shm`, caused by
parallel query workers. This can crash PostgreSQL into recovery and fail 100+
unrelated tests, which makes it look like a code regression.

Disable parallel query workers before a full run:

```bash
export PGOPTIONS='-c max_parallel_workers_per_gather=0'
```

### Every DB test fails with `UndefinedTable` in the truncate fixture

Orphaned tables from an abandoned branch are stuck in the shared test
container. They are empty — drop them, or reset the container.

## Route assertions

Feature-module routers mount lazily as `_IncludedRouter` objects. Assert
against resolved OpenAPI paths rather than `app.routes`:

```python
paths = app.openapi()["paths"]
assert "/api/sources/{slug}/enabled" in paths
```

## Optional integrations

Neo4j graph features activate only when `NEO4J_URI`, `NEO4J_USER`, and
`NEO4J_PASSWORD` are configured. **Unit tests fake the graph boundary** — do
not make the normal suite require a live Neo4j.

When changing graph behavior, add tests around `graph_store.py`, `entities.py`,
or the relevant frontend component, then run the targeted backend and Vitest
suites.

## Packaging tests

`scripts/test_*.py` assert on workflows, the Helm chart, and repository
metadata — release sync, Postgres backup templates, CI deploy namespace, Trivy
workflows, agent-skill sync, and others. Changing a workflow or chart template
often means updating one of these.

Validate the chart directly with:

```bash
make helm-validate
```

which lints and renders it under default, production-like, and
external-database value sets.
