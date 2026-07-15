# Task 6 report: lesson generation graph

Implemented the Learn from Link generation pipeline as a typed LangGraph
`StateGraph` compiled without a checkpointer.

## Behavior preserved

- Fetch remains non-fatal and extraction, synthesis, and citation failures stop
  downstream nodes and retain the existing lesson/generation/run failure records.
- Successful runs retain study artifacts, personal relevance fallback behavior,
  immutable generation history, prompt/model/config metadata, and atomic lesson
  persistence.
- Persistence exceptions still record a failed persistence step and failed run,
  then propagate to the caller.
- The graph invocation propagates the authenticated user and the Langfuse session
  `lesson-run:{run_id}`, with a native `CallbackHandler` when Langfuse is enabled.

## Verification

- The topology test asserts every compiled edge, including all conditional
  success/failure routes, and confirms the graph has no checkpointer.
- Extraction, synthesis, and citation failure tests assert exact durable step
  order/status/error records and prove citation/persistence steps are absent
  after their upstream failures.
- Focused Ruff, mypy, ty, and pyrefly checks pass for the assigned files.
- Focused PostgreSQL lesson tests pass.

Initial implementation: `2a38907a`.
