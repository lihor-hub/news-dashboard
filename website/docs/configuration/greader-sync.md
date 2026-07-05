---
title: RSS client sync (Google Reader API)
sidebar_position: 6
---

# RSS client sync (Google Reader API)

News Dashboard exposes a v1 [Google Reader-compatible](https://en.wikipedia.org/wiki/Google_Reader) sync API so third-party RSS readers (NetNewsWire, Reeder, Unread, FeedMe, ...) can subscribe with their favorite native client while News Dashboard stays the backend. It is read-only for subscriptions plus read/star sync — clients cannot add, edit, or delete subscriptions through this API.

## Creating a token

Any signed-in user can create a sync token from **Settings → RSS Client Sync (Google Reader API)**, or via:

```bash
curl -X POST https://your-instance/api/users/me/greader-tokens \
  -H 'Content-Type: application/json' \
  --cookie "nd_session=$SESSION_COOKIE" \
  -d '{"name": "NetNewsWire"}'
```

The response includes the plaintext token (prefixed `ndgr_`) exactly once — only its hash is stored, alongside a short prefix, creation time, and last-used time. Tokens can be revoked at any time from the same Settings section; revoking sets `revoked_at` and immediately invalidates the token. Each user may hold up to 10 active tokens.

## Connecting a client

In your RSS reader's "Google Reader" or "FreshRSS/Miniflux-compatible" account setup:

- **Server URL**: `https://your-instance/api/greader`
- **Username / Email**: your News Dashboard username (any non-empty value is accepted; only the token is checked)
- **Password**: the token you created above

The client performs `POST /api/greader/accounts/ClientLogin` with your username and the token as the password, receives an `Auth=` value (the same token), and sends it back as `Authorization: GoogleLogin auth=<token>` (or a plain bearer token) on every subsequent request.

## Endpoints (v1)

All endpoints below live under `/api/greader/reader/api/0/` and require the `Authorization` header described above:

| Endpoint | Method | Purpose |
|---|---|---|
| `token` | GET | Returns a POST token for client compatibility. |
| `user-info` | GET | Returns the authenticated user's id/username/email. |
| `subscription/list` | GET | Lists visible sources as subscriptions, with `category` mapped to a folder label. |
| `stream/contents/user/-/state/com.google/reading-list` | GET | All articles visible to the user. |
| `stream/contents/user/-/state/com.google/starred` | GET | Starred articles only. |
| `stream/contents/feed/<slug>` | GET | Articles from a single source. |
| `stream/items/ids` | GET | Item id listing for a stream, for clients that page ids separately from content. |
| `stream/items/contents` | POST | Full item bodies for a set of `i=` item ids. |
| `edit-tag` | POST | Add/remove `user/-/state/com.google/read` or `.../starred` tags — delegates to the same article state machine as the web UI. |

Streams and item bodies page via a `c` continuation token returned alongside `items`/`itemRefs` when more results are available; pass it back as `c` on the next request.

## Visibility and security

- Only sources the token owner can see (global subscribed sources plus their own private sources) are ever returned — the same rule the browser API enforces.
- State changes made via `edit-tag` (read/starred) are immediately visible in the web UI, and vice versa, since both paths write through `user_article_state`.
- Tokens are bearer secrets: treat them like passwords, transmit only over HTTPS, and revoke immediately if a client is decommissioned or compromised.
