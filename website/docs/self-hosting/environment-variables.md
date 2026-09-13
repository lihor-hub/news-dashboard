---
title: Environment variables
sidebar_position: 2
---

# Environment variables

## Environment catalogue

Copy [`.env.example`](https://github.com/lihor-hub/news-dashboard/blob/main/.env.example) to `.env` and fill in real values to get
started; it enumerates every variable below plus a few advanced/internal
knobs.

Runtime storage is PostgreSQL only. Set `DATABASE_URL` or the split
`POSTGRES_*` variables.

| Variable                                                                                                         | Use                                                                                                                                                                                                                                                                                                                                                                              |
| ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`                                                                                                   | PostgreSQL DSN.                                                                                                                                                                                                                                                                                                                                                                  |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`                            | PostgreSQL connection parts used when `DATABASE_URL` is unset.                                                                                                                                                                                                                                                                                                                   |
| `SESSION_SECRET`                                                                                                 | Signed session key. Also signs digest mark-read tokens when `TOKEN_SECRET` is unset. Generate with `python -c "import secrets; print(secrets.token_hex(32))"`.                                                                                                                                                                                                                   |
| `TOKEN_SECRET`                                                                                                   | Optional override used to sign one-click digest mark-read tokens. Set this when digest token rotation should be independent from `SESSION_SECRET`.                                                                                                                                                                                                                               |
| `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`                                                           | First local admin account. Used only when no users exist.                                                                                                                                                                                                                                                                                                                        |
| `FREE_LLM_API_KEY`, `FREE_LLM_BASE_URL`                                                                          | Primary API key and base URL for chat, embeddings, Ask AI, and briefings. Use these to point at a self-hosted OpenAI-compatible gateway. Falls back to `OPENAI_API_KEY` / `OPENAI_BASE_URL` when not set.                                                                                                                                                                        |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL`                                                                              | OpenAI credentials. Required for TTS/audio (not replaceable by the free LLM gateway). Also used as fallback for all other AI features when `FREE_LLM_API_KEY` is absent.                                                                                                                                                                                                         |
| `OPENAI_BRIEFING_MODEL`                                                                                          | Model name for briefing generation (e.g. `auto` for a routing gateway, or a specific model ID). Defaults to `gpt-4o-mini`.                                                                                                                                                                                                                                                       |
| `TAVILY_API_KEY`                                                                                                | Enables automatic Deep Agent web research for the first five sourced sections in canonical briefing order. When unset or when research fails, email delivery uses the canonical briefing without enrichment.                                                                                                                                                                  |
| `OPENAI_BRIEFING_ENRICHMENT_MODEL`                                                                              | Optional model override for briefing-email Deep Agent research. Defaults to `OPENAI_BRIEFING_MODEL`, then `gpt-4o-mini`.                                                                                                                                                                                                                                                        |
| `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`                                                    | Traces every OpenAI call (embeddings, Ask AI, briefings, insights, TTS, body fetch) in [Langfuse](https://langfuse.com), each tagged with a descriptive name (`ask-ai`, `briefing-generation`, …). Tracing activates only when both keys are set; otherwise the app uses a plain OpenAI client with no tracing. `LANGFUSE_BASE_URL` is accepted as an alias for `LANGFUSE_HOST`. |
| `KEYCLOAK_AUTH_ENABLED`, `KEYCLOAK_SERVER_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | Enables Keycloak. See [Authentication (Keycloak)](../configuration/authentication.md).                                                                                                                                                                                                                                                                      |
| `DIFY_CHAT_ENABLED`, `DIFY_CHAT_BASE_URL`, `DIFY_CHAT_APP_TOKEN`, `DIFY_CHAT_TITLE`                              | Enables the optional host-owned Dify WebApp iframe assistant. Use a separate Dify origin, HTTPS except for supported loopback HTTP development addresses, and a Publish → Embed token—never a Dify service/API key. See [Dify assistant](../configuration/dify-assistant.md).                                                                               |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`                                                                          | VAPID public and private keys for Web Push notifications. Generate using `npx web-push generate-vapid-keys`.                                                                                                                                                                                                                                                                     |
| `VAPID_EMAIL`                                                                                                    | Contact email address used in VAPID claims mailto link. Defaults to `admin@example.com` if unset.                                                                                                                                                                                                                                                                                |
| `CORS_ORIGINS`                                                                                                   | Comma-separated browser dev origins.                                                                                                                                                                                                                                                                                                                                             |
| `ANALYTICS_RETENTION_DAYS`                                                                                       | Days to retain `user_events` before the daily cleanup job prunes them. Defaults to `180`.                                                                                                                                                                                                                                                                                        |
| `ANALYTICS_ENABLED`                                                                                              | Instance-wide analytics kill switch. Set to `false` to stop ingesting `user_events` for every user regardless of their individual Settings preference. Defaults to `true`. Users can opt out individually from Settings → Privacy.                                                                                                                                               |
| `ENABLE_API_DOCS`                                                                                                | Serves the interactive API docs (`/docs`, `/redoc`, `/openapi.json`) when truthy. Off by default so a public deployment doesn't leak its full API surface.                                                                                                                                                                                                                       |
| `PUBLIC_RENDERER_EGRESS_PROXY`                                                                                   | Credential-free HTTP(S) validating proxy for optional Selenium fallback. Direct browser egress must be blocked; use IP/network allowlisting or external proxy authentication instead of URL userinfo.                                                                                                                                                                            |
| `NEWSLETTER_IMAP_HOST`, `NEWSLETTER_IMAP_PORT`, `NEWSLETTER_IMAP_USERNAME`, `NEWSLETTER_IMAP_PASSWORD`           | Shared IMAP mailbox polled for newsletter emails (`newsletter_ingest.py`). Feature is fully inert unless host, username, and password are all set. Port defaults to `993`.                                                                                                                                                                                                       |
| `NEWSLETTER_IMAP_FOLDER`                                                                                         | Mailbox folder to poll for newsletters. Defaults to `INBOX`.                                                                                                                                                                                                                                                                                                                     |
| `NEWSLETTER_POLL_MINUTES`                                                                                        | Interval in minutes between newsletter mailbox polls. Defaults to `15`.                                                                                                                                                                                                                                                                                                          |
| `NEWSLETTER_MAX_MESSAGE_BYTES`                                                                                   | Max accepted size in bytes for one RFC822 newsletter message. Oversized messages are skipped and marked seen (not retried) before full parsing. Defaults to 5 MiB (`5242880`).                                                                                                                                                                                                   |

SQLite is supported only as a legacy import source for
`news-dashboard-migrate sqlite-to-postgres`.

### AI orchestration and tracing

The backend uses the vanilla LangChain and LangGraph APIs according to the
shape of each AI operation:

- LangChain composes Ask AI, briefing chat, lesson chat, prompts, model calls,
  and structured output parsing.
- LangGraph orchestrates briefing generation, lesson generation, and agent
  action planning and execution. These graphs are compiled without a
  checkpointer. PostgreSQL run and step records remain the source of truth for
  workflow status and history, including idempotency and stale-run recovery
  where those behaviors apply.
- Deep Agents runs bounded, read-only web research for the first five sourced
  sections in canonical briefing order when `TAVILY_API_KEY` is configured.
  PostgreSQL stores the
  validated enrichment for retry and preview reuse; research failure falls back
  to the unchanged canonical email.
- Native provider clients remain in use for embeddings, TTS, image generation,
  and isolated calls that do not need chain or graph orchestration.

Langfuse tracing is optional. When both Langfuse keys are configured,
framework call sites use `langfuse.langchain.CallbackHandler` and
`langfuse.propagate_attributes(...)` directly. Each request or operation still
has its own trace; a Langfuse session groups related traces without replacing
the trace IDs used for feedback.

Managed prompts are fetched by the stable `production` label by default.
Langfuse assigns every saved prompt an immutable version, and the exact fetched
prompt object is linked to its generation in each trace. This makes prompt
version, labels, trace, user, and session available together in Langfuse. The
prompt optimizer writes proposed revisions as new `candidate`-labeled versions;
promoting or rolling back means moving the `production` label in Langfuse, not
deploying application code. Internal callers may also request an exact prompt
version when a reproducible evaluation or rollback requires it.

| Operation                                   | Langfuse session ID                                                                |
| ------------------------------------------- | ---------------------------------------------------------------------------------- |
| Ask AI                                      | Optional client-provided `session_id`; omitted requests remain independent traces. |
| Briefing conversation                       | `briefing:{user_id}:{briefing_id}`                                                 |
| Lesson conversation and related lesson work | `lesson:{user_id}:{lesson_id}`                                                     |
| Briefing generation                         | `briefing-run:{run_id}`                                                            |
| Lesson generation                           | `lesson-run:{run_id}`                                                              |
| Agent action lifecycle                      | `agent-action:{run_id}`                                                            |

`POST /api/ask` accepts the optional field alongside its existing inputs:

```json
{
  "query": "What changed in LangGraph this week?",
  "include_all": false,
  "session_id": "research:langgraph-weekly"
}
```

Session IDs must be ASCII strings of at most 199 characters. Blank strings are
treated as absent; invalid values receive a request validation error. Existing
clients can omit `session_id`.

> **Upgrading an existing deployment:** article embeddings moved from an
> opaque BLOB column to [pgvector](https://github.com/pgvector/pgvector), so
> similarity search (Ask AI, topic map, recommendations) runs in SQL instead
> of Python. Swap your Postgres image to `pgvector/pgvector:pg16` (or install
> the `vector` extension on an external Postgres) before starting the new
> version — the app backfills existing embeddings into the new column
> automatically on first boot. Starting against a Postgres without the
> extension fails fast with a clear error naming it.

## Production settings

The catalogue above covers shared runtime settings; the sections below explain
production requirements and optional features.

### Required Variables

| Variable                   | Description                                                                                   |
| -------------------------- | --------------------------------------------------------------------------------------------- |
| `SESSION_SECRET`           | Signed session key. Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `BOOTSTRAP_ADMIN_USERNAME` | Initial admin username (created on first run)                                                 |
| `BOOTSTRAP_ADMIN_PASSWORD` | Initial admin password                                                                        |
| `POSTGRES_PASSWORD`        | PostgreSQL database password                                                                  |

### Optional AI Features

| Variable            | Description                                 |
| ------------------- | ------------------------------------------- |
| `OPENAI_API_KEY`    | OpenAI API key for summaries, insights, TTS |
| `FREE_LLM_API_KEY`  | Alternative LLM API key                     |
| `FREE_LLM_BASE_URL` | Custom LLM endpoint                         |

### Optional Email Delivery

Email delivery remains disabled until the deployment provides a complete SMTP
configuration and an absolute, browser-facing `APP_BASE_URL`. Enabling email
controls in a user's settings does not make delivery available by itself.

| Variable       | Description                                                                         |
| -------------- | ----------------------------------------------------------------------------------- |
| `SMTP_HOST`    | SMTP relay hostname.                                                                |
| `SMTP_PORT`    | SMTP relay port.                                                                    |
| `SMTP_USER`    | SMTP login username.                                                                |
| `SMTP_PASS`    | SMTP login password. Store this outside version control.                            |
| `SMTP_FROM`    | Sender address used for outbound messages.                                          |
| `SMTP_TLS`     | Transport mode: `starttls`, `ssl`, or `none`.                                       |
| `APP_BASE_URL` | Absolute public URL used for links in email, independent of Keycloak configuration. |

`SMTP_USERNAME` and `SMTP_PASSWORD` remain supported for legacy OTP email
deployments. OTP-specific `OTP_SMTP_*` values retain precedence when set. With
Helm, configure the non-secret values under `app.email`, set
`app.publicBaseUrl`, and provide credentials through `app.email.existingSecret`;
the chart does not render credential values into the Deployment.

For email links, `APP_BASE_URL` takes precedence over the compatibility
variables `NEWS_DASHBOARD_BASE_URL` and `NEWS_DASHBOARD_URL`, in that order.

### Optional Observability

| Variable              | Description                                                                                                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `METRICS_ENABLED`     | Set to `true` to expose the Prometheus `/metrics` endpoint. Off by default.                                                                                                          |
| `SENTRY_DSN`          | Backend error tracking. Point at a Sentry or GlitchTip-compatible DSN to capture unhandled exceptions. Off by default — no SDK initializes and no network calls are made when unset. |
| `SENTRY_ENVIRONMENT`  | Environment tag attached to backend events (e.g. `staging`, `production`). Defaults to `production` when `SENTRY_DSN` is set.                                                        |
| `SENTRY_DSN_FRONTEND` | Frontend error tracking. Served to the SPA via `GET /api/config`; safe to expose since Sentry DSNs are send-only. Off by default.                                                    |

### Optional Dify assistant

News Dashboard can show an optional host-owned Dify WebApp iframe assistant to
signed-in users. Set `DIFY_CHAT_ENABLED=true`, a browser-reachable
`DIFY_CHAT_BASE_URL`, and the `DIFY_CHAT_APP_TOKEN` from Dify **Publish →
Embed**; `DIFY_CHAT_TITLE` controls the accessible label. Production URLs must
use HTTPS; HTTP is accepted only at `localhost`, `127.0.0.1`, and `[::1]` for
development. Dify must use an origin separate from News Dashboard; same-origin
configuration is rejected to protect the authenticated parent page. The iframe
is additionally sandboxed for Dify's required scripts, origin storage, forms,
downloads, and constrained popups, without top-navigation permission. The
embed token is intentionally sent to the browser, so it is not a service/API
key and cannot secure private Dify tools or data. News Dashboard sends no
username, email, user ID, or page context; Dify's WebApp identity is separate.
For the Dify app choice, self-hosted `ALLOW_EMBED=true`, reverse-proxy
`frame-src` and SSE requirements, Helm values, and verification, see the [Dify
assistant guide](../configuration/dify-assistant.md).

### Privacy

| Variable            | Description                                                                                                                                                                                                                                                                                                                                   |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ANALYTICS_ENABLED` | Instance-wide analytics kill switch. Set to `false` to stop ingesting `user_events` (route views, time-on-app, article dwell, feature usage) for every user regardless of their individual preference. Defaults to `true`. Users can additionally opt out for themselves from Settings → Privacy, enforced server-side in `POST /api/events`. |

### Optional Security

| Variable          | Description                                                                                                                                                                                                                                   |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ENABLE_API_DOCS` | Set to `true` to serve the interactive API docs (`/docs`, `/redoc`, `/openapi.json`). Off by default so a public deployment doesn't leak its full API surface to anonymous visitors; enable it for local development or trusted environments. |
| `ENABLE_HSTS`     | Set to `true` to have the app send `Strict-Transport-Security` itself. Off by default for local HTTP development; the production Helm overlay enables it alongside the TLS Ingress middleware. |

> **Important**: Never commit secrets to version control. Use environment variables or a `.env` file (not committed to Git) to manage sensitive values.

### Baseline browser security headers

The app itself sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, and a conservative `Permissions-Policy` on
every response (API and static frontend alike), so this baseline applies
regardless of which front door is used — `docker run`,
`docker-compose.prod.yml`, or Kubernetes Ingress.
`Strict-Transport-Security` stays opt-in via `ENABLE_HSTS` above, and the
production Helm overlay opts in. The production Ingress provides the static
edge baseline; the application remains the source of truth for its dynamic
Content Security Policy.

### Public browser renderer proxy

Selenium fallback for user-controlled public URLs stays disabled unless
`PUBLIC_RENDERER_EGRESS_PROXY` names an HTTP or HTTPS proxy that validates and
pins every public destination. Direct renderer egress must also be blocked.
The URL must contain only a host and optional usable port; whitespace, paths,
query strings, and username/password userinfo are rejected. Proxy credentials
are deliberately unsupported in this URL so they cannot reach Chrome's process
arguments. Authenticate the renderer by source-IP/network allowlisting or an
external proxy authentication mechanism that does not embed secrets in the
Chrome command line.

### Optional article body extraction (Crawl4AI)

When a reader opens an article, the app fetches and caches the full body text.
The fallback chain is: the built-in static/Selenium extractor first, then
[Crawl4AI](https://github.com/unclecode/crawl4ai) (a deterministic
browser-based Markdown extractor), and finally the token-expensive LLM
extractor as a last resort.

Crawl4AI is an **optional** extra — it pulls in a browser and a large
dependency tree, so it is not installed by default and is intentionally kept
out of the committed `uv.lock` baseline; its dependencies are resolved when you
opt in. When it is absent, the app simply skips that layer and falls back to the
LLM extractor as before.

> **Security note:** Crawl4AI currently pins an older `lxml` that carries a
> known XXE advisory ([GHSA-vfmq-68hx-4jfw](https://github.com/advisories/GHSA-vfmq-68hx-4jfw),
> patched in lxml 6.1.0). Only enable this extra in environments where you are
> comfortable with that transitive dependency, and prefer running it against
> trusted article sources.

To enable it in a dev or self-hosted environment:

```bash
# 1. Install the extra
pip install -e '.[crawl4ai]'      # or: pip install '.[crawl4ai]'

# 2. Install the browser it drives (run once)
crawl4ai-setup                    # or: playwright install --with-deps chromium
```

In containerized/Kubernetes deployments, run the same two commands in the image
build (`RUN pip install '.[crawl4ai]' && crawl4ai-setup`) so the Chromium
browser is baked into the image; the extractor launches a headless browser at
runtime and does not download anything on demand.

Article URLs are still validated by the app's SSRF/scheme safety checks before
Crawl4AI is invoked, so `file://`, loopback, and private-network URLs never
reach the browser.
