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

Default sources cover Python, AI/LLM, agents, cloud infrastructure,
engineering, trending news, and repositories. They are seeded when the instance
is initialized.

## Managing sources

From the Sources page you can enable, disable, add, or remove sources. You can
also inspect health information such as last checked time, last successful
fetch, last error, fetched count, and inserted count.

Only RSS/Atom feeds are added by pasting a URL. GitHub release and trending
sources are selected from predefined options.

## Noise controls

Broad feeds are capped so one noisy source does not dominate the Today Feed.
Typical caps are 15 to 20 items for broad trending feeds, 5 items for dense
newsletter feeds, and around 50 items for curated blog feeds.

On multi-user instances, source subscriptions are per-user. Your changes affect
your account only.
