---
title: Concepts and terminology
sidebar_position: 2
---

# Concepts and terminology

News Dashboard uses a small vocabulary so product copy, documentation, and
support conversations describe the same workflow.

## Article

An **article** is a news item discovered from a subscribed source. It has a
title, URL, summary, source, publication date, tags, and optional extracted
body text. Triage, search, briefings, recommendations, and sharing all operate
on articles.

## Workflow state

**Workflow state** is your triage position for an article. It does not decide
whether the article belongs to the day's news corpus.

| State | Meaning |
|-------|---------|
| **Today** | In your active triage queue, waiting to be reviewed. |
| **Later** | Interesting, but not right now. |
| **Done** | Reviewed and finished. |
| **Skipped** | Dismissed as not relevant. |
| **Starred** | Saved as a permanent reference. |
| **Snoozed** | Hidden until a later time. |
| **Archived** | Tucked away from active views, but restorable. |

## Today Feed

The **Today Feed** is your active triage queue. Articles arrive from new
ingestions and, when enabled, recommendations. You move them to Done, Later,
Skipped, Starred, Snoozed, or Archived as you work through them.

## Current-Day Report

The **Current-Day Report** is a generated briefing that summarizes all news
discovered in the current-day window from your available sources. It includes
articles regardless of workflow state, so marking an item Done or Skipped does
not remove it from the day's report.

## Source subscription

A **source subscription** is the set of feeds available to your account. A
source can be an RSS or Atom feed, a GitHub releases feed, a trending feed, or
a custom scraped page.
