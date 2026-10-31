# Privacy & Data Flow

News Dashboard is "your private news platform" — reading, triage, and saved
state stay in your own PostgreSQL database. This document lists every path
by which data can leave your instance, the feature/env var that triggers it,
and how to run with no outbound calls at all.

## Data that stays local

- Articles, feeds, sources, users, sessions, saved/read/starred/snoozed
  state, ingest run history, and search all live in your PostgreSQL
  database and are never sent anywhere.
- Optional Neo4j graph data also stays on your instance. It mirrors article IDs,
  titles, URLs, source slugs, discovery timestamps, entity nodes, mention
  edges, and extracted relationship edges for graph exploration; PostgreSQL
  remains the application database.
- Local usage analytics (`user_events` — page views, article opens, reading
  duration) are recorded only in your database. See
  [Local analytics](#local-analytics-user_events) below.

## Outbound data flows

| Feature | Triggering env var | What's sent | To whom |
| --- | --- | --- | --- |
| Embeddings, Ask AI, briefings, insights, chat completions | `FREE_LLM_API_KEY` / `FREE_LLM_BASE_URL`, or `OPENAI_API_KEY` / `OPENAI_BASE_URL` | Article titles/bodies, extracted entity relationship context, and your prompts/questions, as needed for the feature | The configured LLM gateway (a self-hosted gateway if you point `FREE_LLM_*` at one, otherwise OpenAI) |
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

## Approximate active time

With usage analytics enabled both for your account and this instance, authenticated
visible, focused, connected app use is measured approximately. It pauses after exactly
five minutes without interaction. Quiet reading within that window counts; background
audio, offline use, hidden/unfocused pages and offline catch-up do not. No click targets,
keystrokes, pointer coordinates or persistent device fingerprints are recorded.
Generic app time never qualifies an article read.

A 15-second heartbeat consumes a server-anchored window of at most 30 seconds. Overlapping
tabs/devices and retries are deduplicated with a 120-second logical accounting/retry horizon.
A registered minute cleanup removes expired transient windows, payload hashes, receipts and
interval unions within 180 seconds while the scheduler is running. An unavailable scheduler
can delay physical deletion, but never extends the logical acceptance deadline. Frozen
saved-progress-local day/zone aggregates are retained for 400 days; lifetime millisecond totals,
measurement start, bounded coverage-gap flags and permanently earned 15-minute/1-hour/5-hour/
20-hour badges remain until account deletion. Timezone edits never rebucket past days.
Consent changes invalidate outstanding time windows and automatic-reading evidence under the
same account lock. Presentation preferences do not stop measurement. Disabling measurement
preserves existing totals and badges; reenabling cannot fill gaps.

These totals are approximate engagement, not proof of learning or a complete lifetime record.
Historic global availability is unknown, even when a total is zero; coverage is always partial
or unknown. Network latency, suspension, OS termination and failed best-effort final sends can
lose time. Web/mobile browsers, installed PWA, Electron's hosted renderer, Android TWA and iOS
Safari/PWA share this conservative web lifecycle, not a native background service or a claim of
native-device parity. There is no browser-extension tracker.

Archive-v2 exports your owned totals, frozen day aggregates, coverage flags and badge dates,
not activity window tokens, interval unions, payload hashes, receipts or rate counters.
Uploaded time/rewards are informational only and cannot restore or earn progress. Account
deletion cascades all activity rows. Legacy analytics time remains a separate estimate and is
never converted into these totals or badges.

## Functional daily progress

Authenticated visible app visits store one saved-local calendar date, its timezone,
first observation, whether it qualified for credit, and welcome consumption status.
Daily streak counters and permanently earned rewards stay in PostgreSQL until account
deletion. No device fingerprint, IP address, route log, or reading-history-derived
visit backfill is used for this ledger. Guest visits do not create personal progress.

This functional record is independent of optional analytics: turning analytics off,
or disabling daily welcome popups or reward animations, does not stop daily credit.
The two presentation preferences are independent and default on. Progress has its own
saved timezone; changing it does not reschedule briefing email. Past dates stay frozen;
travel can suppress a credit or restart a streak without removing the best or rewards.
A welcome is consumed atomically across devices before display; a lost response or
crash may lose feedback, but never earned progress. No offline retro-credit is recorded.

Archive v2 includes account-scoped daily dates, counters, awards, presentation claims
and progress preferences. Exported progress is informational, **not restored** from an
uploaded archive; only validated progress preferences are restored. Account deletion
cascades these functional records. Existing delivered or forwarded email cannot be
recalled or erased from recipients' mailboxes.

## Permanent qualifying reads and optional automatic reading

Manual Done (including authorized legacy, Google Reader and approved agent declarations)
records one permanent qualifying read per account and versioned normalized URL identity.
Article-kind Reading List items share that identity; other kinds and audio finishing alone
do not qualify. Signed email links require a human confirmation POST; merely fetching the
link does not record completion. Unread/Undo changes the list, never removes credit or badges.

We retain a SHA-256 URL digest, provenance, recording time and any known live effective time
until account deletion, even if article retention removes the article. This digest is
pseudonymous and guessable, **not anonymous**. Different URLs for one story can count
separately. Imported article completion evidence is self-reported, has unknown earned time,
and earns silently; uploaded progress totals or reward claims are never trusted. Historical
reconciliation is separately operated, not a scan performed by opening the collection.

Automatic reading is optional analytics, separate from generic app-active time. It requires
a loaded authorized body, visible focused connected reading with no five-minute idle gap,
90% body progress, 30–120 attentive seconds based on body length, and two seconds at the end.
This approximates attention, not comprehension. Unsupported word segmentation uses 120 seconds.
No offline catch-up, external-page, summary-only or audio-only evidence qualifies. Consent and
the instance analytics switch are checked server-side; opting out clears unfinished evidence
but preserves functional manual progress and earned rewards. At most one aggregate reader
lease per account stores a body hash, bounded durations, sequence and last bounded retry
receipt, not a scroll trail or interaction log. Pending evidence becomes invalid after 24 hours
and expired rows are removed by the existing telemetry cleanup and on the next reader request.

Topic progression uses only the first qualifying read's title and summary, not your tags,
interests or a remote AI service. At most two relevant tracks are frozen, including a result
with no topics, with taxonomy/rule versions and a compact title/summary evidence code. New
credits do not retain a title or summary copy. A transitional pending source, if present in
an older build, must be consumed/deleted atomically using its original text, never later
article text. No operational historical processing is performed automatically. Export includes
owned credits, frozen topic attribution, awards and any transitional pending sources, never
reader tokens or retry evidence. Uploaded progress remains informational, not reward authority.
Counts and earned levels survive unread, content deletion and later classifier changes;
historical totals remain incomplete pending reconciliation. Account deletion cascades all of
these records; article deletion clears its reference and unfinished evidence, not earned credit.

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

- [Configuration](https://docs.lihor.ro/docs/self-hosting/environment-variables) — full environment variable
  reference.
- [SECURITY.md](SECURITY.md) — vulnerability disclosure policy and
  security-relevant configuration.
