---
title: MCP server (opt-in AI client access)
sidebar_position: 5
---

# MCP server (opt-in AI client access)

News Dashboard can expose a minimal, read-only [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro)-style tool set so an external AI client (Claude Desktop, Codex, or another MCP-aware agent) can search and read the articles visible to one user. It is disabled by default and does not give clients raw database, SQL, shell, or file-system access.

## Enabling the server

Set on the backend:

```bash
MCP_SERVER_ENABLED=1
```

When unset (or falsy), all `/api/mcp/*` endpoints and the token-management endpoints under `/api/users/me/mcp-tokens` return `403 Forbidden`.

## Creating a token

Once enabled, a signed-in user can create a token from **Settings → MCP Client Access**, or via:

```bash
curl -X POST https://your-instance/api/users/me/mcp-tokens \
  -H 'Content-Type: application/json' \
  --cookie "nd_session=$SESSION_COOKIE" \
  -d '{"name": "Claude Desktop"}'
```

The response includes the plaintext token (prefixed `ndmcp_`) exactly once — only its hash is stored (SHA-256) alongside a short prefix, creation time, and last-used time. Losing the token means creating a new one; tokens can be revoked at any time from the same Settings section, which sets `revoked_at` and immediately invalidates it. Each user may hold up to 10 active tokens.

## Calling tools

Tool calls authenticate with `Authorization: Bearer <token>`, not the session cookie:

```bash
curl https://your-instance/api/mcp/tools \
  -H "Authorization: Bearer $MCP_TOKEN"

curl -X POST https://your-instance/api/mcp/rpc \
  -H "Authorization: Bearer $MCP_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"tool": "search_articles", "arguments": {"q": "rust", "limit": 10}}'
```

Available tools, all read-only and scoped to the token owner's visible articles:

| Tool | Scope | Description |
|------|-------|--------------|
| `search_articles` | `search` | Search articles visible to the token owner. `limit` is capped at 25. |
| `get_article` | `read` | Fetch a single visible article by `article_id`. Returns 404 for articles the owner cannot see. |
| `list_briefings` | `briefings` | List the token owner's recent briefing metadata (no article bodies). |
| `ask` | `ask` | Ask a question answered via retrieval over the token owner's corpus. |

Every new token is issued all four scopes by default. Requests are bounded: queries are capped at 2,000 characters and result lists at 25 items, matching the limits used by the browser-facing `/api/ask` and search endpoints.

## Security boundaries

- No tool exposes raw SQL, environment variables, secrets, or server file-system/shell access.
- Article visibility follows the same per-user rules as the authenticated web API — a token can never see another user's private sources or state.
- Mutation tools (marking articles read, creating shares, etc.) are intentionally absent; only after a human-approval workflow exists for agent-initiated actions will mutating tools be considered.
- Tokens are bearer secrets: treat them like passwords, transmit only over HTTPS, and revoke immediately if a client is decommissioned or compromised.

## Connecting an MCP client

Most MCP clients expect a local process or a documented HTTP tool endpoint. Point the client at `POST /api/mcp/rpc` (and `GET /api/mcp/tools` for discovery) on your instance, with the bearer token configured as a static header. Consult your specific client's documentation for how it wires up custom HTTP tool servers — News Dashboard does not (yet) ship a bundled stdio adapter.
