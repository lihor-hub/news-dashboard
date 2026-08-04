# Task 3 report: mounted and container integration

## Outcome

Implemented the deployed-path integration slice in commit `7c80c74a`.

- Added an official FastMCP Client harness that traverses the real mounted `news_dashboard.main.app` route table.
- Proved exact seven-tool discovery and representative search, article, briefing, and AI-stubbed Ask calls.
- Proved under-scoped, revoked, missing, invalid, cross-user, disabled, Host, and Origin behavior through the mounted front door.
- Proved `/mcp/` is reserved before the SPA fallback and never returns the SPA document for transport failures.
- Added an isolated real-container smoke using the normal Dockerfile/CMD, a private pgvector network, a non-logged bearer, the official external client, disabled-mode restart, and no PostgreSQL host port.
- Added the container smoke as a merge-group/PR CI lane and made the required `Test & build` rollup fail when it fails.

## TDD evidence

Initial focused run: 3 failed / 1 passed. The failures exposed two real harness boundaries: strict Host protection rejected Starlette's default `testserver`, and FastMCP lifespan teardown wrapped expected client authentication failures in an exception group. The helper was corrected to send the deployed Host and preserve the leaf client error after lifespan shutdown.

Final focused run:

```text
17 passed, 18 pre-existing Starlette/TestClient deprecation warnings
```

The run covered `test_mcp_integration.py`, `test_mcp_deployment.py`, `test_mcp_operations.py`, and `test_spa_static.py`. Ruff, Ruff format, mypy, ty, pyrefly, workflow YAML parsing, shell syntax, pre-commit, and `git diff --check` passed.

## Verification limitation

The real container script could not execute locally because Docker Desktop was not running (`Cannot connect to the Docker daemon`). The script is syntax-checked and its safety/wiring contract is tested locally; the new merge-gating Ubuntu CI lane executes the actual Docker build and probes before merge.
