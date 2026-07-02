---
title: Authentication (Keycloak)
sidebar_position: 2
---

# Keycloak authentication

`news-dashboard` can use the existing minipc Keycloak instance as the public login provider while keeping the app's local `users` table as the per-user authorization/data boundary.

## Runtime flow

1. The frontend calls `GET /api/auth/config`.
2. When `KEYCLOAK_AUTH_ENABLED=1`, the login screen shows the new dashboard-style `Sign in with Keycloak` button.
3. `/auth/login` must reach the FastAPI backend and returns a `307` redirect to Keycloak using Authorization Code flow.
4. `/auth/callback` exchanges the code, reads Keycloak `userinfo`, creates or reuses a local app user, and sets the existing signed `nd_session` cookie.
5. All existing authenticated API routes continue to use `require_auth`, so article state, source subscriptions, briefings, and admin routes remain scoped by local `user_id`.

Keycloak-created users receive an unusable random local password because Keycloak owns authentication. The comma-separated `KEYCLOAK_ADMIN_USERNAMES` env var controls which Keycloak usernames become app admins on first login. If unset, no Keycloak user is granted admin on first login.

### PWA/service-worker routing

The dashboard is a PWA, so the generated Workbox service worker can answer browser navigations with the SPA `index.html` fallback. That is correct for client routes such as `/today`, but it must never intercept backend or identity-provider routes.

`vite.config.ts` therefore denies fallback handling for:

```ts
navigateFallbackDenylist: [/^\/api\//, /^\/auth\//, /^\/keycloak\//];
```

Without this denylist, an already-installed PWA or a browser with an old service worker can open `/auth/login` and see the dashboard login shell again instead of following the backend `307` to Keycloak.

## Backend environment

Required when Keycloak auth is enabled:

```bash
KEYCLOAK_AUTH_ENABLED=1
NEWS_DASHBOARD_BASE_URL=https://news.lihor.ro
KEYCLOAK_SERVER_URL=https://news.lihor.ro/keycloak
KEYCLOAK_INTERNAL_SERVER_URL=https://news.lihor.ro/keycloak
KEYCLOAK_REALM=news-dashboard
KEYCLOAK_CLIENT_ID=news-dashboard
KEYCLOAK_ADMIN_USERNAMES=alice,bob   # comma-separated; omit to grant no admins via Keycloak
SESSION_SECRET=<long random string>
```

`KEYCLOAK_SERVER_URL` is the browser-visible issuer base. `KEYCLOAK_INTERNAL_SERVER_URL` may point to an internal service if one exists; for the minipc same-host reverse proxy it intentionally matches the public URL.

## Caddy

The minipc Caddy config exposes Keycloak under the same hostname:

```caddy
news.lihor.ro {
	handle /keycloak* {
		reverse_proxy 127.0.0.1:8081
	}

	reverse_proxy 127.0.0.1:30088
}
```

This avoids a separate DNS record and keeps redirect URIs under `https://news.lihor.ro`.

Do **not** enable a separate `keycloak.lihor.ro` Caddy site unless the DNS record exists first. If that site is imported while the subdomain is `NXDOMAIN`, Caddy will keep retrying Let's Encrypt issuance and logging ACME DNS failures. For this deployment, the durable public Keycloak base is:

```text
https://news.lihor.ro/keycloak
```

## Helm

The chart exposes the Keycloak settings under `app.auth` in `helm/news-dashboard/values.yaml`. When `app.auth.enabled=true`, Helm renders an auth Secret containing `SESSION_SECRET` and injects the Keycloak env vars into the app deployment.

For local deployment, override `app.auth.sessionSecret` with a generated value:

```bash
helm upgrade --install news-dashboard ./helm/news-dashboard \
  --set app.auth.sessionSecret="$(python -c 'import secrets; print(secrets.token_hex(32))')"
```

## Keycloak realm/client

Recommended realm/client values:

- Realm: `news-dashboard`
- Client ID: `news-dashboard`
- Client type: public OpenID Connect client
- Valid redirect URI: `https://news.lihor.ro/auth/callback`
- Valid post-logout redirect URI: `https://news.lihor.ro`
- Web origin: `https://news.lihor.ro`

## Google sign-in

Enable Google through Keycloak, not as a second auth implementation inside the
dashboard. The app should keep talking only to Keycloak; Keycloak brokers the
Google identity, then `/auth/callback` creates or reuses the same local
dashboard user record as any other Keycloak login.

### Google Cloud

1. Open Google Cloud Console and create or select the project that should own
   the OAuth client.
2. Configure the OAuth consent screen for the app.
3. Create an OAuth 2.0 Client ID with application type `Web application`.
4. Add this authorized redirect URI:

   ```text
   https://news.lihor.ro/keycloak/realms/news-dashboard/broker/google/endpoint
   ```

5. Copy the generated client ID and client secret.

### Keycloak

1. Open the `news-dashboard` realm.
2. Go to **Identity providers** and add **Google**.
3. Use alias `google` so the broker callback path stays:

   ```text
   /realms/news-dashboard/broker/google/endpoint
   ```

4. Paste the Google client ID and client secret.
5. Keep the default scopes unless the dashboard needs more profile data. The
   app currently needs only standard OIDC identity fields such as username,
   email, and display name.
6. Save the provider, then open a private browser window and visit:

   ```text
   https://news.lihor.ro/auth/login
   ```

   The Keycloak login page should show the Google provider as an alternate
   sign-in action. After Google redirects back to Keycloak, Keycloak redirects
   to `https://news.lihor.ro/auth/callback`, and the dashboard session cookie is
   issued by the app.

No frontend or backend environment variable is required specifically for Google
as long as `KEYCLOAK_AUTH_ENABLED=1` and the existing Keycloak settings point at
the `news-dashboard` realm.

## Login theme

The custom Keycloak theme lives in:

```text
deploy/keycloak-theme/news-dashboard/login/
```

It extends `keycloak.v2` and overrides only CSS. The CSS mirrors the Radar
Dashboard app shell: `RD` mark, compact centered card, warm OKLCH
background/card colors, rounded inputs, app-style primary actions, social
provider buttons, and dark-mode support.

Mount it into the Keycloak container at:

```text
/opt/keycloak/themes/news-dashboard
```

Then set the realm login theme to `news-dashboard`.

For local development/self-hosting, disable Keycloak theme caching while iterating:

```yaml
KC_SPI_THEME_CACHE_THEMES: 'false'
KC_SPI_THEME_CACHE_TEMPLATES: 'false'
KC_SPI_THEME_STATIC_MAX_AGE: '-1'
```
