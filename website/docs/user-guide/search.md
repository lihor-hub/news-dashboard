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

## Full-text extraction

Deeper body search depends on optional article body extraction. When enabled,
the app fetches and caches article text, then indexes it alongside the normal
metadata fields. This increases storage and ingestion work, so it is kept
optional.
