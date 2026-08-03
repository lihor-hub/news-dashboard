---
title: Authentication
sidebar_position: 2
---

# Authentication

News Dashboard has one primary credential — a signed session cookie — plus two
narrow token types for integrations that cannot hold cookies.

## Session cookie

Successful login sets an `nd_session` cookie containing a signed token that
carries the user ID and admin flag. The token is signed, not encrypted: it is
tamper-evident, and the server re-reads the user record on every request rather
than trusting the claims inside it.

Sessions last `SESSION_DAYS` days (default `30`). Expiry is enforced against
the token's own age at verification time, so shortening `SESSION_DAYS`
immediately invalidates older cookies.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/auth/config` | GET | Which login methods this instance offers. |
| `/api/auth/metadata` | GET | Identity-provider metadata for the client. |
| `/api/auth/login` | POST | Username/password login; sets the session cookie. |
| `/api/auth/logout` | GET | Clears the session cookie. |
| `/api/auth/me` | GET | The current user. Requires a session. |

Call `/api/auth/config` before rendering a login screen — it reports whether
this instance uses local passwords, SSO, or both, so clients do not hardcode
an assumption.

## Email one-time codes

Passwordless login by emailed code, in two steps:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/auth/otp/request` | POST | Sends a one-time code to an email address. |
| `/api/auth/otp/login` | POST | Exchanges email + code for a session cookie. |

Both steps are throttled per email address and answer `429` with
`"Too many code requests; try again later"` or `"Too many code attempts; try
again later"` when tripped. A successful login clears the failure counter.

An invalid or expired code returns `401 "Invalid or expired code"`. The
request step does not reveal whether an address is registered.

## Keycloak SSO

When `KEYCLOAK_AUTH_ENABLED` is set, browser-redirect SSO routes are mounted
alongside the local flows:

| Route | Purpose |
|-------|---------|
| `/auth/login` | Redirect to the identity provider. |
| `/auth/register` | Redirect to provider-side registration. |
| `/auth/callback` | OIDC callback; establishes the session. |
| `/auth/logout` | Provider-side logout. |

Admin rights can be granted by provider username via
`KEYCLOAK_ADMIN_USERNAMES`. Configuration is covered in
[Configuration → Authentication](../configuration/authentication.md).

## Guest accounts

A guest session authenticates normally and can read everything, but middleware
rejects every mutating request before it reaches a handler:

```json
{ "detail": "Guest accounts cannot modify data" }
```

This is enforced centrally rather than per-endpoint, so it applies uniformly
to routes added later. Clients backed by a guest session should render the UI
read-only rather than relying on failed writes.

## CSRF protection

Because the session lives in a cookie, cookie-authenticated **mutations** pass
an origin check. If a request carries the session cookie and presents an
`Origin` outside the allowed set, it is rejected:

```json
{ "detail": "Cross-origin request rejected" }
```

The allowed set derives from the instance's configured CORS origins. Two
practical consequences:

- Browser clients on a different domain need that domain in the CORS
  configuration, not just permissive CORS headers.
- Server-to-server integrations should use a **token** instead of a cookie.
  Token-authenticated requests do not carry the session cookie and so are not
  subject to the origin guard.

## Integration tokens

Two token families exist for clients that cannot hold a browser cookie. Both
are per-user, individually revocable, and scoped to a single integration.

### MCP tokens

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/users/me/mcp-tokens` | GET | List your MCP tokens. |
| `/api/users/me/mcp-tokens` | POST | Mint a token. |
| `/api/users/me/mcp-tokens/{token_id}` | DELETE | Revoke a token. |

These authenticate the read-only [MCP tool set](integrations.md#mcp-server).
MCP bearer authentication is independent of Keycloak and browser sessions.
The server is enabled by default; setting `MCP_SERVER_ENABLED` to `false`, `0`,
`no`, or `off` disables the MCP transport and blocks creation of new tokens.
Existing tokens remain stored so access can resume if the feature is enabled
again, and revocation invalidates a token immediately.

### Google Reader tokens

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/users/me/greader-tokens` | GET | List sync tokens. |
| `/api/users/me/greader-tokens` | POST | Mint a token. |
| `/api/users/me/greader-tokens/{token_id}` | DELETE | Revoke a token. |

These back the [Google Reader-compatible sync
API](integrations.md#google-reader-sync) used by third-party feed readers.

### Podcast feed tokens

Podcast feeds are consumed by player apps that cannot log in, so the feed URL
carries its own capability token:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/briefings/podcast-feed-token` | GET | Fetch the current feed token. |
| `/api/briefings/podcast-feed-token/regenerate` | POST | Rotate it. |

The token grants read access to that user's generated podcast audio and
nothing else. Regenerating invalidates the previous URL — that is the only way
to revoke a feed that has been shared.

## Account lifecycle

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/users/me/export` | GET | Export your data. |
| `/api/users/me/import` | POST | Import a previously exported archive. |
| `/api/users/me` | DELETE | Delete your account and associated data. |

Import accepts JSON archives up to 20 MiB. Administrative user management is
separate and documented under [Operations](operations.md#user-administration).
