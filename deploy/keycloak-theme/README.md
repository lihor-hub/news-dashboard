# Keycloak theme: auth-state coverage

The `news-dashboard` theme inherits `keycloak.v2` and overrides only
`login/resources/css/login.css` (no custom FreeMarker templates). CSS-only
inheritance is enough to brand every page keycloak.v2 already renders,
because the selectors below (`#kc-page-title`, `.pf-v5-c-alert`,
`#kc-social-providers`, form controls, buttons) are shared across all of
them.

## State matrix

| State | Keycloak page/template | Coverage |
| --- | --- | --- |
| Normal login | `login.ftl` | Styled (form controls, primary button, brand header) |
| Invalid credentials | `login.ftl` + `#input-error` | Styled (`.pf-v5-c-alert`, `#input-error`) |
| Locked account | `login.ftl` (temporarily disabled message) | Styled via the same alert/helper-text selectors |
| Required action / update password | `login-update-password.ftl` | Styled (shared form control + button selectors) |
| TOTP/OTP MFA challenge | `login-otp.ftl` | Styled (shared form control + button selectors) |
| Verify email | `login-verify-email.ftl` | Styled (shared alert/info selectors) |
| Registration | `register.ftl` | Styled (shared form control + button selectors) |
| Reset credentials | `login-reset-password.ftl` | Styled (shared form control + button selectors) |
| Expired session / action timeout | `login-page-expired.ftl` | Styled (shared alert/link selectors) |
| Generic provider error | `error.ftl` | Styled (shared alert selectors); browser-side OAuth callback failures never reach this page — see below |

Brand mark and tagline are configured once as CSS custom properties
(`--nd-brand-mark`, `--nd-brand-tagline` in `:root`) instead of being
duplicated across selectors.

## OAuth callback failures (application side, not Keycloak-rendered)

`GET /auth/callback` in `backend/news_dashboard/auth_routes/router.py` never
returns a raw `HTTPException` to the browser. Invalid/missing OAuth state,
a missing authorization code, a provider-side denial (`?error=...`), and
token-exchange failures all redirect to `/login?auth_error=<code>`, where
`LoginPage` renders branded, non-sensitive recovery copy with a "try
Keycloak again" / "use email code" / "return home" path. A successful
callback restores the originally requested app route via a short-lived,
app-relative-only `next` cookie set by `/auth/login` and `/auth/register`.

## Manual verification checklist

1. `docker compose -f deploy/keycloak-theme/... up` (or the project's local
   Keycloak stack) with the `news-dashboard` theme selected on the realm.
2. Visit `/auth/login`, confirm the branded header, form controls, and
   primary button render instead of default PatternFly styling.
3. Trigger each state below and confirm branded rendering:
   - Wrong password → invalid-credentials alert.
   - Repeated wrong passwords until the realm's brute-force lockout fires →
     locked-account alert.
   - A user with a required action (e.g. `UPDATE_PASSWORD`) → required
     action form.
   - A user with OTP enabled → TOTP challenge form.
   - `/auth/register` → registration form; submit with an unverified email
     → verify-email page.
   - "Forgot password" → reset-credentials form.
   - Let the login `code` param expire, then submit → page-expired state.
4. Cancel the Keycloak login screen (deny consent, or navigate back) and
   confirm the app redirects to `/login?auth_error=oauth_denied` with
   branded copy instead of a raw error.
5. Tamper with or drop the `nd_oauth_state` cookie before completing
   `/auth/callback` and confirm `/login?auth_error=oauth_state`.
6. Stop the Keycloak container after `/auth/login` but before completing
   the callback, then finish the flow, and confirm
   `/login?auth_error=oauth_exchange_failed`.
7. Start the flow from a deep link (e.g. `/articles/42`) and confirm a
   successful login returns to `/articles/42` rather than `/`.
