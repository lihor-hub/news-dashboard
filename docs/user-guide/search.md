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
