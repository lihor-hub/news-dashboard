---
title: MCP server
sidebar_position: 5
---

# MCP server

News Dashboard exposes a read-only [Model Context Protocol](https://modelcontextprotocol.io/docs/getting-started/intro) server at `/mcp`. MCP-aware AI clients connect with stateless Streamable HTTP and see only news visible to the token owner.

The server is enabled by default. To shut down MCP access and block creation of new MCP tokens, set:

```bash
MCP_SERVER_ENABLED=false
```

The explicit values `false`, `0`, `no`, and `off` disable it. Leaving the variable unset keeps it enabled.

## Create a token

A signed-in user can create a token from **Settings → MCP Client Access**, choosing the least set of scopes the client needs. Tokens can also be created through the session-authenticated API:

```bash
curl -X POST https://your-instance/api/users/me/mcp-tokens \
  -H 'Content-Type: application/json' \
  --cookie "nd_session=$SESSION_COOKIE" \
  -d '{"name": "MCP client", "scopes": ["search"]}'
```

The plaintext `ndmcp_` token appears once. News Dashboard stores only its SHA-256 hash and a short display prefix. Each user can hold up to 10 active tokens and can revoke one immediately from Settings or `DELETE /api/users/me/mcp-tokens/{token_id}`.

Available token scopes are `search`, `read`, `ask`, and `briefings`. Omitting `scopes` grants all four; prefer an explicit subset. News discovery and search tools require `search`; `get_news_article` requires `read`; `ask_news` requires `ask`; saved-briefing tools require `briefings`.

MCP authentication is independent of Keycloak and browser login. The bearer token alone identifies the MCP user; clients never send a user ID as a tool argument.

## Connect a client

Configure the MCP client with:

- URL: `https://your-instance/mcp/`
- Transport: Streamable HTTP
- Header: `Authorization: Bearer <your ndmcp_ token>`

Use HTTPS outside a trusted local development environment. Do not put the token in a URL, command history, or logs. There is no stdio adapter or sidecar service.

## Available tools

| Tool | Scope | Description |
|------|-------|-------------|
| `list_latest_news` | `search` | Lists recent articles visible to the token owner. Supports source, category, state, archive, and date-range filters. |
| `list_news_sources` | `search` | Pages through the token owner's subscribed, enabled sources that can be used with `search_news`. |
| `search_news` | `search` | Searches visible articles with typed filters and offset pagination. An empty query returns a filtered recent listing. |
| `get_news_article` | `read` | Retrieves one visible article by its positive integer article ID. |
| `ask_news` | `ask` | Answers a question from a bounded, user-visible news corpus and returns validated citations. |
| `list_briefings` | `briefings` | Pages through complete saved briefings owned by the token user. |
| `get_briefing` | `briefings` | Retrieves one complete saved briefing owned by the token user, including safe visible citations. |

Use `list_news_sources` before filtering by source. It returns only sources that are both subscribed and enabled for the authenticated user, in deterministic category, descending priority, name, then slug order. Sources whose exact slug or category is not a valid search filter value are omitted. Each source has `slug`, `name`, `category`, and `kind`; raw feed URLs, ownership identifiers, and internal state are omitted. The exact `slug` and `category` are valid `search_news` filters. Display-only `name` and `kind` values are capped at 120 characters and may be shortened further when JSON escaping requires it to stay within the 4,800-byte budget.

Source discovery accepts `limit` from 1 through 25 (default 25) and an optional `cursor`. Omit the cursor for the first page. A cursor must be a canonical ASCII-decimal string of at most 20 digits: `0` or a non-zero digit followed by digits, with no sign, leading zero, or whitespace. Pass each `next_cursor` back unchanged to fetch the next page, and continue until it is `null`. A cursor at or beyond the end returns the terminal `{sources: [], truncated: false, next_cursor: null}` response.

Every source page uses the `{sources, truncated, next_cursor}` envelope. `truncated: true` means the 4,800-byte structured-content budget ended that page before its requested count; use `next_cursor` to continue without skipping a source. A non-null `next_cursor` with `truncated: false` simply means more sources remain after a full page.

`search_news` accepts these arguments:

| Argument | Type and bounds | Behavior |
|----------|-----------------|----------|
| `q` | string, at most 2,000 characters; default `""` | Full-text query. An empty value returns the filtered recent listing in the web search's canonical order. |
| `sources` | up to 50 non-empty strings, each at most 120 characters | Source slugs from `list_news_sources`. |
| `categories` | up to 50 non-empty strings, each at most 120 characters | Source categories. |
| `date_range` | `all`, `day`, `week`, or `month`; default `all` | Filters by discovery time. `day`, `week`, and `month` cover the trailing 1, 7, and 30 days. |
| `states` | up to 50 values from `today`, `later`, `done`, `skipped`, `archived` | Workflow states belonging to the token owner. |
| `starred_only` | boolean; default `false` | Returns only articles starred by the token owner. |
| `include_archived` | boolean; default `false` | Includes archived articles. Explicitly filtering for the `archived` state overrides the default exclusion. |
| `limit` | integer from 1 through 25; default 10 | Maximum number of articles requested. |
| `offset` | integer from 0 through 10,000; default 0 | Number of matching articles to skip for pagination. |

Values within one filter group combine with OR; separate filter groups combine with AND. Search results contain complete compact records with `id`, `title`, canonical `url`, `source_slug`, `source_name`, `category`, `published_at`, `summary`, the token owner's `state`, and the token owner's `starred` value. They never contain article bodies.

Article-list responses use `{articles, truncated}`. Results accumulate only complete records within a 4,800-byte structured-content budget; `truncated: true` means another complete article did not fit. `search_news` pagination remains numeric: use `offset` from 0 through 10,000 rather than a source cursor. The MCP transport applies a separate 16 KiB response limit.

### Retrieve an article

Call `get_news_article` with one `article_id`: a strict positive integer no larger than PostgreSQL's `BIGINT` maximum (`9223372036854775807`). The result always has these top-level fields:

```json
{
  "found": true,
  "article": {
    "id": 123,
    "title": "Example article",
    "canonical_url": "https://example.com/article",
    "source_slug": "example",
    "source_name": "Example",
    "category": "engineering",
    "kind": "rss",
    "published_at": "2026-08-04T09:00:00+00:00",
    "discovered_at": "2026-08-04T09:05:00+00:00",
    "summary": "Summary text",
    "body": "Article text",
    "body_truncated": false
  },
  "truncated": false
}
```

`published_at` and `discovered_at` can be `null`. Every other article field is present. Title, source labels, category, kind, summary, and body are whitespace-normalized, escaped plain text—not HTML or Markdown. `canonical_url` remains URL data rather than escaped display text.

A missing ID and an article outside the token owner's visibility boundary return the same sentinel, without an existence hint:

```json
{"found": false, "article": null, "truncated": false}
```

The visibility boundary includes private-source ownership and enabled global subscriptions. A private article owned by someone else, an article from a globally disabled subscription, and an article available only through an in-app share are not readable through this tool. Shared content must be read through its separate share capability.

If the visible article has no cached body, retrieval may fetch and populate the internal body cache. It does not change read/starred state, sources, shares, tags, or settings. Extraction failures still return `found: true` with an empty body and do not reveal provider diagnostics, extraction methods, attempts, or stored raw content.

`body_truncated` means the body was shortened. Top-level `truncated` means any returned text field was shortened to keep the complete structured result within its 4,800-byte limit; the outer transport remains capped at 16 KiB. Required fields remain present when truncation occurs.

### Ask a question about news

Call `ask_news` with a non-empty `question` of at most 2,000 characters and optional `corpus`. `corpus` is `saved_and_read` (the default) or `all_visible`. `saved_and_read` is the public API name for the current product's **Starred + Done** set; it does not mean every article ever opened. `all_visible` widens retrieval to all non-archived articles available through the owner's private sources and enabled global-source subscriptions. Neither option includes another user's private sources, disabled subscriptions, archived articles, or share-only access.

The result contains `answer`, `citations`, nullable `trace_id`, and `truncated`. Citation brackets are positions in the authorized retrieval result, not article database IDs. Only canonical positive brackets such as `[1]` can create a citation. News Dashboard validates the corresponding already-authorized source, permits only well-formed HTTP(S) URLs, removes tracking parameters and fragments, and deduplicates by article ID in first-cited order. Unsupported or ambiguous brackets remain answer text but never become authoritative citations.

`trace_id` is a 32-character Langfuse trace ID when tracing is configured and available; otherwise it is `null`. `truncated: true` means the answer or complete citation list was shortened to fit the 4,800-byte structured-result budget. Citation URLs are validated whole and omitted rather than shortened to a different destination.

The instance needs `FREE_LLM_API_KEY` (preferred) or `OPENAI_API_KEY`, plus the corresponding optional base URL. MCP answering backfills at most 16 missing embeddings, retrieves 8 articles, caps answers at 512 model tokens, uses a 20-second provider timeout, and has a 30-second foreground deadline. A timed-out foreground call abandons the waiting thread; the provider timeout and work caps remain the underlying cost bounds.

The dedicated per-token generation bucket permits a burst of 2 and refills one request every 30 seconds. This is separate from the general MCP limit. Stable errors are:

| Code | Stable public message | Retry guidance |
|------|-----------------------|----------------|
| `ask_not_configured` | `News answering is not configured.` | Configure AI credentials; do not retry unchanged. |
| `embedding_unavailable` | `News retrieval is temporarily unavailable.` | Retry with backoff. |
| `provider_authentication_failed` | `News answering provider authentication failed.` | Repair provider credentials; do not retry unchanged. |
| `provider_rate_limited` | `News answering provider is rate limited; retry later.` | Retry with provider-aware backoff. |
| `ask_timeout` | `News answering timed out; retry later.` | Retry with backoff. |
| `ask_rate_limited` | `News answering rate limit exceeded; retry later.` | Wait at least 30 seconds before retrying. |
| `ask_unavailable` | `News answering is temporarily unavailable.` | Retry with backoff. |

When Langfuse is enabled, MCP Ask traces contain operational metadata only: authenticated user attribution, surface and corpus tags, model, token usage, provider-reported cost, character and citation counts, timing, and status. They exclude bearer tokens, questions, article text, prompts, source titles/URLs, generated answers, provider response bodies, and exception details. Application logs follow the same content-free boundary.

MCP `ask_news` and the optional A2A endpoint can share an `ask`-scoped token, but their routes and flags are independent. `/mcp/` follows `MCP_SERVER_ENABLED`; the A2A agent card and `/api/a2a` require `A2A_SERVER_ENABLED=true`. Enabling either does not enable the other. A2A retains its canonical Starred + Done corpus and does not expose MCP's `corpus` selector.

### Saved briefings

`list_briefings` accepts an integer `limit` from 1 through 25 (default 10) and an integer `offset` from 0 through 10,000 (default 0). Values outside these ranges, booleans, and non-integers are rejected. Results contain only the authenticated token owner's saved briefings whose status is complete, ordered newest first by creation time and then descending briefing ID.

The response has this exact shape:

```text
{
  briefings: [{
    id: integer,
    title: string,
    summary: string,
    scope: string,
    since_at: datetime | null,
    until_at: datetime | null,
    created_at: datetime
  }],
  next_offset: integer | null,
  truncated: boolean
}
```

The server reads one lookahead row to determine whether another page exists but never returns that row. When more data exists, `next_offset` points to the first database row not returned. This also applies when the 4,800-byte structured-content budget ends a page early, so continuing from `next_offset` does not skip a briefing. `next_offset: null` marks the terminal page. `truncated: true` means a field or complete record was shortened or omitted to satisfy output bounds; it is independent of whether another normal page exists.

`get_briefing` accepts one strict positive integer, `briefing_id`. A missing ID, an incomplete briefing, and another user's briefing all produce the same safe `Briefing not found` error. A successful response has this exact shape:

```text
{
  briefing: {
    id: integer,
    title: string,
    summary: string,
    scope: string,
    since_at: datetime | null,
    until_at: datetime | null,
    created_at: datetime,
    content: {
      sections: [{title: string, body: string, citations: [integer]}],
      worth_opening: [integer]
    },
    citations: [{
      article_id: integer,
      title: string,
      source: string,
      url: string,
      section_index: integer | null,
      citation_index: integer | null
    }],
    content_truncated: boolean,
    omitted_sections: integer,
    omitted_citations: integer
  },
  truncated: boolean
}
```

Briefing strings and collections are bounded: title 240 characters, summary 800, saved time-window `scope` 80, section title 200, section body 1,500, citation source 120, and citation URL 2,048 bytes; at most 12 sections, 25 citations, and 25 `worth_opening` IDs are considered. Whole sections and citations are packed within 4,800 structured-content bytes; partial objects are never emitted. `content_truncated` and the outer `truncated` indicate degraded, shortened, or omitted briefing data. `omitted_sections` and `omitted_citations` count material excluded because it was malformed, invisible, invalid, over a collection bound, or over the byte budget.

Citation access is evaluated when the briefing is read, not frozen when it was saved. A citation remains available only if its article is still visible to the token owner: global sources must still be enabled and subscribed, and private sources must belong to that user. Links must normalize to a valid HTTP or HTTPS URL with a valid host and no embedded credentials. Invalid, deleted, disabled, unsubscribed, foreign, duplicate, and dangling citations are omitted; their IDs are also removed from section citation lists and `worth_opening`. Malformed legacy briefing content degrades to safe typed empty or filtered content with truncation and omission metadata instead of exposing stored data or returning an internal error.

The briefing tools only read previously saved results. They cannot generate or regenerate a briefing, mutate content, chat with a briefing, send email, create a podcast, change a schedule, trigger delivery, or inspect or start agent runs. Internal fields such as owner, status, model, errors, prompts, scripts, delivery data, trace IDs, workflow state, article bodies, and source ownership are not returned.

MCP clients should use tool discovery rather than assuming a deployment exposes every tool. The separately configured A2A endpoint remains ask-only and does not advertise briefing tools.

## Security boundaries

- Tokens are individually scoped and revocable; revoked tokens stop authenticating immediately.
- Rate limits use an opaque, process-local token-instance identity, never the bearer value or a reusable database row ID.
- Logs contain tool name, status, and duration metadata only. They exclude tokens, arguments, article content, prompts, and answers.
- Internal failures return a generic error without tracebacks, database details, or provider details.
- Tools cannot run SQL, shell commands, or file-system operations and cannot read secrets.
- Mutation tools are absent. MCP access cannot change article state, sources, shares, or settings.
- Private-source visibility is enforced for the authenticated token owner.
- Article misses do not distinguish absent IDs from unauthorized IDs.
