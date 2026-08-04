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

## Review repair

- Added an outer ASGI Host/Origin guard so exact routing-header validation runs
  before FastMCP authentication. Unconfigured hosts (including implicit test or
  server hosts) now return a generic 421; an Origin is optional but, when sent,
  must exactly match an allowlisted scheme and authority or receives a generic
  403.
- Changed production Compose to require `APP_BASE_URL` and pass empty optional
  MCP overrides, allowing the application to derive its exact public host and
  origin instead of injecting localhost values.
- Changed Helm MCP allowlist defaults to empty and derive them from
  `app.publicBaseUrl` or the configured ingress. Localhost values remain only
  for development renders with no public URL or ingress. The production values
  now exercise ingress derivation rather than repeating the public hostname.
- Added regressions for implicit hosts, same-host wrong-scheme origins,
  production Compose fail-closed configuration, production ingress derivation,
  and Helm public-base-URL derivation.

Repair verification:

- Focused config/Compose/Helm tests: `50 passed`.
- All MCP plus deployment tests: `213 passed`; three unrelated workers hit the
  shared PostgreSQL container's `max_locks_per_transaction` limit. The affected
  briefing module passed serially: `64 passed`.
- `make lint`: passed.
- `make typecheck`: passed.
- `git diff --check`: passed.
