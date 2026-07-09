# Task 1 Report: Persist Canonical Lesson Records

## Status

Implemented the canonical backend lesson persistence artifact for issue #1136 without touching frontend code or later-task extraction/status-transition behavior.

## Scope Completed

- Added the new `learn_from_link` backend feature package:
  - `backend/news_dashboard/learn_from_link/__init__.py`
  - `backend/news_dashboard/learn_from_link/models.py`
  - `backend/news_dashboard/learn_from_link/service.py`
  - `backend/news_dashboard/learn_from_link/router.py`
- Extended PostgreSQL schema initialization in `backend/news_dashboard/db.py` with the new `lessons` table and index.
- Mounted the new router from `backend/news_dashboard/main.py`.
- Added focused backend tests in `backend/tests/test_learn_from_link.py`.

## TDD Log

### RED test authoring

Wrote failing tests first in `backend/tests/test_learn_from_link.py` covering:

- `service.create_lesson(...)` persists a pending lesson record
- unsafe URLs raise `service.LessonUrlError`
- `service.get_lesson(...)` is user-scoped
- duplicate normalized URLs reset `generation_status` to `pending` and clear `generation_error`
- `POST /api/learn/lessons` creates a lesson
- `POST /api/learn/lessons` returns `400` for unsafe URLs
- `GET /api/learn/lessons/{id}` returns the user-owned lesson
- `GET /api/learn/lessons/{id}` returns `404` for another user's lesson

### RED command

Requested command from brief:

```bash
PATH="$PWD/.venv/bin:$PATH" source .env && pytest backend/tests/test_learn_from_link.py -q
```

Observed local shell issue before test collection:

```text
.env:11: command not found: jure
```

The repo `.env` contains `SMTP_PASSWORD` with spaces, which `zsh` could not `source` directly as shell syntax.

Adjusted focused command to load only the needed DB vars from `.env` while preserving the same pytest target:

```bash
DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' .env)" \
TEST_DATABASE_URL="$(sed -n 's/^TEST_DATABASE_URL=//p' .env)" \
PATH="$PWD/.venv/bin:$PATH" \
pytest backend/tests/test_learn_from_link.py -q
```

RED output:

```text
ImportError while importing test module 'backend/tests/test_learn_from_link.py'
E   ModuleNotFoundError: No module named 'news_dashboard.learn_from_link'
```

This was the expected functional RED state: the package/route did not exist yet.

### Implementation

Implemented the minimal backend slice only:

- `LessonCreateRequest` request model
- `LessonUrlError`
- `create_lesson(...)`
- `get_lesson(...)`
- safe-URL validation via `validate_server_fetch_url(url)`
- canonical URL normalization using `normalize_url(url)` plus deterministic query ordering
- Postgres `lessons` table with user-scoped uniqueness on `(user_id, normalized_url)`
- duplicate insert behavior implemented with `ON CONFLICT ... DO UPDATE` resetting:
  - `generation_status = 'pending'`
  - `generation_error = NULL`
  - `updated_at = NOW()`
- `POST /api/learn/lessons`
- `GET /api/learn/lessons/{lesson_id}`

Not implemented, by design:

- extraction of article body/content beyond the placeholder `source_content` field
- background processing/status transitions beyond the pending shell
- frontend UI

### Intermediate RED during GREEN

After the initial implementation, the focused test run exposed one remaining mismatch:

```text
FAILED test_create_lesson_persists_pending_record
FAILED test_create_lesson_endpoint_persists_record
AssertionError:
expected normalized_url == https://example.com/story?a=1&b=2
actual normalized_url   == https://example.com/story?b=2&a=1
```

Fixed by adding deterministic query-param ordering in the lesson service after calling the shared reading-list normalizer.

### GREEN command

```bash
DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' .env)" \
TEST_DATABASE_URL="$(sed -n 's/^TEST_DATABASE_URL=//p' .env)" \
PATH="$PWD/.venv/bin:$PATH" \
pytest backend/tests/test_learn_from_link.py -q
```

GREEN output:

```text
........                                                                 [100%]
8 passed, 18 warnings in 5.19s
```

## Verification

### Lint

```bash
PATH="$PWD/.venv/bin:$PATH" make lint
```

Final result:

```text
ruff check backend
All checks passed!
ruff format --check backend
240 files already formatted
vulture backend backend/vulture_whitelist.py --min-confidence 80
npm run lint --silent
npm run format:check --silent
Checking formatting...
All matched files use Prettier code style!
npm run dead-code --silent
```

### Typecheck

```bash
PATH="$PWD/.venv/bin:$PATH" make typecheck
```

Final result:

```text
mypy backend
Success: no issues found in 240 source files
PYTHONPATH=.:backend ty check backend
All checks passed!
pyrefly check backend
 INFO 0 errors (4 suppressed, 84 warnings not shown)
npm run typecheck --silent
```

### Focused tests

```bash
DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' .env)" \
TEST_DATABASE_URL="$(sed -n 's/^TEST_DATABASE_URL=//p' .env)" \
PATH="$PWD/.venv/bin:$PATH" \
pytest backend/tests/test_learn_from_link.py -q
```

Final result:

```text
........                                                                 [100%]
8 passed, 18 warnings in 5.19s
```

## Files Changed

- `backend/news_dashboard/db.py`
- `backend/news_dashboard/main.py`
- `backend/news_dashboard/learn_from_link/__init__.py`
- `backend/news_dashboard/learn_from_link/models.py`
- `backend/news_dashboard/learn_from_link/service.py`
- `backend/news_dashboard/learn_from_link/router.py`
- `backend/tests/test_learn_from_link.py`

## Self-Review

- The change stays within the task's ownership boundary for backend lesson persistence and its focused tests.
- Runtime SQL is PostgreSQL-only and uses psycopg `%s` placeholders.
- The new API follows the repo's feature-module package pattern and is mounted on the existing authenticated `api` router.
- Duplicate lesson creation is idempotent per user and preserves any existing extracted content while resetting generation state for later workers.
- Test coverage exercises both service and HTTP behavior, including user scoping and unsafe URL rejection.

## Concerns

- The brief's sample expected sorted query parameters in `normalized_url`, while the shared `reading_list.service.normalize_url(...)` preserves input query order. To satisfy the brief and keep reuse of the shared normalizer, the lesson service adds a deterministic query-ordering pass after calling `normalize_url(...)`.
- The exact brief command using `source .env` is not portable against the current local `.env` because one value contains spaces. I used an equivalent focused command that injects only `DATABASE_URL` and `TEST_DATABASE_URL`.

## Commit

Requested commit message:

```text
feat: add learn from link lesson records
```

## Review Fix Follow-Up

### Fixes applied

- Preserved the existing `original_url` when retrying duplicate lesson creation on `(user_id, normalized_url)` conflicts.
- Updated the user-scoping test to use the actual created second user id instead of a hard-coded `2`.

### Command

```bash
DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' .env)" \
TEST_DATABASE_URL="$(sed -n 's/^TEST_DATABASE_URL=//p' .env)" \
PATH="$PWD/.venv/bin:$PATH" \
pytest backend/tests/test_learn_from_link.py -q
```

### Output

Red before the service fix:

```text
FAILED backend/tests/test_learn_from_link.py::test_create_lesson_duplicate_resets_pending_state
AssertionError: assert 'https://example.com/story/' == 'https://example.com/story'
1 failed, 7 passed, 18 warnings in 4.10s
```

Green after the service fix:

```text
........                                                                 [100%]
8 passed, 18 warnings in 4.06s
```

### Files changed

- `backend/news_dashboard/learn_from_link/service.py`
- `backend/tests/test_learn_from_link.py`
