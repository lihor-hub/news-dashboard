# FastMCP Saved Briefings Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task.

**Goal:** Expose complete saved briefings through read-only, owner-scoped FastMCP list/get tools, closing #1368.

**Architecture:** Strengthen the canonical briefing service so ownership/status and cited-article visibility are enforced in PostgreSQL before MCP exposure. Put MCP-only typed normalization and 4,800-byte packing in `mcp.briefings`; register thin `briefings`-scoped tools that offload synchronous reads from the event loop. Malformed stored content degrades safely, and citations/IDs are intersected with currently visible normalized HTTP(S) articles.

## Global constraints

- PostgreSQL/psycopg only; parameterized canonical service queries.
- Token-derived user only; both tools require `briefings` and are hidden otherwise.
- Complete saved rows only; no generation, regeneration, chat, email, podcast, scheduling, delivery, mutation, or agent-run access.
- Missing/foreign IDs are indistinguishable; logs contain no IDs/content/URLs/tokens.
- Preserve current source/search catalog and A2A's separate opt-in `ask` surface.
- Record RED behavior before each implementation slice.

### Task 1: Fix canonical ownership and citation visibility

**Files:** `backend/news_dashboard/briefings/service.py`, `backend/tests/test_briefings_db.py`, optionally `backend/tests/test_briefings_api.py`

- [ ] Add RED tests for deterministic `created_at DESC,id DESC`, owner+complete list/get filtering, pagination, global subscription visibility, owned-vs-foreign private citations, and existing userless background behavior.
- [ ] Add keyword-only status filtering to canonical list/get queries.
- [ ] Make cited-article fetch user-aware with the canonical visible-article SQL; pass user through get/latest readers.
- [ ] Preserve existing API shapes and parameterized psycopg behavior.
- [ ] Run briefing DB/API tests, lint, and typecheck; commit `fix(briefings): enforce citation visibility`.

### Task 2: Build typed safe briefing schemas and packing

**Files:** create `backend/news_dashboard/mcp/briefings.py`, modify `backend/news_dashboard/mcp/models.py`, create `backend/tests/test_mcp_briefings.py`

- [ ] Add pure RED tests for exact allowlists, internal-field omission, datetime serialization, canonical/fallback URL normalization, invalid schemes/hosts/credentials/ports, malformed content, boolean/duplicate citation IDs, invisible/dangling ID removal, field/collection caps, Unicode/escaped 4,800-byte bound, list resume semantics, and typed input bounds.
- [ ] Implement Pydantic summary/detail/content/citation/list/get models; add briefing ID/limit/offset aliases.
- [ ] Normalize malformed JSON to safe typed empty/filtered content; never echo unknown data.
- [ ] Pack complete records/sections/citations within the structured budget, with omission counts and truncation flags; use lookahead-aware next offsets without skipping byte-truncated rows.
- [ ] Run pure/new MCP tests plus existing MCP regressions, lint, and typecheck; commit `feat(mcp): add bounded briefing schemas`.

### Task 3: Register authenticated non-blocking tools

**Files:** `backend/news_dashboard/mcp/server.py`, `backend/tests/test_mcp_briefings.py`, optional A2A regression

- [ ] Add official-client RED tests for scope discovery/direct denial, empty/list/get/pagination, ownership and safe not-found, malformed/invalid citations, structured/wire limits, metadata-only telemetry, heartbeat concurrency, no mutation/generation calls, exact canonical arguments, and A2A/search compatibility.
- [ ] Register async `list_briefings(limit=10,offset=0)` and `get_briefing(briefing_id)` with `require_scopes("briefings")`.
- [ ] Offload synchronous canonical reads with AnyIO; list requests `limit+1`, user ID, and `status="complete"`; get maps missing/foreign to one sanitized error.
- [ ] Run MCP briefing/general/A2A/auth suites, lint, and typecheck; commit `feat(mcp): expose saved briefings`.

### Task 4: Document, verify, review, and publish #1368

**Files:** `website/docs/configuration/mcp-server.md`, `website/docs/api/integrations.md`

- [ ] Document scope, exact inputs/defaults/bounds, schemas, newest-first pagination, complete-only semantics, safe not-found, citation visibility/URL rules, truncation metadata, and explicit non-generation/non-mutation boundary.
- [ ] Keep current source/search tools accurate and MCP Q&A planned; do not advertise briefing tools through A2A.
- [ ] Build docs and scan stale planned/only-search claims.
- [ ] Run lint, typecheck, full guarded test suite, docs build, audits, stale/artifact/secret/diff checks.
- [ ] Independently review each task and whole branch; resolve Critical/Important findings.
- [ ] Rebase current `origin/main`, rerun affected gates/review, push, open `Closes #1368` PR, enable squash auto-merge, monitor CI, and confirm issue closure.
