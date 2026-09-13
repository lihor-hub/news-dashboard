---
title: Search
sidebar_position: 5
---

# Search

Search finds articles available to your account by keyword, then narrows them
with filters. PostgreSQL searches title, summary, reason, tags, source name,
and cached article body text when available.

## Using search

Choose **Search** in navigation, or press `⌘K` / `Ctrl+K` for the command
palette's quick search of up to six articles. Select a result to open it in
the article reader. The Search page shows article titles, summaries, sources,
categories, workflow states, and publication dates.

Search matches word prefixes and requires every searchable word to match:
`postgres index` finds articles containing both prefixes. Tokens shorter than
two characters and standalone numbers are ignored. Quoted phrases, explicit
wildcards, and `OR` expressions are not supported search operators.

## Filters

Filters are stored in the Search URL, so you can bookmark a query and return
to it. Sharing the URL does not grant access to articles outside the other
reader's account.

- **Starred** limits results to your starred articles.
- **Include archived** includes archived articles, which are excluded by
  default. Selecting **Archived** under State also includes them.
- **State** selects Today, Later, Done, Skipped, or Archived.
- **Category** and **Source** narrow the feed selection.
- **Date** chooses any time, today, past week, or past month, based on article
  discovery time rather than publication time.
- **Tag** selects a tag when tags are available.

Multiple choices within a filter group combine with OR; different filter
groups combine with AND. Results load 100 at a time; select **Load more** for
the next page. An empty query lets you browse using just the filters.

## Saved Views

Select **Save view** to name and store the current query and filters. Saved
views are private to your account. Selecting a saved view restores its URL
parameters and refreshes results. These are manual shortcuts; they do not
send alerts, scheduled notifications, or email digests.

## Searching article bodies

Body text joins the index when it has been fetched and cached through the
normal article-reading path. There is no separate body-indexing switch.
An article whose body has not been fetched can still match its metadata.

## Troubleshooting

If an article is missing, clear the filters, check **Include archived**, and
try fewer or longer search words. Verify that its source is still available
to your account. A failed search request is different from an empty result;
retry the request before changing your filters.

## Searching from an MCP client

The read-only MCP server exposes the same user-scoped article search through
`search_news`. Use `list_news_sources` first to discover the subscribed,
enabled source slugs available to your token. Both tools require the `search`
scope and use the user identified by the MCP bearer token; there is no user or
owner argument.

Source discovery is ordered by category, descending priority, name, then slug.
Request 1–25 sources per page (default 25), omitting `cursor` for the first
page. Pass each `next_cursor` back unchanged until it is `null`. The cursor is
a canonical ASCII-decimal string of at most 20 digits; a cursor at or beyond
the end returns an empty terminal page. Source pages use
`{sources, truncated, next_cursor}`. Here, `truncated: true` means the
4,800-byte budget ended the page early, and `next_cursor` resumes at the first
source not returned.

Each discovered source has `slug`, `name`, `category`, and `kind`. Exact slug
and category values are valid `search_news` filters. Sources with invalid
filter-valued slugs or categories are omitted. Display-only name and kind are
capped at 120 characters and may be shortened further when JSON escaping
requires it to stay within the 4,800-byte budget.

`search_news` supports a query plus source, category, date-range, workflow-state,
starred, and archive filters. An empty query returns the filtered recent listing
in the web search's canonical order. Multiple values within a source, category,
or state filter combine with OR; different filter groups combine with AND.

Date ranges use article discovery time, not publication time: `day`, `week`,
and `month` cover the trailing 1, 7, and 30 days. Archived articles are omitted
unless `include_archived` is true or `archived` is explicitly selected as a
state. Workflow state and starred status belong to the authenticated token
owner, so one user's state cannot leak into another user's results.

Page search results with `limit` (1–25, default 10) and numeric `offset`
(0–10,000, default 0); this is separate from the source-discovery cursor.
Queries are limited to 2,000 characters. Source and category filters accept up
to 50 non-empty values of at most 120 characters, and states accept up to 50
values from `today`, `later`, `done`, `skipped`, and `archived`.

Search returns `{articles, truncated}`. Each article includes compact metadata,
its canonical URL when available, a summary, and your state and star value;
article bodies are omitted. Article responses keep only complete records within
the structured-content size budget, so `truncated: true` means the next
complete article did not fit. See
[Configuration → MCP server](../configuration/mcp-server.md) for setup and the
full argument reference.

## Privacy

Keyword search runs in the instance's PostgreSQL database. It does not send
your query to an external search service. Optional analytics events record
feature usage without query text or article contents.
