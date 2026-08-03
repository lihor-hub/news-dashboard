# Search

News Dashboard includes full-text search across your article corpus so you can
find articles by keyword or topic, then narrow the results with filters.

## What you can search

The search index includes:

- **Title** — the article headline
- **Summary** — the first 280 characters of the feed description (HTML stripped)
- **Reason** — the contextual blurb (e.g., "New release vX.Y.Z from source.")
- **Tags** — any tags you've applied to articles
- **Source name** — the human-readable name of the source (e.g., "Hugging Face Blog")
- **Body** — the cached full article text, when it has been fetched for that
  article (there is no separate setting to turn this on or off — the body
  is indexed whenever it's already been captured through the app's normal
  body-fetch path)

## How search works

Behind the scenes, News Dashboard uses PostgreSQL's built-in full-text search
(`tsvector` column and `GIN` index). When you type a query:

1. The app splits your input into alphanumeric tokens (at least 2 characters,
   and not a bare number) and lowercases them
2. It builds a query that requires every token to match as a **prefix**,
   combined with **AND** — e.g. `postgres index` matches articles containing
   both a word starting with "postgres" and a word starting with "index"
3. The database returns matching articles ranked by relevance (`ts_rank_cd`)

Search does not currently support quoted exact phrases, explicit wildcard
characters, or `OR` logic — every word you type narrows the results further.

## Where to search

Click **Search** in the navigation sidebar to open the full Search page, or
press `⌘K` / `Ctrl+K` anywhere in the app to open the command palette, which
includes a quick inline search (showing up to 6 matching articles) alongside
jump-to-view and action shortcuts. Press `?` to see all keyboard shortcuts.

On the Search page, results show:
- Article title
- Summary snippet
- Source name and category
- Article status (today/later/done/skipped/archived)
- Publication date

Click any result to open the article in the main view.

## Filters

The Search page filters are backed by the URL, so a search with filters
applied can be bookmarked or shared:

- **Starred** — only starred articles
- **Include archived** — archived articles are **excluded by default**;
  toggle this on to include them, or pick "Archived" directly under **State**
- **State** — multi-select across today, later, done, skipped, and archived
- **Category** — multi-select by category
- **Source** — multi-select by source
- **Date** — any time, today, past week, or past month
- **Tag** — a single tag

Results load 100 at a time; use **Load more** to fetch additional pages.

## Saved Views

Use **Save view** on the Search page to store the current query and filters as a
manual preset. Saved views are private to your account. Selecting one replaces
the current Search URL parameters, so results refresh through the same search
path as ordinary filters.

Saved views are reusable shortcuts only. They do not send alerts, scheduled
notifications, or email digests.

## Search scope

Search looks across **all articles in your database** by default, regardless
of workflow state, category, or source — narrow the results using the filters
above (e.g. select "Saved" as a state, or a specific source).

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
[Configuration → MCP server](../../website/docs/configuration/mcp-server.md)
for setup and the full argument reference.

## Keeping search relevant

Because the search index is built from article data you already have:

- No extra ingestion steps are required — search works on existing articles
- The index updates automatically when:
  - New articles are ingested
  - You add or remove tags
  - An article's status changes
  - An article's body is fetched and cached
- No external services are needed; everything runs inside your PostgreSQL
  instance

## Privacy

Search queries execute locally in your own PostgreSQL database — your query
text and article contents are never sent to an external service. If you've
opted in to in-app analytics, using search records lightweight usage events
(such as which route or feature was used) to help understand app usage; these
events never include your query text or article contents.
