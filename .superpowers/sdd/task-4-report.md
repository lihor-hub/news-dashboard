# Task 4 report

## Outcome

Implemented claim-safe scheduled daily briefing email delivery and integrated it with the existing per-user APScheduler path.

## Behavior

- Added PostgreSQL `INSERT ... ON CONFLICT DO NOTHING RETURNING` delivery claims.
- Added conservative recovery for stale `claimed` and due `retryable_failed` rows; stale `sending` is never reclaimed.
- Claims precede generation, current-local-day complete briefings are reused, and quiet days become `skipped`.
- Delivery follows `claimed -> rendered -> sending -> sent`, rechecking consent, account email, and SMTP configuration immediately before `sending`.
- SMTP transport failures are sanitized and classified as retryable; missing email/configuration are permanent.
- Email-only subscribers are selected by the per-user scheduler; push and email execution remain isolated per user and use one canonical briefing.
- Scheduled generation overrides Langfuse session/tags with `daily-email:{user_id}:{date}` and `[daily-email, briefing]`; default callers retain existing attributes.
- Briefing validation now requires a summary for non-empty story sets, removes unsafe/duplicate citations, and enforces the 1,800-word ceiling.

## TDD evidence

- RED: focused test collection failed because `claim_delivery` was missing.
- GREEN: `189 passed in 8.99s` across delivery, scheduler, briefing DB, and briefing agent tests.

## Gates

- `make lint`: passed.
- `make typecheck`: mypy, ty, pyrefly, and frontend typecheck passed.

## Self-review

- Claim and retry updates are single PostgreSQL statements and preserve replica safety.
- The final SMTP boundary remains intentionally at-most-once-biased: a stale `sending` row is observable but not resent.
- Stored error fields contain category strings only; recipient addresses, tokens, provider responses, and rendered content are not persisted.

## Concerns

- Plain SMTP cannot close the crash window between provider acceptance and recording `sent`; the conservative `sending` policy avoids automatic duplicates as required.
