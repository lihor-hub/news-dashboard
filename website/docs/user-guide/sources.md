---
title: Sources and subscriptions
sidebar_position: 4
---

# Sources and subscriptions

Sources are the feeds News Dashboard uses to discover articles. Your source
subscription controls which feeds are active for your account.

## Source kinds

| Kind | What it means |
|------|---------------|
| `rss_feed` | A standard RSS or Atom feed. |
| `github_release_feed` | A GitHub releases Atom feed. |
| `trending_feed` | Hacker News or GitHub trending feeds. |
| `scraped_page` | A custom parser for pages that do not expose a suitable feed. |
| `reddit_feed`, `lobsters_feed`, `mastodon_feed` | Community feeds with their own fetchers. |

Default sources cover Python, AI/LLM, agents, cloud infrastructure,
engineering, trending news, and repositories. They are seeded when the instance
is initialized.

## Managing sources

From the Sources page you can enable, disable, add, or remove sources. You can
also inspect health information such as last checked time, last successful
fetch, last error, fetched count, and inserted count.

Choose **Add source** to open **Add private source**. Select RSS Feed, Reddit,
Lobsters, or Mastodon, then enter a name and feed URL. **Test source** previews
entries before you save. You can set a category, optional slug, and high
priority, then choose **Add source**. The new source belongs to your account.
GitHub releases, trending feeds, and custom scrapers also appear among the
instance's predefined sources; they are not choices in this dialog.

Use a source's switch to enable or disable it without removing it. On shared
sources the switch controls your subscription; on your private sources it
controls whether that source is enabled.

### Source health

- **ok:** the most recent successful fetch (or checked time if none succeeded)
  is no more than 48 hours old, with no recorded error.
- **stale:** that timestamp is older than 48 hours, or no fetch is recorded.
- **error:** the last fetch recorded an error; inspect its message.

A source that responds successfully can still return no new articles. Compare
fetched and inserted counts before assuming ingestion failed. For errors,
check the feed URL and use **Test source** when adding a corrected source;
persistent failures may require the instance operator to investigate.

## Import and export OPML

Any signed-in user can move feed subscriptions between readers with OPML.
Open **Feeds → Sources** (`/feeds`); **Import OPML** and **Export OPML** are
in the toolbar above the source list.

To import, choose **Import OPML** and select an `.opml` or `.xml` file exported
from your previous reader. Imported feeds become private RSS sources for your
account. The **OPML Import Result** panel reports how many feeds were **added**,
**skipped**, or **failed**. Expand **Skipped** to see reasons such as duplicates;
failed entries show their feed URL and error so you can correct them and retry.

Choose **Export OPML** to download `subscriptions.opml`. It contains only your
enabled RSS-type (`rss_feed`) sources, including subscribed shared sources and
your enabled private sources. It does not include articles, reading state, or
stars. Other source kinds, including GitHub releases, trending feeds, and
scraped pages, are not covered by OPML.

### Import limits

The server accepts files up to **5 MiB (5,242,880 bytes)** and **1,000 outlines**
by default. Folder outlines count toward the outline limit even when they do
not contain a feed URL. Split larger exports into smaller OPML files and import
them separately.

If a limit is exceeded, the result panel shows **Import failed** followed by
one of these messages (the numbers reflect the server's configured limits):

- `OPML file too large (max 5242880 bytes); split it into smaller files and import them separately`
- `OPML file has too many outlines (1001, max 1000); split it into smaller files`

The size error returns HTTP 413; the outline error returns HTTP 400. Instance
operators can change these limits with the server environment variables
`MAX_OPML_IMPORT_BYTES` (bytes) and `MAX_OPML_IMPORT_OUTLINES` (outline count).

For the import/export endpoints, see the
[Sources and ingestion API reference](../api/sources-and-ingestion.md).

## Noise controls

Broad feeds are capped so one noisy source does not dominate the Today Feed.
Typical caps are 15 to 20 items for broad trending feeds, 5 items for dense
newsletter feeds, and around 50 items for curated blog feeds.

On multi-user instances, source subscriptions are per-user. Your changes affect
your account only.
