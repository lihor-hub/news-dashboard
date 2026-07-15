# LangChain, LangGraph, and Langfuse Sessions Design

## Goal

Adopt vanilla LangChain and LangGraph across the existing AI backend according to each flow's orchestration needs, while grouping related traces into native Langfuse sessions. Preserve public APIs, persistence, error behavior, retries, prompt management, and feedback trace IDs.

## Framework boundaries

Use LangChain for conversational and composable LLM operations: Ask AI, briefing chat, lesson chat, prompt-to-model pipelines, and structured output parsing. Use LangGraph for workflows that already have explicit stages, branching, retries, or durable run records: briefing generation, lesson generation, and agent-action planning/execution.

Keep native provider clients for embeddings, TTS, image generation, and isolated atomic calls where a chain or graph would add no orchestration or observability value. The migration must not route these operations through LangGraph merely for uniformity.

Application code will use the frameworks and Langfuse integration directly. It will not introduce a project-owned chain, graph, callback, or tracing abstraction.

## Dependencies and configuration

Add compatible runtime floors for `langchain-core`, `langchain-openai`, and `langgraph`, and regenerate `uv.lock`. Existing OpenAI-compatible configuration remains authoritative: the free-model API key, base URL, model environment variables, request timeout, and fallback behavior must keep their current semantics.

Langfuse remains optional at runtime. When both Langfuse keys are configured, each framework invocation uses `langfuse.langchain.CallbackHandler` and a `langfuse.propagate_attributes(...)` scope. Without both keys, workflows run normally without a callback and without importing or initializing tracing unnecessarily.

## Session model

Session IDs are stable US-ASCII strings shorter than 200 characters:

- Ask AI: an optional client-provided `session_id`; omitted requests remain independent traces.
- Briefing conversation: `briefing:{user_id}:{briefing_id}`.
- Lesson conversation and related lesson work: `lesson:{user_id}:{lesson_id}`.
- Briefing generation: `briefing-run:{run_id}`.
- Lesson generation: `lesson-run:{run_id}`.
- Agent action lifecycle: `agent-action:{run_id}`.

All traced framework invocations propagate the authenticated user ID where available, a descriptive trace name, existing feature tags, and framework metadata. A session groups related traces; it does not replace the trace-per-request or trace-per-operation model.

`POST /api/ask` gains an optional `session_id` field. Existing clients remain compatible. The value must be an ASCII string of at most 199 characters; blank strings are treated as absent. Invalid values receive normal request validation errors rather than being silently truncated.

## LangChain flows

Chat flows construct framework messages from the existing system prompt, supplied history, and current user message. Their return values remain plain strings. Existing grounding context limits and ordering remain unchanged.

Structured generation flows use prompt templates, `ChatOpenAI`, and structured output or explicit parsers while preserving existing validation functions as the final domain boundary. Provider-specific response objects must not leak into service interfaces.

Ask AI continues to return its current answer, citations, and Langfuse trace ID contract. Feedback remains attachable to the returned root trace.

## LangGraph workflows

Each graph state contains only the values needed by subsequent nodes plus the durable database run ID. Nodes call the existing focused domain functions where possible. Graph topology mirrors current control flow rather than redesigning product behavior.

Briefing generation retains candidate selection, deterministic theme clustering, drafting with bounded exponential retry, citation validation, and persistence. Lesson generation retains fetch, extraction, synthesis, citation verification, personal relevance, and persistence. Agent actions retain planning, approval/cancellation boundaries, execution, and durable status transitions.

Existing run and step tables remain the source of truth for product-visible workflow history. LangGraph checkpoints are not introduced in this change; adding a second persistence mechanism would create conflicting recovery semantics. Existing idempotency and stale-run recovery stay intact.

## Errors and compatibility

Domain exceptions, HTTP status codes, response schemas, database status transitions, retry counts, and fallback behavior must remain unchanged. Framework exceptions are translated at existing service boundaries. Langfuse failures are non-fatal and never prevent an AI workflow from completing.

The migration must not add SQLite logic or generic database support. All runtime persistence remains PostgreSQL-specific.

## Testing

Use red-green-refactor for each migration slice. Focused tests cover optional Ask AI sessions, native Langfuse callback and attribute propagation, LangChain message/history parity, structured result validation, LangGraph node order and branch behavior, retry/failure transitions, and preservation of root trace IDs for feedback.

Run the affected tests after every slice, then run `make lint`, `make typecheck`, and `source .env && make test` with `PGOPTIONS='-c max_parallel_workers_per_gather=0'`. PostgreSQL tests must use the dedicated `nd-test-pg` instance on port 55432.

## Delivery

Ship the migration as one issue and one pull request. Keep commits organized by independently testable migration slice, rebase on `origin/main` before pushing, enable squash auto-merge, repair branch-caused CI failures, and confirm the required checks and merge complete.
