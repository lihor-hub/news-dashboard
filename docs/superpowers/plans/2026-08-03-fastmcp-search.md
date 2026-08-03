# FastMCP Source Discovery and Search Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task.

**Goal:** Add authenticated, search-scoped `list_news_sources` and `search_news` FastMCP tools that reuse the browser's canonical PostgreSQL source and article-query behavior, closing #1371.

**Architecture:** Extract the existing per-user source-list query from the HTTP router into `sources.service` without changing the HTTP response. Keep `ingest.service.search_articles(..., user_id=...)` as the only search implementation. The MCP adapter supplies identity only from the verified token, publishes strict typed schemas, and accumulates complete compact records into schema-valid bounded envelopes before the outer transport limiter.

**Stacking:** This branch is based on unmerged #1367. Publish it as a stacked PR against `codex/feat-fastmcp-1367`; after #1367 merges, rebase onto `origin/main`, change the PR base to `main`, and rerun required gates.

## Global constraints

- PostgreSQL/psycopg runtime only; no copied MCP-specific SQL search layer.
- Both tools require `search` and are hidden from under-scoped tokens.
- User identity is token-derived; no user/owner argument.
- Preserve A2A imports of MCP validation/auth helpers and all browser HTTP behavior.
- Never return bodies, raw feed URLs, owner IDs, secrets, embeddings, scores, or internal state timestamps.
- Logs remain metadata-only at every level.
- Add behavior tests and record RED before production changes.

### Task 1: Extract the canonical source-list service

**Files:** `backend/news_dashboard/sources/service.py`, `backend/news_dashboard/sources/router.py`, `backend/tests/test_source_subscriptions.py`

- [ ] Add a failing service test covering subscribed/unsubscribed global sources, owned/private isolation, soft deletion, preference metadata, and established ordering.
- [ ] Implement `list_sources_for_user(user_id, *, database_url=None)` with the exact current router SQL and psycopg parameters.
- [ ] Delegate the HTTP route to the service while preserving `{"items": ...}` and inclusive unsubscribed-source behavior.
- [ ] Run focused source/API tests, lint, and type checks; commit `refactor(sources): share per-user source listing`.

### Task 2: Add typed discovery and search tools

**Files:** `backend/news_dashboard/mcp/models.py`, `backend/news_dashboard/mcp/server.py`, `backend/tests/test_mcp.py`

- [ ] Add failing official FastMCP client tests for tool discovery/generated schemas, source visibility, combined filters, empty-query ordering, pagination, invalid bounds, scope denial, private-source isolation, cross-user workflow/star isolation, 25-result cap, and adversarial wire bounds.
- [ ] Add typed constraints: query max 2,000, filter lists max 50 with non-empty 120-character values, workflow-state/date enums, limit `1..25`, and offset `0..10,000`. Preserve `MAX_QUERY_LENGTH` for A2A.
- [ ] Implement search-scoped `list_news_sources() -> {sources,truncated}` from the canonical source service, returning only subscribed/searchable rows and compact `slug,name,category,kind` fields.
- [ ] Implement search-scoped `search_news(...) -> {articles,truncated}` by calling `search_articles` with `_current_user_id()`. Translate MCP `day` to canonical `today`; pass all other typed filters and pagination unchanged.
- [ ] Share a 4,800-byte whole-record accumulator. Compact article fields to `id,title,url,source_slug,source_name,category,published_at,summary,state,starred`, using `canonical_url or url`; preserve schema validity under the 16 KiB transport bound.
- [ ] Tool descriptions document empty-query behavior, OR-within/AND-between filters, discovery-time date windows, archive override semantics, pagination, bounds, and omitted bodies.
- [ ] Run focused MCP/source tests, lint, and type checks; commit `feat(mcp): add source discovery and news search`.

### Task 3: Publish accurate search documentation

**Files:** `website/docs/configuration/mcp-server.md`, `website/docs/api/integrations.md`, `website/docs/user-guide/search.md`

- [ ] Update published tool tables and schemas for the two new tools, scope, filter enums/bounds, empty query, pagination, source/state ownership, canonical URLs, and truncation envelopes.
- [ ] Keep article retrieval, briefings, and Ask AI explicitly planned until their issues merge; remove stale claims that source search is unavailable.
- [ ] Build Docusaurus and scan for stale single-tool/source-search-planned wording.
- [ ] Run focused tests, lint, and type checks; commit `docs(mcp): document source discovery and search`.

### Task 4: Review and publish #1371

- [ ] Run `make lint`, `make typecheck`, full `dotenv run -- make test` with `PGOPTIONS='-c max_parallel_workers_per_gather=0'`, docs build, dependency audits, stale scans, and secret/artifact checks.
- [ ] Run independent task reviews and a whole-branch review; resolve every Critical/Important finding through fix/re-review.
- [ ] Push the stacked branch and open a PR against `codex/feat-fastmcp-1367` with `Closes #1371`, verification evidence, and the required generated-code trailer.
- [ ] After #1367 merges, rebase onto current `origin/main`, change base to `main`, rerun affected gates/review, enable squash auto-merge, monitor CI, and confirm #1371 closes.
