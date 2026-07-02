---
title: Today Feed and triage
sidebar_position: 3
---

# Today Feed and triage

The Today Feed is the main work surface in News Dashboard. It contains articles
ready for review from the latest ingestion run and, when recommendations are
enabled, older articles that may be relevant again.

## Triage states

- **Done** removes the article from Today and stores it in your read history.
- **Later** moves the article to a separate read-it-later queue.
- **Skipped** dismisses the article and gives the recommender negative feedback.
- **Starred** keeps the article as a permanent reference.
- **Snoozed** hides the article until the selected time.
- **Archived** removes the article from active views while keeping it restorable.

## Article cards

Each card shows the article title, source, discovery time, summary, reason, and
available triage actions. Recommendation badges and explanations appear when
personalized recommendations are active.

Triage actions update immediately. The Today Feed is designed for fast repeated
decisions, so keyboard shortcuts are available on the feed:

| Key | Action |
|-----|--------|
| `d` or `r` | Mark Done |
| `s` | Star |
| `l` | Send to Later |
| `x` | Skip |
| `o` | Open article |
| `j` / `k` | Move to next or previous article |

## Briefing independence

Workflow state does not affect the [Current-Day Report](briefings#the-current-day-report).
The report summarizes what was discovered today, not only what remains in your
Today Feed.
