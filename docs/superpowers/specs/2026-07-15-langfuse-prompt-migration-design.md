# Langfuse Prompt Migration Design

## Goal

Move the 19 remaining runtime LLM prompt templates from Python call sites into
Langfuse Prompt Management without making Langfuse a runtime dependency for
otherwise valid installations.

## Scope

The migration covers hardcoded feature prompts used for article extraction and
translation, cluster labels, push copy, quizzes, reading-list summaries,
recaps, recommendations, shares, podcast scripts, lesson artifacts and chat,
and briefing chat. The eight prompts already fetched through `get_prompt()`
remain compatible.

User-provided instructions and retrieved article or lesson content are prompt
inputs, not managed templates. Model selection, temperature, token limits,
tools, and structured-output schemas remain in application code. Prompt
rewriting, experiments, and evaluation-framework work are out of scope.

## Architecture

`news_dashboard.ai_client` remains the only prompt-management boundary. It will
resolve both Langfuse text and chat prompts by name and `production` label,
compile `{{variable}}` placeholders, and return a value containing the compiled
content plus the underlying Langfuse prompt object used for trace linking.

Each feature owns a local fallback with the same logical content and variable
names as its Langfuse prompt. When Langfuse is disabled, unavailable, or lacks a
prompt, the helper compiles that fallback locally. Feature code must not call
the Langfuse SDK directly.

Text prompts are used when the template is a single message. Native chat
prompts are used when system/user boundaries are part of the template's
behavior. Dynamic context construction and conditional sections remain in
Python and are supplied as precomputed variables.

## Runtime Flow

1. A feature builds bounded dynamic inputs such as article text or lesson
   context.
2. It requests a named prompt through the shared helper.
3. The helper fetches the `production` version and compiles variables, or
   compiles the local fallback.
4. The feature passes the compiled text or messages to `chat_create()`.
5. `chat_create()` links the fetched prompt object to the Langfuse generation.

Prompt fetch failure must never prevent the LLM request when a valid fallback
exists. Existing gateway fallback behavior is unchanged.

## Prompt Naming and Variables

Names are lowercase and hyphenated, based on the existing feature trace names.
Variables use Langfuse double-brace syntax. Variables contain request-specific
data only; stable behavioral instructions remain in the managed template.

The production label is explicit at the application boundary. Creating a new
version does not affect production until that version receives the label.

## Deployment and Rollback

An idempotent migration command or script creates the initial prompt versions
in the configured Langfuse project and assigns `production`. It must read
credentials from environment variables and never store or print secrets.

Deployment order is prompts first, application second. Rollback can move the
Langfuse `production` label to an earlier version. Disabling Langfuse credentials
immediately returns every call to its code fallback.

## Verification

Tests cover text and chat prompt fetching, variable compilation, fallback
compilation, fetch failures, and trace linking. Representative feature tests
assert that dynamic inputs reach the compiled prompt without changing response
parsing or schemas.

Before delivery, run `make lint`, `make typecheck`, and the PostgreSQL-backed
suite with `source .env && make test` and parallel query workers disabled as
required by `AGENTS.md`. Verify the created Langfuse prompts through the API
without exposing credentials.

## Acceptance Criteria

- All 19 remaining templates have production-labeled Langfuse prompts.
- All migrated feature calls use the shared prompt-management boundary.
- Langfuse-managed generations link to the exact prompt version.
- Missing or unavailable Langfuse prompts use local fallbacks.
- Existing model configuration and structured-output behavior remain stable.
- Migration and rollback are documented and covered by tests.
