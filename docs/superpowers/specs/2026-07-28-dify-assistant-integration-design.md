# Optional Dify Assistant Integration Design

**Status:** Approved

**Deciders:** Product owner and maintainers

**Issue:** [#1292](https://github.com/lihor-hub/news-dashboard/issues/1292)

## Goal

Allow a self-hosted News Dashboard instance to expose a published Dify chat
application as a floating assistant without changing the default experience or
exposing server-side credentials.

## Scope

The first integration slice adds a News Dashboard-owned floating launcher and
responsive panel containing Dify's published WebApp iframe. It includes runtime
configuration, React lifecycle isolation, Docker Compose and Helm wiring,
tests, and operator documentation. It does not synchronize private articles
into Dify, put a Dify API key in the browser, grant the Dify agent write access
to News Dashboard, or send News Dashboard account or page context to Dify.

## Architecture

The backend converts environment variables into a small public configuration
object returned by `GET /api/config`. The object is enabled only when the
explicit feature flag, an HTTPS-or-local-development base URL, and an embed
token are all valid. At the browser boundary, configuration fails closed if
the Dify URL has the same origin as News Dashboard; cross-origin iframe
isolation is part of the privacy boundary.

The authenticated application shell loads a focused React component. When the
configuration is enabled, News Dashboard renders a native floating button. The
button opens a host-owned panel containing Dify's documented
`{baseUrl}/chatbot/{appToken}` WebApp iframe. The iframe exists only while the
panel is open. Closing the panel, unmounting the shell, logging out, or changing
authenticated accounts destroys the iframe and its complete runtime. Reopening
or remounting creates a new iframe, so a transient load failure is retryable.

No Dify script executes in the News Dashboard parent document. The integration
sets no Dify window globals, installs no Dify window listeners, and adds no
Dify-owned parent styles or DOM artifacts.

News Dashboard sends no username, email address, News Dashboard user ID,
article/page context, Dify input variables, system variables, or user variables
to the public WebApp. The iframe URL has no query string or fragment. Dify
creates and manages its own WebApp end-user and conversation identity inside
the frame; that identity is separate from News Dashboard authentication and is
not a mapping to a News Dashboard account.

## Configuration

| Variable              | Default          | Purpose                                                 |
| --------------------- | ---------------- | ------------------------------------------------------- |
| `DIFY_CHAT_ENABLED`   | `false`          | Explicit instance-wide opt-in                           |
| `DIFY_CHAT_BASE_URL`  | empty            | Browser-reachable, separate origin of the Dify instance |
| `DIFY_CHAT_APP_TOKEN` | empty            | Public token from Dify **Publish → Embed**              |
| `DIFY_CHAT_TITLE`     | `News Assistant` | Accessible launcher and panel name                      |

`DIFY_CHAT_BASE_URL` is normalized by removing a trailing slash. Production
URLs must use HTTPS. HTTP is accepted only for `localhost`, `127.0.0.1`, and
`[::1]` development addresses. The URL origin must differ from the News
Dashboard origin; mounting Dify at a path on the same origin is rejected.
Tokens and titles are length-limited by Unicode code point, and control
characters are rejected. Invalid or partial configuration produces a disabled
public object rather than a partially usable integration.

The embed token is intentionally browser-visible and is not a Dify service API
key. Operators must never place a Dify API key in `DIFY_CHAT_APP_TOKEN`.

## User experience

When enabled, News Dashboard's floating assistant button appears in the
lower-right corner on authenticated pages. It is a keyboard-accessible native
button with a visible focus indicator and a target of at least 44 by 44 CSS
pixels. The named panel and its close button are keyboard accessible, and the
Dify iframe has an accessible title.

On mobile, the launcher and panel clear News Dashboard's fixed navigation and
safe-area inset; the panel uses the remaining viewport. On desktop, the panel
uses a bounded chat-sized layout. Dify owns only the conversation interface
inside the iframe.

When disabled or invalid, News Dashboard renders no launcher or iframe and
makes no Dify-origin request. If Dify is offline or blocked by browser policy,
News Dashboard continues normally; closing and reopening the panel creates a
fresh iframe request.

## Security and deployment

Dify WebApps are public by default. Operators must publish the intended app,
enable embedding in Dify, deploy Dify on an origin separate from News
Dashboard, and expose both applications over HTTPS in production. Self-hosted
Dify deployments must set `ALLOW_EMBED=true`.

If a reverse proxy adds a Content Security Policy to News Dashboard, its
`frame-src` must allow the exact Dify origin. This iframe integration does not
require that origin in the News Dashboard parent document's `script-src` or
`connect-src`, and iframe navigation does not require Dify CORS to allow the
News Dashboard origin. Dify's own proxy must still serve the WebApp and its
streaming responses correctly.

Private News Dashboard retrieval should later use the existing per-user,
read-only MCP token boundary or a backend-mediated Dify API integration. Dify's
separate WebApp identity cannot substitute for News Dashboard authentication or
authorize private-data access.

## Verification

Backend tests cover disabled, partial, enabled, normalized, length-limited, and
unsafe URL configuration. A frontend parity test proves the browser uses
Python's Unicode code-point length metric, and a browser-boundary test rejects a
same-origin frame. Component tests prove that disabled or malformed
configuration has no launcher, enabled configuration has no iframe until
opened, the exact context-free WebApp URL is used, native controls have
accessible names and keyboard semantics including Escape dismissal, and
close/unmount remove the iframe. An AppShell boundary test proves no user prop
is passed. Tests also prove a failed iframe can be retried by reopening.
Deployment tests cover Docker Compose and Helm configuration. Repository lint,
format, typecheck, tests, docs build, and frontend build remain required before
delivery.
