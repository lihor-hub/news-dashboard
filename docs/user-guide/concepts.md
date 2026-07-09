# Concepts & Terminology

News Dashboard uses a small set of precise terms to describe the reading
workflow. Using these terms consistently makes the product predictable and
avoids confusion between "read" as a state and "read" as an action.

## Article

A **news item** discovered from a subscribed source. An Article has a title,
URL, summary, and metadata (category, tags, source, publication date). All
features — triage, search, briefings, sharing — operate on articles.

*Don't call it*: Feed item, story, post, entry.

## Workflow State

The user's **triage position** for an article. Workflow State tells you where
an article sits in your reading process. It does **not** decide whether the
article belongs to the day's news corpus (the [Current-Day Report][1] covers
all articles discovered today regardless of state).

The states are:

| State      | Meaning                                                          |
| ---------- | ---------------------------------------------------------------- |
| **Today**  | In your active triage queue, waiting to be reviewed              |
| **Later**  | Interesting but not right now — come back to it                  |
| **Done**   | Reviewed and finished                                            |
| **Skipped**| Not relevant; dismissed without reading                          |
| **Starred**| Saved as a permanent reference                                   |
| **Snoozed**| Hidden until a later time                                        |
| **Archived** | Tucked out of view; can be restored to Done                  |

*Don't call it*: Read status, started status, view state.

[1]: briefings.md

## Today Feed

Your **active triage queue** — the list of articles currently meant to be
reviewed. Processing your Today Feed is the primary workflow. Articles arrive
here from new ingestions and recommendations; you move them to Done, Later,
Skipped, or other states as you work through them.

*Don't call it*: Current-day news, all news, inbox, unread feed.

## Current-Day Report

A **generated briefing** that summarizes all news discovered in the
current-day window from your available sources — regardless of each article's
Workflow State. This is the daily brief the app generates for you.

*Don't call it*: Since-last-briefing report, Today-only briefing, inbox-only
briefing.

## Source Subscription

The **set of news sources** available to your account. A source is a feed
(RSS, GitHub releases, trending, scraped page, etc.) from which the app
discovers articles. You manage sources from the Sources page: add, remove,
enable, or disable them.

*Don't call it*: Feed filter, source state, channel.

## Knowledge Graph

An **entity relationship map** built from your visible articles. Entities are
people, organizations, products, and places extracted from article text.
Co-occurrence edges mean two entities appeared in the same article; typed
relationship edges are explicit article-supported relationships.

*Don't call it*: Global facts database, ontology, web search graph.

## Where these terms come from

This terminology is defined in [`CONTEXT.md`](../../CONTEXT.md) and is the
canonical language for the project. All documentation, UI labels, and
changelog entries use these terms.
