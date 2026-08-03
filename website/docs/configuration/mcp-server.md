---
title: MCP server
sidebar_position: 5
---

# MCP server

News Dashboard exposes a read-only [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro) server at `/mcp`. MCP-aware AI clients connect with stateless Streamable HTTP and see only news visible to the token owner.

The server is enabled by default. To shut down MCP access and block creation of new MCP tokens, set:

```bash
MCP_SERVER_ENABLED=false
```

The explicit values `false`, `0`, `no`, and `off` disable it. Leaving the variable unset keeps it enabled.

## Create a token

A signed-in user can create a token from **Settings → MCP Client Access**, choosing the least set of scopes the client needs. Tokens can also be created through the session-authenticated API:

```bash
curl -X POST https://your-instance/api/users/me/mcp-tokens \
  -H 'Content-Type: application/json' \
  --cookie "nd_session=$SESSION_COOKIE" \
  -d '{"name": "MCP client", "scopes": ["search"]}'
```

The plaintext `ndmcp_` token appears once. News Dashboard stores only its SHA-256 hash and a short display prefix. Each user can hold up to 10 active tokens and can revoke one immediately from Settings or `DELETE /api/users/me/mcp-tokens/{token_id}`.

Available token scopes are `search`, `read`, `ask`, and `briefings`. Omitting `scopes` grants all four; prefer an explicit subset. The current `list_latest_news` tool requires `search`. Tools using the other scopes are planned and are not available yet.

MCP authentication is independent of Keycloak and browser login. The bearer token alone identifies the MCP user; clients never send a user ID as a tool argument.

## Connect a client

Configure the MCP client with:

- URL: `https://your-instance/mcp/`
- Transport: Streamable HTTP
- Header: `Authorization: Bearer <your ndmcp_ token>`

Use HTTPS outside a trusted local development environment. Do not put the token in a URL, command history, or logs. There is no stdio adapter or sidecar service.

## Available tool

| Tool | Scope | Description |
|------|-------|-------------|
| `list_latest_news` | `search` | Lists recent articles visible to the token owner. Supports source, category, state, archive, and date-range filters. |

`list_latest_news` defaults to 10 articles and never returns more than 25. Responses contain compact article metadata and summaries, not article bodies or internal-only fields. Filter lists and the total serialized response size are also bounded. Every response has `articles` and a `truncated` boolean; when the size bound prevents another complete article from fitting, `truncated` is `true` and the returned articles remain valid structured data.

Article retrieval, source search, briefings, and question answering are planned as separate additions. MCP clients should use tool discovery instead of assuming those tools exist.

## Security boundaries

- Tokens are individually scoped and revocable; revoked tokens stop authenticating immediately.
- Rate limits use an opaque, process-local token-instance identity, never the bearer value or a reusable database row ID.
- Logs contain tool name, status, and duration metadata only. They exclude tokens, arguments, article content, prompts, and answers.
- Internal failures return a generic error without tracebacks, database details, or provider details.
- Tools cannot run SQL, shell commands, or file-system operations and cannot read secrets.
- Mutation tools are absent. MCP access cannot change article state, sources, shares, or settings.
- Private-source visibility is enforced for the authenticated token owner.
