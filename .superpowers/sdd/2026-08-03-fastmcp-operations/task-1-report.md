# Task 1 report: deployment defaults and HTTP guard

## Delivered

- Added immutable `McpHttpConfig` parsing for exact Host and Origin allowlists.
- Derived public defaults from `APP_BASE_URL`, with safe localhost defaults for local installs.
- Rejected wildcard allowlist values to keep the transport contract exact.
- Added `create_mcp_http_app` and enabled FastMCP strict Host/Origin protection.
- Kept MCP on the existing FastAPI listener and preserved the explicit-false transport/token shutdown behavior.
- Rendered `MCP_SERVER_ENABLED=true` and Host/Origin settings in all three Compose paths and the Helm chart.
- Added production Helm values for `news.lihor.ro`; no MCP service, port, or database exposure was added.

## TDD evidence

The first focused run failed because the config/factory module and deployment values did not exist. After the implementation, the same focused test set passed.

## Verification

- Focused MCP, briefing, config, Compose, and Helm tests: `214 passed`.
- `make lint`: passed (backend and frontend lint/format/dead-code gates).
- `make typecheck`: passed (mypy, ty, pyrefly, and frontend typecheck).
- `git diff --check`: passed.

The shared PostgreSQL container was neither started, stopped, nor reconfigured.
