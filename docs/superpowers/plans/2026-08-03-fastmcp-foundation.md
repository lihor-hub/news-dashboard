# FastMCP Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom MCP-style RPC with a default-enabled, authenticated FastMCP Streamable HTTP server and one complete `list_latest_news` tool, closing GitHub issue #1367.

**Architecture:** Build an explicit `FastMCP` server inside the existing `news_dashboard.mcp` feature package and mount its stateless HTTP ASGI application at `/mcp` before the SPA fallback. A custom FastMCP `TokenVerifier` adapts the existing hashed, scoped `ndmcp_` token store into `AccessToken` identity; tools derive the user ID from the verified token and reuse existing PostgreSQL services. The legacy `/api/mcp/tools` and `/api/mcp/rpc` transport is removed in the same change while the authenticated token-management REST API and Settings UI remain.

**Tech Stack:** Python 3.14, FastAPI/Starlette, FastMCP 3.4+, PostgreSQL/psycopg, pytest, uv.

## Global Constraints

- Runtime database access is PostgreSQL-only and uses psycopg `%s` parameters; do not add SQLite fallbacks or database sniffing.
- MCP authentication is independent of Keycloak and browser sessions.
- `MCP_SERVER_ENABLED` defaults to enabled when absent; explicit `false`, `0`, `no`, or `off` disables MCP access and new token creation.
- The endpoint is stateless Streamable HTTP at `/mcp`; no sidecar service or stdio adapter is added.
- The first release is read-only and exposes no SQL, shell, filesystem, secret, mutation, resource, or prompt component.
- User identity comes exclusively from the verified token and is never accepted as a tool argument.
- Preserve token creation, listing, one-time plaintext display, least-privilege scope selection, last-used tracking, and revocation.
- Logs never contain bearer tokens, tool arguments, article bodies, briefing bodies, questions, prompts, or generated answers.
- Add behavior tests before production code and record the expected failing result before each implementation step.
- Update published MCP documentation in the same PR; do not leave legacy RPC instructions live.

---

### Task 1: Add FastMCP and adapt News Dashboard tokens

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `backend/news_dashboard/mcp/service.py`
- Create: `backend/news_dashboard/mcp/auth.py`
- Modify: `backend/tests/test_mcp.py`

**Interfaces:**
- Consumes: `service.authenticate_token(token: str, *, database_url: str | None = None) -> dict[str, Any] | None`
- Produces: `NewsDashboardTokenVerifier(TokenVerifier)` with `async verify_token(token: str) -> AccessToken | None`
- Produces: `service.mcp_enabled() -> bool` whose absent-environment default is `True`
- Token claims: `subject=str(user_id)`, `client_id=f"mcp-token:{token_id}"`, `scopes=sorted(stored_scopes)`, and claims containing integer `user_id` and `token_id`

- [ ] **Step 1: Add failing default-flag and verifier tests**

  Extend `backend/tests/test_mcp.py` with tests that delete `MCP_SERVER_ENABLED` and expect `mcp_enabled()` to be true, parametrize explicit false values, and exercise `NewsDashboardTokenVerifier.verify_token()` for active, revoked, malformed, and unknown tokens. The active-token assertion must hand-derive the expected subject, client ID, scopes, and claims from the seeded user/token IDs.

- [ ] **Step 2: Run the focused tests and verify RED**

  Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests/test_mcp.py -q`

  Expected: the absent flag assertion fails because the current default is false, and importing `NewsDashboardTokenVerifier` fails because the adapter does not exist. If PostgreSQL is unavailable, record the infrastructure failure, run any new pure unit test independently where possible, and do not claim the database cases passed.

- [ ] **Step 3: Add the dependency and minimal verifier**

  Add a compatible FastMCP floor to the runtime dependencies and regenerate `uv.lock`. Implement a focused verifier module:

  ```python
  from fastmcp.server.auth import AccessToken, TokenVerifier

  class NewsDashboardTokenVerifier(TokenVerifier):
      async def verify_token(self, token: str) -> AccessToken | None:
          authenticated = service.authenticate_token(token)
          if authenticated is None:
              return None
          token_id = int(authenticated["token_id"])
          user_id = int(authenticated["user_id"])
          scopes = sorted(str(scope) for scope in authenticated["scopes"])
          return AccessToken(
              token=token,
              client_id=f"mcp-token:{token_id}",
              subject=str(user_id),
              scopes=scopes,
              claims={"user_id": user_id, "token_id": token_id},
          )
  ```

  Change `mcp_enabled()` so an absent value is enabled and only the explicit false spellings disable it. Do not weaken prefix, hash, revocation, scope, or last-used behavior.

- [ ] **Step 4: Run focused tests and verify GREEN**

  Run the Task 1 tests and confirm active tokens authenticate while false, unknown, malformed, and revoked cases fail as specified.

- [ ] **Step 5: Run dependency and Python quality checks**

  Run `uv lock --check`, `PATH="$PWD/.venv/bin:$PATH" make lint`, and `PATH="$PWD/.venv/bin:$PATH" make typecheck`. Run the repository-supported dependency vulnerability audit and record any new finding attributable to FastMCP.

- [ ] **Step 6: Commit Task 1**

  Commit only the dependency, verifier, flag behavior, and their tests with message `feat(mcp): add FastMCP token verification`.

### Task 2: Mount the real MCP transport and ship latest-news retrieval

**Files:**
- Create: `backend/news_dashboard/mcp/server.py`
- Modify: `backend/news_dashboard/mcp/router.py`
- Modify: `backend/news_dashboard/mcp/models.py`
- Modify: `backend/news_dashboard/main.py`
- Modify: `backend/tests/test_mcp.py`
- Modify: `backend/tests/test_main_lifespan.py`

**Interfaces:**
- Consumes: `NewsDashboardTokenVerifier`
- Consumes: `search_articles(q="", limit=..., states=..., categories=..., sources=..., include_archived=..., date_range=..., user_id=...)`
- Produces: `mcp = FastMCP("News Dashboard", auth=NewsDashboardTokenVerifier(), mask_error_details=True, strict_input_validation=True)`
- Produces: `mcp_http_app = mcp.http_app(path="/", stateless_http=True, transport="http")`
- Produces tool: `list_latest_news(limit: int = 10, sources: list[str] | None = None, categories: list[str] | None = None, states: list[str] | None = None, date_range: Literal["all", "day", "week", "month"] = "all", include_archived: bool = False) -> dict[str, Any]`

- [ ] **Step 1: Add failing FastMCP client transport tests**

  Replace legacy route-call tests with tests using `fastmcp.Client` against the explicit server or mounted ASGI app. Prove that an authenticated client can initialize, lists `list_latest_news`, and receives only seeded articles visible to the token owner. Add scope-denial, cross-user private-source isolation, invalid filter, maximum-limit, revoked-token, unauthenticated, and explicit-disabled cases. Add an application routing test proving `/mcp` is mounted before the SPA fallback and the legacy endpoints no longer exist.

- [ ] **Step 2: Run the new transport tests and verify RED**

  Expected failures: no FastMCP server/component exists, `/mcp` is not mounted, and legacy endpoints still resolve.

- [ ] **Step 3: Implement token-scoped user extraction**

  Add a private helper in the server module that calls FastMCP's current-access-token dependency, validates the integer `user_id` claim, and raises a sanitized authorization error if it is unavailable. Do not accept `user_id` in the public tool signature.

- [ ] **Step 4: Implement the explicit server and latest-news tool**

  Register only `list_latest_news`, require the `search` scope with FastMCP component authorization, validate inputs with typed parameters, clamp `limit` to 25, bound filter lists, call the existing user-scoped PostgreSQL search service with an empty query, and return compact structured article records without bodies or internal-only fields.

- [ ] **Step 5: Replace the legacy transport**

  Keep only the authenticated token-management routes in `mcp/router.py`. Remove `public_mcp_router`, `McpRpcRequest`, `TOOLS`, `ToolError`, and `call_tool` when no production path uses them. Mount the FastMCP ASGI application at `/mcp` in `main.py` before the SPA mount. When the flag is explicitly disabled, the mount must fail closed without affecting the rest of FastAPI.

- [ ] **Step 6: Run focused transport tests and verify GREEN**

  Confirm initialization, tool discovery, latest-news retrieval, scope filtering, isolation, bounds, revocation, disabled mode, mount ordering, and legacy removal through behavior assertions.

- [ ] **Step 7: Run affected backend tests**

  Run `backend/tests/test_mcp.py`, `backend/tests/test_main_lifespan.py`, `backend/tests/test_spa_static.py`, `backend/tests/test_auth.py`, and `backend/tests/test_operational_read_auth.py` with the required PostgreSQL environment.

- [ ] **Step 8: Commit Task 2**

  Commit the server, mount, first tool, legacy removal, and tests with message `feat(mcp): mount authenticated FastMCP server`.

### Task 3: Harden the endpoint and replace public documentation

**Files:**
- Modify: `backend/news_dashboard/mcp/server.py`
- Modify: `backend/tests/test_mcp.py`
- Modify: `.env.example`
- Modify: `website/docs/configuration/mcp-server.md`
- Modify: `website/docs/api/integrations.md`
- Modify: `website/docs/api/authentication.md`
- Modify: `website/docs/api/index.md`

**Interfaces:**
- Consumes: authenticated FastMCP server and `list_latest_news`
- Produces: per-token rate limiting, response limiting, sanitized error transformation, and metadata-only timing/logging

- [ ] **Step 1: Add failing security behavior tests**

  Add behavior tests showing repeated requests from one non-secret token identifier are rate-limited, oversized tool output is bounded, internal exceptions do not expose tracebacks or database/provider details, and logs contain tool/status/duration metadata but not bearer tokens, arguments, article content, or answers. The tests must exercise middleware behavior rather than grep source configuration.

- [ ] **Step 2: Run security tests and verify RED**

  Expected: the current unconfigured FastMCP server does not provide the required rate, response, and sanitized error behavior.

- [ ] **Step 3: Configure minimal production middleware**

  Add FastMCP middleware in an order that sanitizes errors, rate-limits per verified `client_id`, bounds responses, and records timing/structured metadata. Use conservative explicit constants near server construction; never use raw bearer strings as rate-limit or log identifiers. Keep request/response payload logging disabled.

- [ ] **Step 4: Run security tests and verify GREEN**

  Confirm the rate-limit key is token-specific but non-secret, output is bounded, and errors/logs are sanitized.

- [ ] **Step 5: Replace MCP documentation**

  Update `.env.example` to document the default-enabled flag and explicit shutdown. Rewrite the published configuration and API pages to describe `/mcp`, stateless Streamable HTTP, HTTPS bearer setup, token scopes, `list_latest_news`, the 25-item bound, revocation, Keycloak independence, and the absence of mutation/SQL/shell/filesystem access. Remove every instruction to call `/api/mcp/tools` or `/api/mcp/rpc`; describe later tools as planned rather than available until their issues merge.

- [ ] **Step 6: Verify documentation and focused checks**

  Search for stale legacy endpoint instructions, build the documentation site using its repository script, and run the MCP tests plus `make lint` and `make typecheck`.

- [ ] **Step 7: Commit Task 3**

  Commit security middleware and documentation with message `docs(mcp): document secure FastMCP access`.

### Task 4: Verify, review, and publish issue #1367

**Files:**
- Review all files changed by Tasks 1-3.

**Interfaces:**
- Produces: a green, review-approved PR that closes #1367 and is queued for squash auto-merge.

- [ ] **Step 1: Run mandatory local gates**

  Run `PATH="$PWD/.venv/bin:$PATH" make lint`, `PATH="$PWD/.venv/bin:$PATH" make typecheck`, and `PATH="$PWD/.venv/bin:$PATH" dotenv run -- make test` with `PGOPTIONS='-c max_parallel_workers_per_gather=0'`. Build the published documentation site. Do not push if any required gate fails.

- [ ] **Step 2: Run task and whole-branch reviews**

  Generate review packages for each task range and the full `origin/main..HEAD` range. Resolve every confirmed Critical or Important finding through the sub-agent fix/re-review loop; record minor findings for final triage.

- [ ] **Step 3: Rebase and re-run affected gates if the base changes**

  Fetch and rebase onto `origin/main`. If the rebase changes the base, rerun the affected checks before pushing.

- [ ] **Step 4: Push and create the PR**

  Push `codex/feat-fastmcp-1367` without bypassing hooks. Create a PR whose body begins `Closes #1367`, summarizes the mounted server/auth/tool/docs behavior, lists exact verification evidence, and ends with the repository's required generated-code trailer.

- [ ] **Step 5: Enable auto-merge and monitor required CI**

  Queue squash auto-merge, watch `Lint & typecheck` and `Test & build`, repair branch-caused failures, and confirm the PR merged and #1367 closed before beginning dependent issue work.
