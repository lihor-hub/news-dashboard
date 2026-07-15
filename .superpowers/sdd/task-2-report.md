# Task 2 report

## Status

Implemented and committed-ready.

## Red/green evidence

- Red: focused suite reported 5 expected managed-prompt wiring failures and 99 passes.
- Green: focused suite reported 104 passes and 1 pre-existing deprecation warning.

## Implementation

- `ai-body-fetch`: text prompt with bounded `html`.
- `translate-body`: chat prompt with `from_lang` and `body`.
- `summarize-media-article`: chat prompt with `title`, `description`, and `transcript`.
- `translate-article`: chat prompt with `title` and `summary`.
- `topic-cluster-label`: text prompt with bounded `articles_text`.
- All five calls pass the resolved `ManagedPrompt` to `chat_create()` and use its compiled content.
- Existing models, response formats, temperatures, token limits, input caps, and parsing behavior are preserved.

## Verification

- Owned-file Ruff check: pass.
- Owned-file Ruff format check: pass (7 files already formatted).
- Owned-file strict mypy: pass (7 source files).
- Focused pytest: 104 passed, 1 warning.
- Full pytest: 2588 passed, 6 failed, 5 errors; failures are shared PostgreSQL/concurrent-worktree contamination (`out of shared memory`, duplicate rows) plus unrelated concurrently edited tests.
- Repository-wide lint/typecheck are blocked by concurrent Task 3/4 changes outside Task 2 ownership; Task 2-owned files are clean.

## Concerns

- `.env` cannot safely be sourced as shell because an existing value is interpreted as a command; verification used the repository-supported `dotenv run --` loader without exposing or changing credentials.
- Full-suite failures are not caused by Task 2; the focused Task 2 suite is green after the full-suite attempt.

## Review fix verification

- Added an explicit `label="production"` to all five Task 2 `get_prompt()` calls.
- Added an explicit `prompt_type="text"` to `ai-body-fetch` and `topic-cluster-label`; the three chat prompts retain explicit `prompt_type="chat"`.
- Strengthened all five regression tests to assert the exact prompt name, fallback, type, label, and variables.
- Red: the five exact-call tests failed because the new explicit arguments were absent.
- Green: the five exact-call tests passed.
- Focused Task 2 pytest: 104 passed, 1 pre-existing Starlette deprecation warning.
- Owned-file Ruff check: pass.
- Owned-file Ruff format check: pass (7 files already formatted).
- Owned-source strict mypy: pass (3 source files).
