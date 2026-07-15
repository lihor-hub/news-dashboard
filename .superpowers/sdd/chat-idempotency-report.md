# Chat prompt synchronization idempotency report

## Status

Fixed live-discovered Langfuse chat prompt synchronization churn. SDK chat messages carrying
`type="text"` now compare against catalog messages by their supported semantic fields without
creating duplicate production versions.

## TDD evidence

- RED: the realistic SDK regression recreated all 9 chat prompts while leaving text prompts
  unchanged.
- GREEN: `backend/tests/test_prompt_catalog.py` passes with SDK-shaped `role`, `content`, and
  `type="text"` messages.
- Contract coverage confirms that prompt type, role, content, and message order remain exact;
  unsupported message types and malformed message dictionaries safely compare as changed.

## Implementation

- Chat comparison validates that the SDK value is a list of message mappings.
- Each supported message may contain only `role`, `content`, and the SDK's optional `type` field;
  `role` and `content` must be strings, and `type` must be `text` when present.
- The comparison removes only the validated SDK representation detail (`type="text"`) before
  comparing the ordered role/content message list with the catalog fallback.
- Text prompt comparison and production prompt type comparison are unchanged.

## Verification

- `dotenv run -- .venv/bin/pytest backend/tests/test_prompt_catalog.py -q` — 9 passed.
- `dotenv run -- .venv/bin/pytest backend/tests/test_prompt_catalog.py backend/tests/test_ai_client.py -q`
  with parallel PostgreSQL workers disabled — 40 passed.
- `make lint` — passed.
- `make typecheck` — passed (mypy, ty, pyrefly, and frontend typecheck).
- Direct Ruff lint and format checks for the synchronization script and catalog tests — passed.
- `git diff --check` — passed.

## Concerns

None. Unknown future message fields intentionally compare as changed instead of being silently
discarded, preserving the synchronization command's safe failure behavior.
