# Langfuse Prompt Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the 19 remaining runtime feature prompts into Langfuse Prompt Management while preserving offline/local fallback behavior.

**Architecture:** Extend `news_dashboard.ai_client` with one typed resolver for text and chat prompts. Feature modules supply bounded variables and local fallback templates; Langfuse owns production-labeled versions and `chat_create()` links the resolved prompt version to each generation.

**Tech Stack:** Python 3.14, Langfuse Python SDK 4.14+, OpenAI-compatible chat API, pytest, ruff, mypy, ty, pyrefly.

## Global Constraints

- Fetch the explicit Langfuse `production` label.
- Preserve local fallbacks for outages and installations without Langfuse.
- Use native chat prompts where system/user boundaries affect behavior.
- Keep model names, temperatures, token limits, tools, and response schemas in code.
- Keep dynamic context construction and conditional logic in Python.
- Never store or print Langfuse credentials.
- Runtime database behavior remains PostgreSQL-only.

---

### Task 1: Typed text and chat prompt boundary

**Files:**
- Modify: `backend/news_dashboard/ai_client.py`
- Test: `backend/tests/test_ai_client.py`

**Interfaces:**
- Produces: `PromptMessage = dict[str, str]`, `ManagedPrompt(text: str | None, messages: list[PromptMessage] | None, langfuse_prompt: Any | None)`, and `get_prompt(name, fallback, prompt_type="text", label="production", variables=None)`.
- Invariant: exactly one of `text` and `messages` is populated.

- [ ] **Step 1: Write failing resolver tests**

  Add tests that mock `_client()` and assert text prompts fetch with
  `label="production", type="text"`, chat prompts fetch with `type="chat"`, both
  compile variables, and the returned object retains the exact SDK prompt.

- [ ] **Step 2: Write failing fallback and trace tests**

  Cover disabled Langfuse and SDK exceptions for both prompt types. Assert chat
  fallback role/order is preserved and `chat_create()` forwards
  `langfuse_prompt` only when the resolver returned a real SDK prompt.

- [ ] **Step 3: Run the red tests**

  Run: `source .env && pytest backend/tests/test_ai_client.py -q`

  Expected: failures because chat resolution and the new typed result do not exist.

- [ ] **Step 4: Implement the minimal shared boundary**

  Add overload-friendly fallback types, local `{{variable}}` compilation for
  every message, explicit prompt-type fetching, validation of compiled SDK
  output, and warning-plus-fallback behavior. Keep existing text callers source
  compatible through the default `prompt_type="text"`.

- [ ] **Step 5: Run the focused tests and commit**

  Run: `source .env && pytest backend/tests/test_ai_client.py -q`

  Expected: PASS.

  Commit: `feat: support managed chat prompts (#1242)`

---

### Task 2: Article ingestion, extraction, and analysis prompts

**Files:**
- Modify: `backend/news_dashboard/body_fetch.py`
- Modify: `backend/news_dashboard/ingest/service.py`
- Modify: `backend/news_dashboard/insights.py`
- Test: `backend/tests/test_body_fetch.py`
- Test: `backend/tests/test_translation.py`
- Test: `backend/tests/test_media_ingest.py`
- Test: `backend/tests/test_insights.py`

**Interfaces:**
- Consumes: Task 1 `get_prompt()` and `ManagedPrompt`.
- Produces prompts: `ai-body-fetch` (text: `html`), `translate-body` (chat: `from_lang`, `body`), `summarize-media-article` (chat: `title`, `description`, `transcript`), `translate-article` (chat: `title`, `summary`), `topic-cluster-label` (text: `articles_text`).

- [ ] **Step 1: Add failing feature wiring tests**

  Patch each module's prompt resolver and capture `chat_create()` arguments.
  Assert exact prompt name/type/variables, compiled messages, and prompt-version
  link while retaining existing response formats and bounds.

- [ ] **Step 2: Run the red tests**

  Run: `source .env && pytest backend/tests/test_body_fetch.py backend/tests/test_translation.py backend/tests/test_media_ingest.py backend/tests/test_insights.py -q`

  Expected: managed-prompt assertions fail at the hardcoded call sites.

- [ ] **Step 3: Refactor the five call sites**

  Convert stable instructions into Langfuse-compatible fallback templates.
  Pass bounded request data through the variables listed above and pass the
  returned `ManagedPrompt` into `chat_create()`.

- [ ] **Step 4: Run focused tests and commit**

  Run the command from Step 2; expected: PASS.

  Commit: `feat: manage ingestion and analysis prompts (#1242)`

---

### Task 3: Reader-facing utility prompts

**Files:**
- Modify: `backend/news_dashboard/push.py`
- Modify: `backend/news_dashboard/quizzes/service.py`
- Modify: `backend/news_dashboard/reading_list/service.py`
- Modify: `backend/news_dashboard/recaps/narrative.py`
- Modify: `backend/news_dashboard/lesson_recaps/narrative.py`
- Modify: `backend/news_dashboard/recommendations.py`
- Modify: `backend/news_dashboard/shares/service.py`
- Test: `backend/tests/test_push_notifications.py`
- Test: `backend/tests/test_quiz.py`
- Test: `backend/tests/test_reading_list.py`
- Test: `backend/tests/test_recap_narrative.py`
- Test: `backend/tests/test_lesson_recap_narrative.py`
- Test: `backend/tests/test_recommendation_contracts.py`
- Test: `backend/tests/test_article_shares.py`

**Interfaces:**
- Consumes: Task 1 resolver.
- Produces text prompts: `briefing-push-hook`, `recap-push-hook`, `weekly-quiz`, `reading-list-summary`, `weekly-recap-narrative`, `weekly-lesson-recap-narrative`, `recommendation-explanation`, and `share-context`.

- [ ] **Step 1: Add failing prompt-wiring tests**

  Assert the eight exact names and their bounded variables: headline block;
  recap counts/category/streak; article blurbs; reading-list text; precomputed
  recap JSON; article/history fields; and article/note/annotation/interests.

- [ ] **Step 2: Run the red tests**

  Run: `source .env && pytest backend/tests/test_push_notifications.py backend/tests/test_quiz.py backend/tests/test_reading_list.py backend/tests/test_recap_narrative.py backend/tests/test_lesson_recap_narrative.py backend/tests/test_recommendation_contracts.py backend/tests/test_article_shares.py -q`

  Expected: prompt-name/link assertions fail.

- [ ] **Step 3: Refactor the eight call sites**

  Route raw-client calls through `chat_create()` where necessary, retain their
  tags/user attribution/model options, compile the listed variables, and pass
  each managed prompt for trace linking.

- [ ] **Step 4: Run focused tests and commit**

  Run the command from Step 2; expected: PASS.

  Commit: `feat: manage reader utility prompts (#1242)`

---

### Task 4: Podcast, lesson, and briefing chat prompts

**Files:**
- Modify: `backend/news_dashboard/tts.py`
- Modify: `backend/news_dashboard/learn_from_link/service.py`
- Modify: `backend/news_dashboard/briefings/service.py`
- Test: `backend/tests/test_tts.py`
- Test: `backend/tests/test_lesson_slide_deck.py`
- Test: `backend/tests/test_lesson_infographic.py`
- Test: `backend/tests/test_learn_from_link.py`
- Test: `backend/tests/test_briefings_api.py`

**Interfaces:**
- Consumes: Task 1 chat resolver.
- Produces chat prompts: `podcast-script-generation`, `lesson-slide-deck`, `lesson-infographic`, `lesson-chat`, `lesson-relevance`, and `briefing-chat`.

- [ ] **Step 1: Add failing native-chat wiring tests**

  Assert role/order, exact names, and variables. For lesson and briefing chat,
  assert Python inserts bounded history between the compiled system message and
  final user question without moving history into the managed template.

- [ ] **Step 2: Run the red tests**

  Run: `source .env && pytest backend/tests/test_tts.py backend/tests/test_lesson_slide_deck.py backend/tests/test_lesson_infographic.py backend/tests/test_learn_from_link.py backend/tests/test_briefings_api.py -q`

  Expected: native chat-prompt assertions fail.

- [ ] **Step 3: Refactor the six call sites**

  Use native chat fallbacks and compile preformatted content variables. Preserve
  JSON response schemas, parsers, history limits, and current exception behavior.

- [ ] **Step 4: Run focused tests and commit**

  Run the command from Step 2; expected: PASS.

  Commit: `feat: manage lesson and briefing chat prompts (#1242)`

---

### Task 5: Idempotent Langfuse synchronization

**Files:**
- Create: `scripts/sync_langfuse_prompts.py`
- Create: `backend/news_dashboard/prompt_catalog.py`
- Test: `backend/tests/test_prompt_catalog.py`
- Modify: `README.md`

**Interfaces:**
- Produces: immutable prompt catalog entries containing `name`, `type`, `prompt`, and optional commit message; CLI exits nonzero when required credentials or host are absent.
- Consumes: the same fallback templates and names as Tasks 2–4, imported from one catalog rather than duplicated by the script.

- [ ] **Step 1: Add failing catalog and sync tests**

  Assert exactly 19 unique prompt names, valid text/chat shapes, double-brace
  variables, no secrets, and one `create_prompt(..., labels=["production"])`
  call per catalog entry using a mocked Langfuse client.

- [ ] **Step 2: Run the red tests**

  Run: `source .env && pytest backend/tests/test_prompt_catalog.py -q`

  Expected: failure because the catalog and sync command do not exist.

- [ ] **Step 3: Implement catalog and synchronization command**

  Centralize the 19 fallback definitions in `prompt_catalog.py`. Make the script
  initialize the SDK from environment variables, create a new version only when
  content/type differs from the current production version, promote created
  versions with `labels=["production"]`, and print names/versions only.

- [ ] **Step 4: Document operation and rollback**

  Document environment setup, dry verification, sync invocation, production
  label rollback, and disabling Langfuse to use local fallbacks. Never include
  credential examples containing real values.

- [ ] **Step 5: Run focused tests and commit**

  Run: `source .env && pytest backend/tests/test_prompt_catalog.py -q`

  Expected: PASS.

  Commit: `feat: add Langfuse prompt catalog sync (#1242)`

---

### Task 6: External sync, full verification, and delivery

**Files:**
- Modify only files required to fix failures caused by Tasks 1–5.

**Interfaces:**
- Consumes: all preceding tasks.
- Produces: 19 production-labeled prompts in `https://fuse.lihor.ro` and a merge-ready PR.

- [ ] **Step 1: Bootstrap and verify PostgreSQL test infrastructure**

  Run `scripts/bootstrap-worktree.sh` if `.venv`, `.env`, or dependencies are
  missing. Confirm `nd-test-pg` is running and `.env` points both database URLs
  to port `55432` without printing their values.

- [ ] **Step 2: Run repository gates**

  Run: `make lint`

  Run: `make typecheck`

  Run: `export PGOPTIONS='-c max_parallel_workers_per_gather=0'; source .env && make test`

  Expected: all commands exit 0.

- [ ] **Step 3: Synchronize prompts using ephemeral environment values**

  Invoke `scripts/sync_langfuse_prompts.py` with the user-authorized credentials
  in process environment only. Do not echo commands, enable shell tracing, save
  credentials, or include them in logs.

- [ ] **Step 4: Verify Langfuse state**

  Query prompt metadata through the SDK/CLI and assert all 19 names have a
  production version and correct type. Report names and versions only.

- [ ] **Step 5: Review, rebase, push, and merge**

  Review the diff, repair confirmed findings, fetch/rebase `origin/main`, rerun
  affected gates, push without bypassing hooks, open a PR closing #1242, enable
  squash auto-merge, watch required CI, and confirm the issue closes.
