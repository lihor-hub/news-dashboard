# LangChain, LangGraph, and Langfuse Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate suitable existing AI flows to vanilla LangChain and LangGraph while preserving behavior and grouping related native Langfuse traces into durable sessions.

**Architecture:** LangChain owns model/prompt/message composition, while existing domain parsers and validators remain the output boundary. LangGraph mirrors the existing briefing, lesson, and action workflow stages without a checkpointer; PostgreSQL run records remain authoritative. Application call sites use Langfuse's `CallbackHandler`, root observations, and `propagate_attributes` directly rather than a project tracing wrapper.

**Tech Stack:** Python 3.14, LangChain 1.3, langchain-openai 1.3, LangGraph 1.2, Langfuse 4.14, FastAPI, PostgreSQL, pytest.

## Global Constraints

- Use vanilla framework and Langfuse APIs; do not add project-owned chain, graph, callback, or tracing wrapper abstractions.
- Preserve public HTTP and service return contracts, exceptions, retries, database run/step records, prompt linkage, feedback trace IDs, provider fallback behavior, and behavior without Langfuse credentials.
- Keep native clients for embeddings, TTS, image generation, and non-orchestrated provider operations.
- Runtime SQL remains PostgreSQL-specific with psycopg parameter style.
- Add dependency floors `langchain>=1.3.12`, `langchain-openai>=1.3.5`, and `langgraph>=1.2.9` and regenerate `uv.lock`.
- Langfuse session and user attributes are ASCII strings shorter than 200 characters and are propagated before framework observations are created.

---

### Task 1: Dependencies and direct Langfuse contract

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `backend/tests/test_ai_client.py`
- Modify: `backend/news_dashboard/ai_client.py`

**Interfaces:**
- Consumes: existing `langfuse_enabled`, prompt loading, request timeout, and fallback-client configuration.
- Produces: framework-compatible `ChatOpenAI` construction and response-content normalization used directly by migrated call sites; it must not encapsulate callbacks, chains, graphs, or propagation scopes.

- [ ] Add red tests proving ChatOpenAI receives the configured API key, base URL, model, and timeout; response text normalization accepts string content and rejects unsupported block content; existing free-provider to OpenAI fallback semantics remain observable.
- [ ] Run `source .env && pytest -n 0 backend/tests/test_ai_client.py -q` and confirm failures identify missing framework behavior.
- [ ] Add the dependency floors, run `uv lock`, and implement only provider/model construction and content normalization needed by direct call sites.
- [ ] Re-run `backend/tests/test_ai_client.py`; refactor while green.
- [ ] Commit as `feat: add vanilla LangChain model support`.

### Task 2: Ask AI chain and optional session API

**Files:**
- Modify: `backend/news_dashboard/assistant/models.py`
- Modify: `backend/news_dashboard/assistant/router.py`
- Modify: `backend/news_dashboard/assistant/service.py`
- Modify: `backend/news_dashboard/embeddings.py`
- Modify: `backend/tests/test_embeddings.py`
- Modify: `backend/tests/test_ask_scope.py`
- Modify: `backend/tests/test_feedback_api.py`
- Modify: `backend/tests/test_user_attribution.py`

**Interfaces:**
- Consumes: optional `AskRequest.session_id`, current retrieval/context builders, existing prompt object, model fallback configuration.
- Produces: the unchanged Ask result mapping including answer, sources, and root Langfuse trace ID.

- [ ] Add red tests for absent/backward-compatible session IDs, valid IDs threaded router → service → Ask, invalid non-ASCII/200-character IDs, exact prompt/context behavior, user/session propagation via native Langfuse APIs, and feedback against the returned root trace.
- [ ] Run the four focused files with `pytest -n 0` and confirm expected behavioral failures.
- [ ] Add `session_id: str | None` validation to `AskRequest`; compose the Ask prompt/model/parser with vanilla LangChain; enclose invocation in a native Langfuse root observation and `propagate_attributes` only when enabled; preserve retrieval, fallback, and response mapping.
- [ ] Re-run focused tests and refactor only after green.
- [ ] Commit as `feat: trace Ask AI LangChain sessions`.

### Task 3: Briefing and lesson conversational chains

**Files:**
- Modify: `backend/news_dashboard/briefings/service.py`
- Modify: `backend/news_dashboard/learn_from_link/service.py`
- Modify: `backend/tests/test_briefings_api.py`
- Modify: `backend/tests/test_learn_from_link.py`

**Interfaces:**
- Consumes: existing system prompts, history arrays, grounding context, ownership checks, model configuration.
- Produces: unchanged plain-string chat answers; sessions `briefing:{user_id}:{briefing_id}` and `lesson:{user_id}:{lesson_id}`.

- [ ] Add red tests that capture LangChain messages and assert exact system/history/user order, callback presence only when enabled, direct `propagate_attributes` values, session identity, and unchanged error behavior.
- [ ] Run the two focused test files and verify failures come from the unimplemented chains/sessions.
- [ ] Replace direct chat completion calls with `ChatPromptTemplate`/message invocation and native Langfuse integration at each call site; normalize AI message content without adding a shared tracing wrapper.
- [ ] Re-run focused tests and refactor while green.
- [ ] Commit as `feat: add Langfuse sessions to AI chats`.

### Task 4: Atomic text and structured LangChain migrations

**Files:**
- Modify: `backend/news_dashboard/{body_fetch.py,entities.py,insights.py,perspectives.py,recommendations.py,watchlist_agent.py,prompt_optimizer.py}`
- Modify: `backend/news_dashboard/{ingest/service.py,quizzes/service.py,reading_list/service.py,shares/service.py}`
- Modify: `backend/news_dashboard/{learn_from_link/service.py,lesson_recaps/narrative.py,recaps/narrative.py}`
- Modify: `backend/news_dashboard/{briefings/service.py,push.py,tts.py}` for text-generation portions only
- Modify: corresponding existing `backend/tests/test_*.py` files for each module.

**Interfaces:**
- Consumes: current prompt text, managed Langfuse prompt object, JSON response settings, tags, user/resource IDs, parsers, validators, and native non-chat clients.
- Produces: unchanged domain values and exceptions; resource sessions only where multiple related traces exist, otherwise metadata/tags without artificial sessions.

- [ ] In small module groups, first change tests to capture vanilla runnable/model invocation and assert current prompt/model/temperature/token/JSON semantics plus existing user attribution and prompt linkage.
- [ ] Run each changed test file and observe the expected red failure before touching its production module.
- [ ] Migrate the corresponding production call sites to vanilla LangChain, retaining explicit existing parsing/validation and native clients for embeddings/audio/images/fetching.
- [ ] Run each module's tests green before moving to the next group; preserve free-provider fallback regressions.
- [ ] Commit independently testable groups with `refactor: run <domain> AI through LangChain` messages.

### Task 5: Briefing generation graph

**Files:**
- Modify: `backend/news_dashboard/briefings/service.py`
- Modify: `backend/tests/test_briefings_db.py`
- Modify: `backend/tests/test_briefing_agent.py`

**Interfaces:**
- Consumes: existing stage constants, `AiFn` injection, run ID, candidate/theme/draft/validate/save functions.
- Produces: a compiled no-checkpointer `StateGraph` invoked by `generate_briefing`, session `briefing-run:{run_id}`, and the unchanged result/exception contract.

- [ ] Add red tests proving node order `candidate_selection → theme_clustering → drafting → citation_verification → assembly`, no-candidate termination, bounded drafting retry, downstream-node skipping on failure, five durable step statuses, and session/user propagation.
- [ ] Run focused briefing tests and confirm the graph contract is missing.
- [ ] Introduce a typed briefing state and focused node functions, compile with `StateGraph`, and invoke inside native Langfuse propagation; preserve idempotency before run creation, injected `ai_fn`, backoff, failed briefing rows, root trace ID persistence, and database steps.
- [ ] Re-run focused tests and refactor while green.
- [ ] Commit as `refactor: orchestrate briefing generation with LangGraph`.

### Task 6: Lesson generation graph

**Files:**
- Modify: `backend/news_dashboard/learn_from_link/service.py`
- Modify: `backend/tests/test_learn_from_link.py`
- Modify: `backend/tests/test_learn_from_link_agent_runs.py`

**Interfaces:**
- Consumes: current fetch/extraction/synthesis/citation/personal-relevance/persistence helpers and lesson run ID.
- Produces: a compiled no-checkpointer `StateGraph`, session `lesson-run:{run_id}`, and unchanged lesson result/status records.

- [ ] Add red tests proving node order, downstream skipping at extraction/synthesis/citation failures, exact durable step/run records, user/session propagation, and successful persistence.
- [ ] Run focused lesson tests and confirm the graph behavior is absent.
- [ ] Add typed lesson graph state and nodes that reuse current domain helpers; retain `_fail` behavior, generation history, personal relevance, prompt/model versions, and persistence exception recording.
- [ ] Re-run focused tests and refactor while green.
- [ ] Commit as `refactor: orchestrate lesson generation with LangGraph`.

### Task 7: Agent-action lifecycle graph

**Files:**
- Modify: `backend/news_dashboard/agent_actions.py`
- Modify: `backend/tests/test_agent_actions.py`

**Interfaces:**
- Consumes: planner parsing/validation, allowlists, admin authorization, persisted run/actions, approval/cancel endpoints, tool executor.
- Produces: graph-driven planning and approved execution with session `agent-action:{run_id}` after the run is durably allocated; unchanged API result/status contracts.

- [ ] Add red tests for planning/validation/persistence order, malformed/non-actionable plans persisting nothing, approval boundary, per-step continue-on-error behavior, cancellation, authorization, and callback/session propagation.
- [ ] Run `test_agent_actions.py` and confirm expected graph-contract failures.
- [ ] Allocate the durable run at the latest point that permits a stable session without persisting invalid plans; build typed planning and execution graphs around existing validators/tools and preserve transaction/status behavior.
- [ ] Re-run the focused file and refactor while green.
- [ ] Commit as `refactor: orchestrate agent actions with LangGraph`.

### Task 8: Documentation, review, and full verification

**Files:**
- Modify: `README.md`
- Modify: affected tests/code only for confirmed review findings.

**Interfaces:**
- Consumes: all completed migration slices.
- Produces: operator/developer documentation and a verified PR-ready branch.

- [ ] Add README documentation for framework dependencies, direct Langfuse integration, session meanings, optional Ask session input, and no-checkpointer PostgreSQL workflow persistence.
- [ ] Run one independent code-review pass against `origin/main`; fix only confirmed in-scope findings and re-run their focused tests.
- [ ] Verify `podman ps --filter name=nd-test-pg` and `.env` points both database URLs to port 55432 without printing secrets.
- [ ] Run `make lint`, `make typecheck`, then `export PGOPTIONS='-c max_parallel_workers_per_gather=0'; source .env; make test` and retain fresh successful output.
- [ ] Fetch/rebase `origin/main`; rerun gates if the base changed; push without bypassing hooks; open a PR containing `Closes #1241` and the standard generated trailer; enable squash auto-merge.
- [ ] Watch required checks, repair branch-caused failures, confirm merge and issue closure, and delete the remote branch if GitHub did not.
