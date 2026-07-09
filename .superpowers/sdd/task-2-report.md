# Task 2 Report: Extract Article Content Into Lessons

## Scope

Implemented issue #1137's synchronous backend extraction slice for Learn from Link.
This task updates lesson creation so backend rows move from the initial shell insert
to either `complete` or `failed` within the same request, while keeping tests fully
offline by patching metadata/body helpers.

## TDD Notes

### RED

Command run:

```bash
PATH="$PWD/.venv/bin:$PATH" pytest backend/tests/test_learn_from_link.py -q
```

Observed failure summary:

- `test_create_lesson_completes_with_extracted_content`
- `test_create_lesson_marks_failed_when_extraction_fails`
- `test_create_lesson_ignores_metadata_failure_when_body_succeeds`
- `test_create_lesson_duplicate_resets_pending_state`
- `test_create_lesson_endpoint_returns_completed_lesson`
- `test_create_lesson_endpoint_returns_failed_lesson_on_extraction_error`

All six failed because Task 1 still returned lessons with `generation_status == "pending"`.

### GREEN

Commands run:

```bash
PATH="$PWD/.venv/bin:$PATH" ruff check backend/news_dashboard/learn_from_link/service.py backend/tests/test_learn_from_link.py
PATH="$PWD/.venv/bin:$PATH" pytest backend/tests/test_learn_from_link.py -q
```

Results:

- `ruff check`: passed
- `pytest backend/tests/test_learn_from_link.py -q`: `11 passed, 18 warnings in 4.74s`

## Implementation Summary

- Extended `create_lesson(..., extract=True)` to insert the canonical lesson row
  and synchronously call extraction by default.
- Added `generate_lesson_from_url(...)` to load the lesson, fetch metadata,
  extract readable body text, and persist either success or failure.
- Reused `reading_list.metadata.fetch_url_metadata` and `body_fetch.extract_body`.
- Metadata fetch exceptions are logged and ignored when body extraction succeeds.
- Extraction errors or empty extraction results persist a `failed` lesson with
  `generation_error = "Could not extract readable article content."`
- Added focused service/API tests for success, failure, metadata fallback, and
  duplicate re-generation behavior.

## Notes

- I did not run the full backend suite because the branch brief called out
  unrelated pre-existing failures on `origin/main`.
- I left unrelated untracked `.superpowers/` and `docs/superpowers/plans/`
  artifacts untouched.
