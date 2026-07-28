# Optional Dify Assistant Integration Design

**Status:** Approved

**Deciders:** Product owner and maintainers

**Issue:** [#1292](https://github.com/lihor-hub/news-dashboard/issues/1292)

## Goal

Allow a self-hosted News Dashboard instance to expose a published Dify chat
application as a floating assistant without changing the default experience or
exposing server-side credentials.

## Scope

The first integration slice embeds Dify's published WebApp widget. It includes
runtime configuration, React lifecycle isolation, Docker Compose and Helm
wiring, tests, and operator documentation. It does not synchronize private
articles into Dify, put a Dify API key in the browser, or grant the Dify agent
write access to News Dashboard.

## Architecture

The backend converts environment variables into a small public configuration
object returned by `GET /api/config`. The object is enabled only when the
explicit feature flag, an HTTPS-or-local-development base URL, and an embed
token are all valid.

The authenticated application shell loads a focused React component. When the
configuration is enabled, the component sets Dify's documented
`window.difyChatbotConfig`, loads `{baseUrl}/embed.min.js`, and removes the
script, configuration, and Dify DOM artifacts when unmounted. A load failure is
contained inside the component and never blocks News Dashboard navigation.

Only the authenticated user's display name and stable News Dashboard user ID
are supplied as display/tracing context. Dify does not authenticate those
browser-provided values, so they must never authorize private-data access.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DIFY_CHAT_ENABLED` | `false` | Explicit instance-wide opt-in |
| `DIFY_CHAT_BASE_URL` | empty | Browser-reachable origin of the self-hosted Dify instance |
| `DIFY_CHAT_APP_TOKEN` | empty | Public token from Dify **Publish → Embed** |
| `DIFY_CHAT_TITLE` | `News Assistant` | Accessible display name |

`DIFY_CHAT_BASE_URL` is normalized by removing a trailing slash. Production
URLs must use HTTPS. HTTP is accepted only for `localhost`, `127.0.0.1`, and
`[::1]` development addresses. Tokens and titles are length-limited, and
control characters are rejected. Invalid or partial configuration produces a
disabled public object rather than a partially usable integration.

The embed token is intentionally browser-visible and is not a Dify service API
key. Operators must never place a Dify API key in `DIFY_CHAT_APP_TOKEN`.

## User experience

When enabled, Dify's floating button appears in the lower-right corner on
authenticated pages. Its bottom offset clears News Dashboard's mobile
navigation and safe-area inset. Dify owns the expanded overlay and its
conversation interface.

When disabled, invalid, offline, or blocked by browser policy, News Dashboard
continues normally. No Dify script is requested when the integration is
disabled.

## Security and deployment

Dify WebApps are public by default. Operators must publish the intended app,
enable embedding in Dify, expose both applications over HTTPS, restrict Dify
CORS to the News Dashboard origin, and configure any reverse-proxy Content
Security Policy to allow the Dify origin for scripts, frames, connections,
images, and media.

Private News Dashboard retrieval should later use the existing per-user,
read-only MCP token boundary or a backend-mediated Dify API integration.
Browser-supplied Dify variables are context only and cannot substitute for
News Dashboard authentication.

## Verification

Backend tests cover disabled, partial, enabled, normalized, and unsafe URL
configuration. Frontend tests prove that the script is absent when disabled,
loads with expected context when enabled, does not duplicate across rerenders,
and cleans up after unmount. Deployment tests cover Docker Compose and Helm
configuration. Repository lint, typecheck, tests, and frontend build remain
required before delivery.
