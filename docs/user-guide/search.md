# Search

News Dashboard includes full-text search across your article corpus so you can
find articles by keyword, topic, or phrase.

## What you can search

The search index includes:

- **Title** — the article headline
- **Summary** — the first 280 characters of the feed description (HTML stripped)
- **Reason** — the contextual blurb (e.g., "New release vX.Y.Z from source.")
- **Tags** — any tags you've applied to articles
- **Source name** — the human-readable name of the source (e.g., "Hugging Face Blog")
- **Body** — the full article text (if the full-text extraction feature is enabled; see note below)

By default, search operates on title, summary, reason, tags, and source name.
If you have enabled full-text extraction (via the `FULL_TEXT_ENABLED` setting or
equivalent), the article body is also indexed.

## How search works

Behind the scenes, News Dashboard uses PostgreSQL's built-in full-text search
(`tsvector` column and `GIN` index). When you type a query:

1. The app parses your input into search terms
2. It constructs a `tsquery` using the `&` (AND) operator by default — meaning
   all terms must appear in the document
3. The database returns matching articles ranked by relevance (ts_rank)
4. The UI displays results with the matching terms highlighted

You can refine your search with:
- **Exact phrases**: `"exact phrase"` (requires full-text to be enabled)
- **Wildcards**: `prefix*` (matches any word starting with prefix)
- **OR logic**: `term1 | term2` (matches articles with either term)

## Where to search

Click the search icon in the top navigation bar or press `/` anywhere in the
app to focus the search box. As you type, results appear instantly below the
input.

Results show:
- Article title
- Summary snippet with matches highlighted
- Source name and category
- Article status (new/read/saved/skipped/archived)
- Publication date

Click any result to open the article in the main view.

## Saved Views

Use **Save view** on the Search page to store the current query and filters as a
manual preset. Saved views are private to your account. Selecting one replaces
the current Search URL parameters, so results refresh through the same search
path as ordinary filters.

Saved views are reusable shortcuts only. They do not send alerts, scheduled
notifications, or email digests.

## Search scope

Search looks across **all articles in your database**, regardless of:
- Workflow state (new, read, saved, skipped, archived, starred, snoozed)
- Category or source
- Date (unless you include date-specific terms in your query)

If you want to limit results to a specific state, use the filters in conjunction
with search (e.g., open the Saved tab, then search within saved articles).

## Keeping search relevant

Because the search index is built from the article metadata you already have:

- No extra ingestion steps are required — search works on existing articles
- The index updates automatically when:
  - New articles are ingested
  - You add or remove tags
  - An article's status changes
- No external services are needed; everything runs inside your PostgreSQL
  instance

## Full-text extraction (optional)

For deeper search, you can enable full-text extraction:

1. Set `FULL_TEXT_ENABLED=true` in your environment
2. The app will download and extract the full article body for saved/read
   articles (using Trafilatura or goose3 under the hood)
3. Extracted text is indexed alongside title/summary/reason/tags/source
4. This enables searching within the article body — useful for finding
   specific mentions inside long-form content

> **Note**: Full-text extraction increases:
> - Database storage (one extra `text` column per article)
> - Ingestion time (HTTP fetch + parsing per article)
> - Index size (larger `tsvector`)

It is off by default to keep the app lightweight and privacy-respecting (no
extra network calls during ingest unless enabled).

## Privacy

Search is 100% local — your query text and article contents never leave your
instance. No telemetry is sent when you search.
