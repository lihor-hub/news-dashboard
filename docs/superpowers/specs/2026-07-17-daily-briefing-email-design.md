# Daily Briefing Email Design

**Date:** 2026-07-17
**Status:** Approved
**Issue:** [#1256](https://github.com/lihor-hub/news-dashboard/issues/1256)

## Goal

Deliver each opted-in user's canonical daily briefing to their account email at their configured local briefing time. The email must summarize the day's most important news in at most ten minutes of reading, ground claims in source links, remain useful on quiet days, and let the recipient unsubscribe without signing in.

The first release supports only the signed-in user's existing account email. It does not accept arbitrary recipient addresses or create a separate email-verification lifecycle.

## Product contract

Email is another publication channel for the existing saved briefing, not a second newsletter-generation system. The web briefing, push notification, and email therefore describe the same selected stories. Existing source subscriptions and user interests continue to define the candidate pool.

An email briefing contains:

- a 30–60 second executive summary;
- approximately 5–10 ranked stories, with no fixed minimum on quiet days;
- a concise explanation and “Why it matters” for each major story;
- direct source links and explicit attribution;
- an optional “Signals and hot takes” section that labels opinion separately from verified reporting;
- a compact “Worth opening” list that favors primary sources; and
- a link to the complete saved briefing in News Dashboard.

The target body length is 1,200–1,800 words. Generation must prefer relevance and impact over filling a quota. Duplicate coverage of one event is clustered into one story.

## Subscriber experience

The existing Daily Brief settings add an Email briefing section. It displays the account email and provides:

- an explicit enable or disable control;
- the existing briefing time and IANA timezone controls shared with push delivery; and
- a Send preview action that renders and sends the latest complete briefing without changing the regular delivery ledger.

Email delivery defaults to disabled for existing and new users. Enabling requires a non-empty account email. Guests and users without an account email see why the control is unavailable. Changing the account email automatically applies to future deliveries because the subscription stores no copied recipient address.

Settings and authenticated APIs can disable delivery. Every email also contains a signed one-click unsubscribe URL that works without a session. Unsubscribe is idempotent, immediately disables email delivery, and returns a small confirmation page with a link back to notification settings. The message includes `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers.

## Architecture

The existing APScheduler service remains the scheduling authority. Its per-user minute tick selects users whose email option is enabled and whose local wall clock matches `briefing_time` in `briefing_timezone`. `zoneinfo.ZoneInfo` handles daylight-saving transitions. Invalid legacy timezone values fall back to UTC and are logged; settings validation continues to reject new invalid values.

For each due user, the worker executes this flow:

1. Claim the user's local delivery date in PostgreSQL.
2. Generate or reuse the user's canonical complete briefing for the current local-day window.
3. Validate the reading budget, citations, links, and story distinctness.
4. Render the saved briefing into HTML and plain text with Jinja.
5. Re-check that the user is subscribed immediately before SMTP dispatch.
6. Send the message and record the outcome.

The existing LangGraph briefing graph remains responsible for candidate selection, clustering, drafting, citation verification, and assembly. This feature adds delivery-oriented validation around the graph result rather than a parallel graph. Existing PostgreSQL briefing and agent-run tables remain the product-visible source of truth; no LangGraph checkpointer is added.

### Selective web enrichment

Normal generation uses articles already collected by the ingestion system. This preserves source preferences, predictable cost, and reproducibility. An optional enrichment step may search configured web sources only for a high-scoring story when the available articles lack a primary source or enough context to explain impact.

Enrichment prefers, in order:

1. official lab, company, project, or regulator publications;
2. original research papers, release notes, or repositories;
3. original public posts from a named commentator; and
4. reputable reporting that adds material context.

Enrichment results enter the same citation-verification boundary as ingested articles. A search failure does not fail the briefing; the graph continues with the grounded material already available. Broad autonomous web browsing for every story is outside this release.

## Persistence and idempotency

Add an email opt-in boolean to `users`, defaulting to false. Reuse `email`, `briefing_time`, and `briefing_timezone`; do not copy them into a subscription table.

Add a `briefing_email_deliveries` table with:

- `id`;
- `user_id` and optional `briefing_id` foreign keys;
- `local_delivery_date`;
- `status`: `claimed`, `rendered`, `sending`, `sent`, `retryable_failed`, `permanent_failed`, `skipped`, or `unsubscribed`;
- `attempt_count` and `next_attempt_at`;
- `provider_message_id` when available;
- a sanitized error code and message;
- `claimed_at`, `sent_at`, `created_at`, and `updated_at` timestamps.

A unique constraint on `(user_id, local_delivery_date)` provides exactly-once claiming for scheduled delivery. Claiming uses PostgreSQL conflict handling so concurrent application replicas cannot create two sends. A stale claim may be recovered after a bounded timeout. Delivery state is separate from briefing generation state, allowing SMTP retries to reuse the saved briefing without another model invocation.

The Send preview path is intentionally excluded from this table's scheduled-delivery uniqueness contract. It is rate-limited and recorded as an audit event through existing operational logging.

## Rendering and transport

Create focused Jinja HTML and plain-text templates rather than assembling markup in Python. The HTML uses a responsive, table-based layout with inline styles for broad email-client compatibility. It contains a preheader, branded header, date and timezone, reading-time estimate, executive-summary panel, story cards, primary links, web-briefing call to action, and preference/unsubscribe footer.

Jinja autoescaping is mandatory for HTML. Article and generated fields are untrusted. Only normalized `http` and `https` URLs may become links; other schemes are rendered as text or omitted. The plain-text template preserves the same story order, source URLs, preference URL, and unsubscribe URL.

Refactor the current SMTP configuration into a reusable transport used by OTP and briefing email without changing existing environment-variable precedence. The transport supports STARTTLS and implicit TLS, authentication when configured, an explicit sender address, MIME multipart alternatives, and custom headers. SMTP configuration remains deployment-owned; no email vendor SDK is introduced.

## Unsubscribe security

Unsubscribe tokens are generated with `itsdangerous.URLSafeTimedSerializer` using the existing server signing secret and a new purpose-specific salt. The payload contains only the user ID, action, and token version. It does not contain the email address. Verification enforces the action and a bounded lifetime; settings remains the permanent fallback after token expiry.

The public endpoint accepts both the GET link used by conventional email clients and RFC 8058 one-click POST. Both paths perform only the scoped disable action. Tokens are never written to application logs, Langfuse traces, analytics events, or delivery errors.

Unsubscribe is checked again immediately before send. A queued retry cannot override a later unsubscribe.

## Langfuse observability

Generation uses the repository's native `langfuse.langchain.CallbackHandler` and `propagate_attributes` integration. Each scheduled run uses a session ID shaped as `daily-email:{user_id}:{local_date}` and tags such as `daily-email` and `briefing`. The existing root briefing trace ID remains attached to the saved briefing.

Traces may include:

- prompt name and version;
- configured model;
- candidate and selected-story counts;
- whether enrichment ran and which source classes it used;
- citation coverage and removed unsupported citations;
- estimated word count and reading time;
- node latency, token usage, and retry count; and
- a delivery outcome category that contains no recipient data.

Email addresses, unsubscribe tokens, SMTP credentials, rendered MIME payloads, and full provider errors are excluded. Langfuse remains optional and non-fatal; generation and delivery work normally without credentials.

## Quality gates

Before rendering, deterministic validation checks:

- the configured reading budget;
- that every citation references an allowed candidate or enrichment result;
- safe and non-empty external URLs;
- repeated citations and materially duplicated story groups;
- that opinion sections are labeled; and
- that an executive summary is present when at least one story exists.

Invalid citations and links are removed. A structurally invalid or over-budget draft receives the existing bounded generation retry. Exhausted generation retries fail the briefing and leave the email delivery retryable only after a new valid briefing exists. A day with no qualifying articles records a skipped delivery and sends no filler email.

## Failure handling

Failures are isolated per user. One generation or SMTP failure cannot stop other due users.

Transient network, rate-limit, and SMTP 4xx failures use bounded exponential backoff with jitter. Authentication errors, invalid recipients, missing deployment configuration, and SMTP 5xx responses become permanent failures until configuration or the account email changes. Error storage and logs use sanitized categories; raw responses that may contain recipient addresses are not persisted.

The send transition follows `claimed → rendered → sending → sent`. Because SMTP cannot participate in the PostgreSQL transaction, a process crash after the server accepts the message but before `sent` is recorded leaves a small duplicate risk. Recovery treats stale `sending` rows conservatively and does not automatically resend unless the transport can provide an idempotency key or delivery status. This is at-most-once-biased behavior at the final network boundary, while database claiming remains exactly once.

## API surface

Extend the existing notification settings payload with `email_enabled` and account-email availability metadata. The existing authenticated settings endpoint validates attempts to enable email without an account address.

Add:

- an authenticated preview-send endpoint with per-user rate limiting;
- a public tokenized unsubscribe GET endpoint; and
- a public RFC 8058 unsubscribe POST endpoint.

The settings response never exposes unsubscribe tokens or delivery errors. Admin run history may expose sanitized delivery status and timestamps through a separate operational endpoint if the existing run-history view is extended during implementation.

## Deployment configuration

Reuse the existing generic SMTP host, port, username, password, sender, and TLS configuration. Helm and Docker deployment examples document the sender and public application base URL required for absolute email links. Missing SMTP configuration keeps email controls visible but reports delivery as unavailable and prevents enabling when the backend exposes that capability state.

The initial default delivery time for a newly configured user remains the repository's existing default. The product may display 21:00 as a suggested value, but this feature does not silently change existing users' schedules.

## Testing and verification

Use red-green-refactor for each slice.

Backend unit tests cover:

- Jinja HTML and text rendering, autoescaping, safe-link filtering, and content order;
- signed token validity, expiry, purpose binding, tamper resistance, and idempotent unsubscribe;
- local-time matching across Europe/Bucharest summer and winter offsets and DST boundaries;
- reading-budget and citation validation;
- SMTP MIME structure, headers, TLS modes, and sanitized failures; and
- Langfuse callbacks, propagated session attributes, and sensitive-data exclusion.

PostgreSQL integration tests cover:

- opt-in defaults and notification-settings updates;
- concurrent and repeated delivery claims;
- stale claim recovery and status transitions;
- unsubscribe-before-retry behavior;
- reuse of a completed canonical briefing; and
- skipped quiet-day delivery.

Frontend tests cover enabled, disabled, unavailable-email, saving, preview, and error states. Browser verification exercises the settings flow at mobile and desktop widths. The focused suites run first, followed by the repository's Python and TypeScript gates and the full backend suite with PostgreSQL parallel query workers disabled as required by `AGENTS.md`.

## Non-goals

This release does not:

- accept arbitrary newsletter recipient addresses;
- implement a separate double-opt-in address-verification flow;
- replace the existing feed ingestion system with unrestricted web search;
- add a third-party newsletter or transactional-email SDK;
- add LangGraph checkpoint persistence alongside the existing workflow tables;
- guarantee final-hop exactly-once delivery when plain SMTP cannot expose an idempotency mechanism; or
- send a low-value filler email when no important stories qualify.
