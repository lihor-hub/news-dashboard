# Sources & Subscriptions

Your **Source Subscription** is the set of feeds News Dashboard uses to discover
articles. Managing sources lets you shape what appears in your Today Feed.

## What is a source?

A source is a feed — an RSS/Atom feed, GitHub releases, Hacker News/GitHub
trending, or a custom-scraped page — from which the app discovers articles.
Each source belongs to a category (AI/LLM, Python, engineering, trending,
etc.) and a kind (rss_feed, github_release_feed, trending_feed, scraped_page).

## Default sources

When you first run `news-dashboard init`, the app populates your subscription
with a curated list of technical news sources. These are defined in
`sources.py` and grouped by category:

- **python** — Python Insider, Astral blog, Ruff/uv/mypy/pyright/scikit-learn/scipy/PyTorch/TensorFlow releases
- **ai-llm** — Anthropic (scraped), OpenAI, Google AI, Hugging Face, Augment Code, Simon Willison, Latent Space, Import AI, InfoQ
- **agents** — LangChain, LangGraph, Langfuse releases
- **cloud-infra** — Kubernetes, Docker, AWS ML blog
- **engineering** — Pragmatic Engineer, GitHub Changelog, GitHub Engineering
- **trending** — Hacker News Best, Hacker News AI search
- **repositories** — GitHub Trending (All, Python, TypeScript)

You can add, remove, enable, or disable any of these sources to match your
interests.

## Source kinds

The app understands these feed types:

| Kind               | What it is                                                  |
| ------------------ | ----------------------------------------------------------- |
| **rss_feed**       | Standard RSS/Atom feed (parsed by feedparser)               |
| **github_release_feed** | GitHub releases Atom feed                                 |
| **trending_feed**  | Hacker News/GitHub trending RSS                             |
| **scraped_page**   | Custom HTML scraper (stdlib urllib + html.parser, no deps)  |

## Source health

Each source displays a health badge in the Sources tab:

- **✅ OK** — last fetch succeeded
- **⚠️ Stale** — last fetch was more than the expected interval ago but not an error
- **❌ Error** — last fetch failed; tooltip shows the error message

The app tracks:
- `last_checked_at` — timestamp of last fetch attempt
- `last_success_at` — timestamp of last successful fetch
- `last_error` — last error message (null if no error)
- `last_fetched_count` — items found in last run
- `last_inserted_count` — new articles added in last run

## Managing sources

On the **Sources** page you can:

- **Enable/disable** a source without deleting it (toggle the switch)
- **Add a new source** by pasting its feed URL (rss_feed, github_release_feed,
  or trending_feed kinds)
- **Remove a source** permanently
- **View health** and last-check timestamps
- **See how many articles** were fetched and inserted in the last run

Only RSS/Atom-type feeds (kind `rss_feed`) can be added via URL. For
github_release_feed and trending_feed kinds, use the dropdown when adding a
source — these are predefined (GitHub user/org/repo releases, HN/GitHub trending).

## Noise filtering

Some broad feeds are capped to avoid overwhelming your Today Feed:

- Broad feeds (HN, GitHub trending): 15–20 items per run
- Newsletter feeds (Import AI, Latent Space): 5 per run
- Curated blog feeds: 50 per run

This keeps the ingestion manageable while still surfacing high-signal content.

## Adding a source

1. Navigate to the Sources page
2. Click "Add source"
3. Choose the kind:
   - For RSS/Atom: paste the feed URL
   - For GitHub releases: select a user/org/repo from the dropdown
   - For trending: select Hacker News or GitHub trending
4. Assign a category (optional; you can create a new one)
5. Click Save — the source will be enabled and queued for the next fetch

## Removing a source

1. On the Sources page, find the source you want to remove
2. Click the trash icon or "Remove" button
3. Confirm — the source is deleted and its articles remain in your database
   (they won't be re-ingested unless you add the source back)

## Source subscriptions are per-user

On a multi-user instance, each user maintains their own source list. Changes
you make affect only your subscription.
