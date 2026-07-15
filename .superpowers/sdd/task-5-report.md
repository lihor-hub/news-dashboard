# Task 5 report

## Status

Implemented the immutable 19-entry prompt catalog, idempotent Langfuse synchronization command,
feature-module catalog adoption, and operator documentation.

## TDD evidence

- RED: `backend/tests/test_prompt_catalog.py` failed at collection because
  `news_dashboard.prompt_catalog` did not exist.
- GREEN: focused catalog tests pass: 7 passed.
- Affected behavior suite: 443 passed with 1 pre-existing Starlette deprecation warning.

## Implementation

- Frozen catalog entries contain a unique name, prompt type, immutable text/chat prompt content,
  and an optional commit message.
- All 19 Task 2–4 feature call sites resolve their local fallbacks from the same catalog used by
  the synchronization script; existing private test compatibility constants are derived from the
  catalog rather than duplicating prompt text.
- The sync command reads its host and credentials only from environment variables, compares each
  current production prompt before writing, creates changed or missing versions with
  `labels=["production"]`, and prints names, versions, and status only.
- README operations cover offline verification, synchronization, production-label rollback, and
  disabling Langfuse to return to local fallbacks.

## Verification

- `make lint`: passed.
- `make typecheck`: passed (mypy, ty, pyrefly, and frontend typecheck).
- `git diff --check`: passed.
- Full repository pytest intentionally deferred to Task 6; the complete affected prompt behavior
  suite passed.

## Concerns

- The affected suite retains one existing Starlette/httpx deprecation warning.
- `.env` remains unsafe to source directly because of an existing unquoted value; verification
  used the repository-supported `dotenv run --` loader without printing or modifying credentials.

## Review follow-up

- Replaced the synchronization command's broad prompt-lookup exception handling with the
  Langfuse SDK's public `NotFoundError` from
  `langfuse.api.commons.errors.not_found_error`. Only that response now means a prompt is absent;
  authentication, network, server, and unexpected failures propagate without creating a version.
- Replaced the missing-prompt test's generic `RuntimeError` with an actual SDK `NotFoundError` and
  added a regression proving a generic lookup failure is re-raised with zero create calls.
- Documented why the synchronization script's catalog import requires `# noqa: E402`: it follows
  the explicit backend path setup needed when running the script directly.

### Review TDD and verification evidence

- RED: the generic-failure regression failed because the command swallowed `RuntimeError` and
  issued 19 create calls.
- GREEN: `dotenv run -- .venv/bin/pytest backend/tests/test_prompt_catalog.py -q` — 8 passed.
- Affected behavior suite excluding the known legacy body-fetch database-isolation tests — 356
  passed with 18 existing Starlette/httpx deprecation warnings.
- `make lint` — passed, including Ruff, formatting, vulture, ESLint, Prettier, and dead-code checks.
- `make typecheck` — passed, including mypy, ty, pyrefly, and frontend type checking.
- A wider 408-test affected-file run had 404 passes and four failures in
  `backend/tests/test_body_fetch.py`; those legacy tests pass `tmp_path` as a database path despite
  the PostgreSQL-only test environment, causing parallel workers to collide on shared constraints
  and article URLs. The failures are unrelated to this review patch and remain for Task 6 or a
  dedicated test-isolation fix.
