# Privacy & Data Flow

News Dashboard is "your private news platform" — reading, triage, and saved
state stay in your own PostgreSQL database. This document lists every path
by which data can leave your instance, the feature/env var that triggers it,
and how to run with no outbound calls at all.

## Data that stays local

- Articles, feeds, sources, users, sessions, saved/read/starred/snoozed
  state, ingest run history, and search all live in your PostgreSQL
  database and are never sent anywhere.
- Local usage analytics (`user_events` — page views, article opens, reading
  duration) are recorded only in your database. See
  [Local analytics](#local-analytics-user_events) below.

## Outbound data flows

| Feature | Triggering env var | What's sent | To whom |
| --- | --- | --- | --- |
| Embeddings, Ask AI, briefings, insights, chat completions | `FREE_LLM_API_KEY` / `FREE_LLM_BASE_URL`, or `OPENAI_API_KEY` / `OPENAI_BASE_URL` | Article titles/bodies and your prompts/questions, as needed for the feature | The configured LLM gateway (a self-hosted gateway if you point `FREE_LLM_*` at one, otherwise OpenAI) |
| Text-to-speech / audio generation | `OPENAI_API_KEY` (always OpenAI; not replaceable by `FREE_LLM_*`) | Text to be synthesized into audio | OpenAI |
| AI-fallback body fetch (Crawl4AI / deterministic extraction fallback) | Feature-internal; used when normal ingestion fails to extract article body | The article URL being fetched | The configured LLM/body-fetch backend |
| LLM call tracing | `LANGFUSE_HOST` (or `LANGFUSE_BASE_URL`), `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | Full request/response payloads for every OpenAI-compatible call (embeddings, Ask AI, briefings, insights, TTS, body fetch), each tagged with a descriptive trace name | Your configured Langfuse instance (only when **both** keys are set; otherwise tracing is inactive and no data is sent) |
| Web Push notifications | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_EMAIL` | Push payload (notification title/body) and the subscription endpoint | The browser's push service (e.g. Mozilla/Google push endpoints), as chosen by the user's browser when they subscribe |
| Backend error tracking | `SENTRY_DSN`, `SENTRY_ENVIRONMENT` | Unhandled backend exception details (stack traces, request context) | The Sentry/GlitchTip-compatible endpoint at `SENTRY_DSN`. Unset by default — no SDK is initialized and no network calls are made |
| Frontend error tracking | `SENTRY_DSN_FRONTEND` | Unhandled frontend JS exception details | The Sentry/GlitchTip-compatible endpoint at `SENTRY_DSN_FRONTEND`. Served to the SPA via `GET /api/config`; DSNs are send-only and designed to be public. Unset by default |
| Keycloak login | `KEYCLOAK_AUTH_ENABLED`, `KEYCLOAK_SERVER_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | Login/authentication requests (standard OIDC flow) | Your configured Keycloak server. Optional; local password auth is used when disabled |

All of the above are **off unless you set their env vars**, with the
exception of the LLM features, which require an API key
(`FREE_LLM_API_KEY` or `OPENAI_API_KEY`) to function at all — see
[Requirements](README.md#requirements).

## Running fully self-contained

To run News Dashboard with zero outbound network calls:

1. Point AI features at your own infrastructure — set `FREE_LLM_BASE_URL`
   to a self-hosted OpenAI-compatible gateway, or leave both
   `FREE_LLM_API_KEY` and `OPENAI_API_KEY` unset to disable AI features
   entirely (embeddings, Ask AI, briefings, insights, TTS all become
   unavailable).
2. Leave `LANGFUSE_HOST`/`LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, and
   `LANGFUSE_SECRET_KEY` unset — tracing only activates when both keys are
   present.
3. Leave `SENTRY_DSN` and `SENTRY_DSN_FRONTEND` unset — no error-tracking
   SDK is initialized and no events are sent.
4. Leave `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` unset to disable Web Push
   notifications, or accept that push payloads transit the browser
   vendor's push service when a user opts in.
5. Leave `KEYCLOAK_AUTH_ENABLED` unset (or `false`) to use local password
   auth only.

With all of the above unset, every network call this app makes stays
between the browser, the backend, and your PostgreSQL database.

## Local analytics (`user_events`)

The app records lightweight usage events (route views, article
opens/closes, session heartbeats) in the `user_events` table to power the
in-app stats/analytics views. This data:

- Is stored only in your own PostgreSQL database — it is never transmitted
  to any external service.
- Is pruned automatically by a daily cleanup job after
  `ANALYTICS_RETENTION_DAYS` days (default `180`).

## Your data: export and deletion

- **Download your data**: Settings → Data Export → "Download archive" (or
  `GET /api/users/me/export`) returns a JSON file with your reading
  history, starred articles, highlights, shares, and daily briefings.
- **Delete your account**: Settings → Danger Zone → "Delete my account"
  (or `DELETE /api/users/me`) permanently removes your user row and all
  associated per-user data (articles state, highlights, shares, push
  subscriptions, OTPs, tags, goals, quizzes, etc.) via cascading deletes.
  You must type your username to confirm. Deleting the last remaining
  admin account is blocked — promote another user to admin first.

## See also

- [Configuration](README.md#configuration) — full environment variable
  reference.
- [SECURITY.md](SECURITY.md) — vulnerability disclosure policy and
  security-relevant configuration.
