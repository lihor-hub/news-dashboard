# Task 3 report

## Outcome

Wired the eight reader-facing utility calls to managed prompts through `get_prompt()` and `chat_create()`, passing only the bounded variables specified by the task and linking each completion to its resolved prompt.

## TDD evidence

- RED: focused suite produced 6 expected missing-prompt failures, with 157 tests passing.
- GREEN: focused suite passed serially: 165 passed, 1 pre-existing Starlette deprecation warning.
- Refactor/gates: `make lint`, `make typecheck`, and `git diff --check` passed.

## Notes

- Directly sourcing `.env` is currently unsafe because line 11 contains an unquoted value parsed as shell syntax; tests were run without printing or modifying credentials.
- A parallel focused run exposed an unrelated shared-database duplicate-key collision in an existing quiz test; the required serial rerun passed.
