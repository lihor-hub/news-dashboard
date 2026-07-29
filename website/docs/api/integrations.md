---
title: Integrations
sidebar_position: 6
---

# Integrations

Three surfaces are built for consumption outside the official clients: the MCP
tool set, the Google Reader-compatible sync API, and sharing. All are opt-in
or user-initiated.

## MCP server

An intentionally narrow, **read-only** tool set that lets an MCP-aware AI
client (Claude Desktop, Codex, or similar) search and read the articles
visible to one user. It exposes no SQL, shell, or file-system access.

Disabled by default. Set `MCP_SERVER_ENABLED=1` on the backend to enable it —
otherwise every `/api/mcp/*` route and the token-management routes return
`403 Forbidden`.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/mcp/tools` | GET | Discover available tools and their schemas. |
| `/api/mcp/rpc` | POST | Invoke a tool. |

Authenticate with an MCP token as a bearer credential. Tokens are minted and
revoked under `/api/users/me/mcp-tokens` — see
[Authentication](authentication.md#mcp-tokens).

### Available tools

| Tool | Scope | Does |
|------|-------|------|
| `search_articles` | `search` | Search articles visible to the token owner. |
| `get_article` | `read` | Fetch a single visible article by id. |
| `list_briefings` | `briefings` | List the owner's recent briefings (metadata only). |
| `ask` | `ask` | Answer a question via retrieval over the owner's corpus. |

Each tool requires its own **scope**, and a token only carries the scopes it
was minted with. A token issued for `search` alone cannot call `ask`, so you
can hand an agent search access without granting it generation budget.

`list_briefings` returns metadata only — briefing bodies are not exposed
through MCP.

Result limits are clamped server-side, so a client asking for an unbounded
page gets a bounded one rather than an error.

Setup instructions for specific clients live in
[Configuration → MCP server](../configuration/mcp-server.md).

## Google Reader sync

A Google Reader-compatible API, so existing feed readers (Reeder, FeedMe,
NewsFlash, and others) can sync against News Dashboard without bespoke
support.

Authenticate with a GReader token from
`/api/users/me/greader-tokens`. Most readers expect the ClientLogin flow:

| Route | Method | Purpose |
|-------|--------|---------|
| `/accounts/ClientLogin` | POST | Exchange credentials for a session. |
| `/reader/api/0/token` | GET | Fetch the write token. |
| `/reader/api/0/user-info` | GET | Account metadata. |
| `/reader/api/0/subscription/list` | GET | Subscribed feeds. |
| `/reader/api/0/stream/contents/{stream_id}` | GET | Items in a stream. |
| `/reader/api/0/stream/items/ids` | GET | Item IDs in a stream. |
| `/reader/api/0/stream/items/contents` | POST | Fetch items by ID. |
| `/reader/api/0/edit-tag` | POST | Add or remove tags — read/starred state. |

`edit-tag` is how third-party readers mark items read or starred; those changes
map onto the same triage state used by the web UI, so the two stay in sync.

Because this implements an external contract that predates this project, it is
the most stable surface here. Configuration details are in
[Configuration → GReader sync](../configuration/greader-sync.md).

## Sharing

Sharing sends an article to another user on the same instance, with a threaded
conversation attached. It is instance-internal — not public link sharing.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/users` | GET | Users you can share with. |
| `/api/articles/{article_id}/share` | POST | Share an article. |
| `/api/shares` | GET | Shares you received. |
| `/api/shares/sent` | GET | Shares you sent. |
| `/api/shares/unread_count` | GET | Badge count. |
| `/api/shares/{share_id}` | GET | One share. |
| `/api/shares/{share_id}/read` | POST | Mark as read. |
| `/api/shares/{share_id}/revoke` | POST | Revoke a share you sent. |

### Shared article content

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/shares/{share_id}/article` | GET | The shared article. |
| `/api/shares/{share_id}/article/body` | POST | Extract its body. |

The recipient reads the article through the **share**, not through
`/api/articles/{id}`. The share is the grant, so revoking it withdraws access
rather than leaving a dangling readable article.

### Discussion

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/shares/{share_id}/messages` | GET / POST | Conversation on a share. |
| `/api/shares/{share_id}/annotations` | GET / POST | Inline annotations. |

Messages are share-level discussion; annotations anchor to positions in the
article body.

## Push notifications

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/notifications/subscribe` | POST | Register a Web Push subscription. |
| `/api/notifications/subscribe` | DELETE | Unregister it. |
| `/api/settings/notifications` | GET / PUT | Notification preferences. |

Notification settings include briefing delivery time, timezone, whether push is
enabled, weekly recap day, and whether to include reading-list items (capped at
20 per briefing). Briefing time is validated as `HH:MM` in 24-hour form, and
recap day must be one of `mon`–`sun`.

## Analytics preferences

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/settings/analytics` | GET / PUT | Opt in or out of analytics. |
| `/api/events` | POST | Record a client-side event. |

Event recording honors the analytics preference — opting out stops collection
rather than merely hiding it. See [PRIVACY.md](https://github.com/lihor-hub/news-dashboard/blob/main/PRIVACY.md)
for what is and is not collected.
