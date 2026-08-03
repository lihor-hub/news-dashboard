# Secure FastMCP Article Retrieval Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task.

**Goal:** Add a read-scoped `get_news_article` FastMCP tool that returns one visible article with sanitized, schema-valid bounded content, closing #1369.

**Architecture:** Reuse `body_fetch.fetch_and_cache_body(article_id, user_id=token_owner)`, the browser reader's canonical visibility/extraction boundary. Missing and unauthorized IDs share one structured sentinel. The MCP adapter converts hostile stored content to escaped plain text and shrinks complete required-field records under the existing 4,800-byte structured ceiling before the 16 KiB transport defense.

## Global constraints

- PostgreSQL/psycopg runtime only; no direct or unscoped MCP article query.
- Identity comes only from the verified token; the tool requires `read` and is hidden otherwise.
- Missing, foreign-private, disabled-subscription, and share-only articles are indistinguishable.
- No raw HTML, extraction internals, bodies in logs, mutation, SQL/shell/filesystem, or Keycloak coupling.
- Preserve A2A behavior and the existing shared token family/scope separation.
- Add behavior tests and record RED before implementation.

### Task 1: Add typed canonical article retrieval

**Files:** `backend/news_dashboard/mcp/models.py`, `backend/news_dashboard/mcp/server.py`, `backend/tests/test_mcp.py`

- [ ] Add official-client RED tests for read-scope discovery, visible cached global/owned-private success, foreign/disabled/share-only/missing identical sentinel, extraction invocation with token owner, extraction-error behavior, strict positive BIGINT ID validation, and no user-state mutation.
- [ ] Add strict `PositiveArticleId` and a required-key schema: `{found, article, truncated}` with article metadata, summary, body, and `body_truncated`.
- [ ] Register only `get_news_article(article_id)` with `require_scopes("read")`; call `fetch_and_cache_body(..., user_id=_current_user_id())`; never perform a second existence lookup.
- [ ] Serialize timestamps consistently, prefer canonical URL, and omit raw/internal fields.
- [ ] Run focused MCP/A2A/auth tests, lint, and type checks; commit `feat(mcp): add secure article retrieval`.

### Task 2: Sanitize and bound hostile content

**Files:** `backend/news_dashboard/mcp/server.py`, `backend/tests/test_mcp.py`

- [ ] Add RED tests for script/event markup, entity-encoded tags, malformed HTML, embedded tool instructions, oversized body/metadata, multibyte/escaping boundaries, schema decoding, inner 4,800-byte and outer 16 KiB limits.
- [ ] Normalize title/summary/body with the canonical cleaner followed by HTML escaping; return escaped plain text, not HTML or Markdown.
- [ ] Add UTF-8-safe field caps and deterministic whole-object reduction. Preserve every required key; set `body_truncated` when body shrinks and result `truncated` when any field shrinks.
- [ ] Keep extraction failure as `found=true` with empty body and no provider diagnostic.
- [ ] Run full MCP tests, lint, and type checks; commit `fix(mcp): bound and sanitize article content`.

### Task 3: Prove authorization, telemetry, and publish docs

**Files:** `backend/tests/test_mcp.py`, `website/docs/configuration/mcp-server.md`, `website/docs/api/integrations.md`, `website/docs/api/authentication.md`, relevant repository mirrors if present

- [ ] Test search/ask-only denial, revoked-token 401, rate/response middleware compatibility, identical safe misses, sanitized internal failures, and DEBUG-level metadata-only logs excluding token, ID, URL, title, summary, body, and extraction detail.
- [ ] Document tool/scope/input/result fields, not-found sentinel, visibility boundary, escaped plain text, cache-only extraction side effect, truncation flags, revocation, and no mutation/internals.
- [ ] Keep source search, briefings, and Ask AI planned until their issues merge; clarify A2A `ask` versus MCP `read` without changing A2A behavior.
- [ ] Update required docs mirrors, build Docusaurus, and scan stale article-retrieval wording.
- [ ] Run MCP/A2A tests, lint, and type checks; commit `docs(mcp): document secure article retrieval`.

### Task 4: Review and publish #1369

- [ ] Run lint, typecheck, full PostgreSQL-backed `make test`, docs build, lock/audits, stale, artifact, secret, and diff checks.
- [ ] Independently review every task and the complete branch; resolve all Critical/Important findings through fix/re-review.
- [ ] Rebase onto current `origin/main`, rerun affected gates, push, open a PR with `Closes #1369`, enable squash auto-merge, monitor CI, and confirm issue closure.
