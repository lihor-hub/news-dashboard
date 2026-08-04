# FastMCP operations and documentation implementation plan

Issue: #1372

## Goal

Finish the default-enabled FastMCP deployment story on the existing FastAPI listener at `/mcp/`. Add strict HTTP transport protection, privacy-safe health and telemetry, deployed-path integration coverage, and complete operator/client documentation for the seven-tool catalog. MCP remains independent of Keycloak and `MCP_SERVER_ENABLED=false` remains the global shutdown control.

## Locked contracts

- No separate MCP service, port, database exposure, legacy RPC compatibility, or Keycloak credential flow.
- Compose and Helm render `MCP_SERVER_ENABLED=true` unless explicitly set false.
- FastMCP validates exact configured Host and Origin values. Server-to-server clients may omit Origin; a supplied Origin must match.
- `GET /api/mcp/health` returns only `disabled`, `healthy`, or `dependency_failure`; disabled and healthy are HTTP 200, dependency failure is HTTP 503. It exposes no token, catalog, or content.
- Prometheus labels are fixed-cardinality. Non-secret numeric token IDs may occur only in metadata-only structured logs, never metric labels.
- The canonical remote URL is `https://news.example.com/mcp/`, with HTTPS and the path preserved by the reverse proxy.

## Task 1: Deployment defaults and HTTP guard

Write failing tests, then:

- Add typed MCP Host/Origin allowlist configuration and a focused HTTP-app factory.
- Enable FastMCP Host/Origin protection.
- Render the feature flag and safe defaults/overrides in every supported Compose and Helm path.
- Prove false disables transport and token creation, and prove no extra service or port is introduced.
- Cover allowed and rejected Host/Origin requests at the mounted HTTP boundary.

## Task 2: Health and operational telemetry

Write failing tests, then:

- Add the public, content-free MCP health contract with a bounded PostgreSQL readiness check.
- Add fixed-cardinality authentication, tool outcome, duration, rate-limit, and response-limit metrics.
- Add metadata-only structured events without bearer values, arguments, content, prompts, provider bodies, URLs, or exception text.
- Ensure events and counters occur exactly once across middleware short-circuits.

## Task 3: Mounted and deployed-path integration coverage

Write an integration matrix using the official FastMCP client against the real mounted FastAPI app:

- discover exactly the seven authorized tools;
- invoke deterministic tools and an AI-stubbed `ask_news`;
- reject missing, invalid, revoked, and under-scoped tokens;
- preserve cross-user isolation, bounds, rate limits, sanitized errors, strict Host/Origin behavior, and disabled mode;
- exercise the supported application container/front door and prove the SPA fallback does not intercept `/mcp/`.

## Task 4: Complete UI and documentation

- Correct Settings copy to say MCP is default-enabled and read-only, with Ask requiring server-side AI.
- Document all seven tools and exact scope mapping, token creation/rotation/revocation, limits, Ask configuration, health/metrics/logging, HTTPS proxy requirements, and security boundaries.
- Add credential-safe FastMCP Python and Claude Code examples using environment placeholders.
- Remove all legacy `/api/mcp/tools`, `/api/mcp/rpc`, disabled-by-default, and planned-question-answering text.
- Explicitly state that tools expose no SQL, shell, filesystem, secrets, mutations, or direct Keycloak credentials.

## Verification and delivery

After the Ask PR merges, rebase onto `origin/main`, then run focused MCP/backend/frontend/docs/deployment tests plus the repository lint, typecheck, complete PostgreSQL-backed suite, Helm validation, website build, dependency audit, and secret/stale-reference scans. Obtain a separate code review, push a dedicated branch, open a PR closing #1372, monitor CI, and merge when green under repository policy.
