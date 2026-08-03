---
title: Search
sidebar_position: 5
---

# Search

Search finds articles across your corpus by keyword, topic, or phrase. It uses
PostgreSQL full-text search, so queries and article contents stay inside your
instance.

## Indexed fields

The search index includes title, summary, reason, tags, source name, and, when
article body extraction is enabled, extracted body text.

Results are ranked by PostgreSQL relevance and can include articles in any
workflow state: Today, Later, Done, Skipped, Starred, Snoozed, or Archived.

## Using search

Open search from the navigation or focus it with `/`. Results show the title,
summary snippet, source, state, and publication date. Select a result to open
the article in the main view.

If you want to narrow results to a specific state, open that view first and use
the search control there.

## Searching from an MCP client

The read-only MCP server exposes the same user-scoped article search through
`search_news`. Use `list_news_sources` first to discover the subscribed,
enabled source slugs available to your token. Both tools require the `search`
scope and use the user identified by the MCP bearer token; there is no user or
owner argument.

`search_news` supports a query plus source, category, date-range, workflow-state,
starred, and archive filters. An empty query returns the filtered recent listing
in the web search's canonical order. Multiple values within a source, category,
or state filter combine with OR; different filter groups combine with AND.

Date ranges use article discovery time, not publication time: `day`, `week`,
and `month` cover the trailing 1, 7, and 30 days. Archived articles are omitted
unless `include_archived` is true or `archived` is explicitly selected as a
state. Workflow state and starred status belong to the authenticated token
owner, so one user's state cannot leak into another user's results.

Page with `limit` (1–25, default 10) and `offset` (0–10,000, default 0).
Queries are limited to 2,000 characters. Source and category filters accept up
to 50 non-empty values of at most 120 characters, and states accept up to 50
values from `today`, `later`, `done`, `skipped`, and `archived`.

Search returns `{articles, truncated}`. Each article includes compact metadata,
its canonical URL when available, a summary, and your state and star value;
article bodies are omitted. Source discovery returns `{sources, truncated}`
with `slug`, `name`, `category`, and `kind`. Both responses keep only complete
records within the structured-content size budget, so `truncated: true` means
the next complete record did not fit. See
[Configuration → MCP server](../configuration/mcp-server.md) for setup and the
full argument reference.

## Full-text extraction

Deeper body search depends on optional article body extraction. When enabled,
the app fetches and caches article text, then indexes it alongside the normal
metadata fields. This increases storage and ingestion work, so it is kept
optional.
