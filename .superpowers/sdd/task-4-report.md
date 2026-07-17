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

## Coordinated fix wave

### Findings addressed

- Added claimant fencing using the PostgreSQL `claimed_at` value as an ownership token. Every transition now requires delivery ID, claim token, and expected current status. A stale worker receives `DeliveryClaimLostError` after another worker reclaims its delivery.
- Preserved the unique `(user_id, local_delivery_date)` claim and conservative stale-`sending` policy.
- Removed delivery-status pseudo-briefings from push fan-out. Only the claim winner receives the valid canonical briefing for push; repeated/losing scheduler paths do not push.
- Channel results are combined honestly: any enabled channel failure marks the per-user run failed, while later users still run.
- Moved unsubscribe-token creation and rendering before `rendered`, and converts preparation failures into fenced, sanitized `retryable_failed` transitions. Consent and SMTP-configuration checks are likewise caught and fenced from `rendered`.
- Added explicit default and scheduled Langfuse attribution coverage and exact 1,800-word ceiling coverage.

### RED evidence

- Claim fencing tests initially failed at collection because `DeliveryClaimLostError` and `_transition_delivery` did not exist.
- Scheduler regressions then failed because a losing claim returned success and a push exception was ignored (`assert False`, actual `True` in both cases).

### GREEN evidence

- Required focused suite: `204 passed in 15.91s`.
- PostgreSQL behavior coverage includes simultaneous claims, stale-worker fencing, due retry, opt-out-before-retry, stale `sending`, canonical reuse, sanitized preparation failure, and Bucharest repeated-DST-wall-time local-date uniqueness.
- Scheduler coverage includes email-only users, invalid timezone UTC fallback, Bucharest summer/winter offsets, repeated-path push suppression, honest push failure, and per-user failure isolation.
- `make lint`: passed after formatting.
- `make typecheck`: mypy, ty, pyrefly, and frontend typecheck passed.
