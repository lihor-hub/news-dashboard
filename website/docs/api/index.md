---
title: API reference
sidebar_position: 1
---

# API reference

News Dashboard exposes a JSON HTTP API served by the same FastAPI backend that
serves the built React frontend. Everything the web UI does, it does through
this API — there is no private back channel.

This section documents the shape of the API: how requests are authenticated,
how responses and errors are structured, and what each area of the surface
covers. It is a hand-written companion to the generated schema, not a
replacement for it.

## The generated schema is the source of truth

The backend publishes an OpenAPI document derived directly from the route
handlers. When this page and the schema disagree, the schema is right.

| Endpoint | What it serves |
|----------|----------------|
| `/docs` | Interactive Swagger UI for the running instance. |
| `/openapi.json` | The raw OpenAPI document. |
| `/api/version` | The running application version. |

The OpenAPI `info.version` and `/api/version` are both read from the `VERSION`
file at startup, so the documented version always matches the deployed build.

## Base URL

All paths in this section are relative to your instance root. For a
self-hosted deployment at `https://news.example.com`, the article list is
`https://news.example.com/api/articles`.

Routes are grouped by the router they mount on, which determines their auth
behavior:

| Prefix | Router | Access |
|--------|--------|--------|
| `/api/*` | authenticated `api` router | Requires a valid session. |
| `/api/admin/*` | `admin` router | Requires a session belonging to an admin user. |
| `/api/auth/*`, `/auth/*` | public router | Login, registration, and SSO callbacks. |
| `/mcp/*` | mounted FastMCP server | Bearer-token authenticated, stateless Streamable HTTP. |
| `/reader/api/0/*`, `/accounts/ClientLogin` | public GReader router | Google Reader-compatible sync. |
| `/api/health`, `/api/live`, `/api/ready`, `/metrics` | system router | Unauthenticated probes. |

## Response conventions

### Collections

List endpoints return an envelope rather than a bare array, so clients can
page without a second count query:

```json
{
  "items": [],
  "limit": 100,
  "offset": 0,
  "has_more": false
}
```

`has_more` is computed by over-fetching one row past `limit`, so it is exact
and costs no extra query. Paginate by advancing `offset` until `has_more` is
`false`.

Both `limit` and `offset` are validated server-side. `limit` is clamped per
endpoint — `/api/articles` accepts `1..500` (default `100`), `/api/search`
accepts `1..200` (default `50`). Out-of-range values are rejected with `422`
rather than silently clamped.

### Errors

Errors use FastAPI's standard envelope:

```json
{ "detail": "Not Found" }
```

For request-validation failures (`422`), `detail` is an array of per-field
objects identifying the offending parameter and the rule it broke.

| Status | Meaning |
|--------|---------|
| `400` | The request was understood but rejected by a domain rule. |
| `401` | No valid session, token, or credential was presented. |
| `403` | Authenticated, but not permitted — see below. |
| `404` | The resource does not exist, or is not visible to you. |
| `422` | Request validation failed (bad query parameter, malformed body). |
| `429` | A rate limit or generation quota was exceeded. |
| `5xx` | Server-side failure. |

`404` is used deliberately in place of `403` for resources that exist but
belong to another user, so the API does not leak their existence.

### Three distinct sources of `403`

A `403` is not always an authorization failure. Check `detail` to tell them
apart:

- `"Guest accounts cannot modify data"` — the session belongs to a guest
  account. Guests have full read access and are blocked from every mutating
  method by middleware.
- `"Cross-origin request rejected"` — a cookie-authenticated mutation arrived
  with an `Origin` header outside the allowed set. See
  [Authentication](authentication.md#csrf-protection).
- Anything else — the endpoint requires admin rights, or an opt-in feature
  such as the MCP server is disabled.

## Sections

| Page | Covers |
|------|--------|
| [Authentication](authentication.md) | Sessions, SSO, OTP, guests, CSRF, and the token types. |
| [Articles and search](articles-and-search.md) | The article lifecycle, triage, search, highlights, and tags. |
| [Sources and ingestion](sources-and-ingestion.md) | Feed management, OPML, ingestion runs, and the scheduler. |
| [Learning and briefings](learning-and-briefings.md) | Briefings, lessons, quizzes, recaps, and podcast generation. |
| [Integrations](integrations.md) | MCP tools, Google Reader sync, sharing, and podcast feeds. |
| [Operations](operations.md) | Health probes, metrics, statistics, and admin endpoints. |

## Stability

The API is versioned with the application, not independently. It is primarily
a first-party interface for the official web, Android, and desktop clients,
and it changes alongside them.

Two surfaces are explicitly built for third-party consumption and are the
safest to integrate against:

- The [MCP tool set](integrations.md#mcp-server) — read-only and deliberately
  narrow.
- The [Google Reader API](integrations.md#google-reader-sync) — implements an
  external, already-stable contract.
