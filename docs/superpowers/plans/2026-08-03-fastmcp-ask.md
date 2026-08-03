# Grounded FastMCP Ask News Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Use the repository Langfuse skill for tracing work.

**Goal:** Add an authenticated, grounded, privacy-preserving `ask_news` FastMCP tool with bounded cost, capacity, citations, tracing, and stable errors, closing #1370.

**Architecture:** Keep `assistant.service.ask -> embeddings.ask` as the only RAG path. Add an optional execution policy so MCP can bound SQL backfill, retrieval, provider timeout, output tokens, and trace content without changing browser/A2A defaults. The async MCP adapter supplies token identity, a typed corpus enum, dedicated opaque-token rate limiting, citation validation over the already-authorized ordered source list, schema-valid response packing, and fixed public errors.

## Global constraints

- PostgreSQL/pgvector canonical retrieval only; no second MCP query or prompt.
- `ask` scope and token-derived identity only; MCP and A2A flags/routes remain independent.
- `saved_and_read` means Starred + Done; `all_visible` means all visible non-archived articles.
- No bearer/question/article/prompt/URL/answer/provider-body content in logs or Langfuse metadata/I/O.
- Preserve cancellation; foreground timeout is paired with provider timeout and bounded spend.
- Record RED before implementation and mock Langfuse locally—never use credentials/data.

### Task 1: Add typed tool shell and canonical call

**Files:** `backend/news_dashboard/mcp/models.py`, `backend/news_dashboard/mcp/server.py`, `backend/tests/test_mcp.py`

- [ ] Add official-client RED tests for ask-only discovery, under-scope hiding/direct denial, generated question/corpus schema, invalid questions, corpus translation, token user ID, and structured success.
- [ ] Add trimmed 1..2,000 question and `saved_and_read|all_visible` corpus aliases.
- [ ] Register async `ask_news` with `require_scopes("ask")`, initially calling only `assistant.service.ask` with `include_all` and token user.
- [ ] Return typed `{answer,citations,trace_id,truncated}` shell; no extra model/prompt/user arguments.
- [ ] Run focused MCP/A2A/auth tests, lint/typecheck; commit `feat(mcp): add ask news tool shell`.

### Task 2: Add bounded canonical execution and privacy tracing

**Files:** `backend/news_dashboard/assistant/service.py`, `backend/news_dashboard/embeddings.py`, `backend/news_dashboard/ai_client.py`, relevant ask/embedding/MCP tests

- [ ] Add RED tests for exact Starred+Done/all-visible cross-user corpus, bounded SQL backfill 16, retrieval 8, answer 512 tokens, provider 20s timeout, and unchanged browser/A2A defaults.
- [ ] Add optional frozen execution policy threaded through canonical service/embed/answer/client calls; `None` preserves existing behavior.
- [ ] MCP policy disables raw trace content, propagates authenticated string user early, tags/metadata only with surface/corpus/character counts, and returns the active 32-hex trace ID.
- [ ] Prove raw question, article text, prompt, URLs, answer, bearer/token identifiers never enter trace attributes/I/O or app logs.
- [ ] Run ask/embedding/MCP/A2A tests, lint/typecheck; commit `feat(ai): bound MCP news answering`.

### Task 3: Validate citations and bound structured results

**Files:** preferably create `backend/news_dashboard/mcp/ask.py`, modify server/tests

- [ ] Add table-driven RED tests for bracket-position parsing, duplicates, invalid/out-of-range references, missing fields/IDs, unsafe/malformed URLs, normalization, invalid trace IDs, oversized answer/titles/URLs, Unicode/escaping, exact 4,800-byte structured and 16 KiB wire bounds.
- [ ] Treat brackets as 1-based positions into the authorized service source list, then dedupe by article ID in first-cited order.
- [ ] Normalize and fail closed to HTTP(S) citations; never invent or trust generated database IDs.
- [ ] Keep complete citation objects and UTF-8-safe answer prefixes within required schema; set truncation flag.
- [ ] Run focused/general MCP tests, lint/typecheck; commit `fix(mcp): validate grounded news answers`.

### Task 4: Add dedicated generation controls and stable errors

**Files:** `backend/news_dashboard/mcp/server.py`, optional `mcp/errors.py`, tests

- [ ] Add deterministic RED tests for ask-only opaque per-token bucket (burst 2, refill 1/30s), identity isolation, LRU 4,096 eviction, non-ask independence, foreground 30s timeout, and provider policy propagation.
- [ ] Add request-specific limiter keyed only by internal `rate_limit_id`; never bearer/public DB token ID.
- [ ] Use AnyIO thread offload with abandonment plus provider timeout and bounded work; preserve cancellation.
- [ ] Map configuration, embedding, provider auth/rate/timeout, dedicated rate, and unexpected failures to fixed allowlisted errors with no exception text; scan fully formatted logs.
- [ ] Run MCP/ask/A2A/auth suites, lint/typecheck; commit `fix(mcp): protect news answering capacity`.

### Task 5: Document, verify, review, and publish #1370

**Files:** `website/docs/configuration/mcp-server.md`, `website/docs/api/integrations.md`, `website/docs/api/authentication.md`, A2A regression/docs only where needed

- [ ] Document signature/corpus semantics, `ask` scope, answer/citations/trace/truncation, AI requirements, fixed limits/errors/retry, privacy boundary, and independent opt-in A2A surface; remove planned-Q&A wording.
- [ ] Prove A2A card/default Starred+Done behavior remains unchanged.
- [ ] Build docs and scan stale claims; run lint/typecheck/full guarded tests/audits/hygiene.
- [ ] Independently review every task and whole branch; resolve Critical/Important findings.
- [ ] Rebase current `origin/main`, rerun affected gates/review, push, open `Closes #1370` PR, enable squash auto-merge, monitor CI, and confirm closure.
