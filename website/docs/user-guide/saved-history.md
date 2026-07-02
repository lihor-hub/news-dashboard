---
title: Saved and read history
sidebar_position: 8
---

# Saved and read history

Your history is the set of articles you have moved out of active triage:
Done, Later, Starred, Snoozed, and Archived.

| View | Contains |
|------|----------|
| **Done** | Articles you have reviewed. |
| **Later** | Articles set aside for future reading. |
| **Starred** | Permanent references. |
| **Archived** | Articles tucked out of normal views. |

Each interaction records timestamps such as read, saved, starred, snoozed, or
unsnoozed time. These timestamps power history views, search, analytics, and
the Reading DNA summary.

## Reading DNA

Reading DNA is a private summary of your reading behavior: articles read, top
categories, top sources, top tags, recent activity, and related trends when
enabled.

## Export and cleanup

The app can export your personal state as JSON for backup or migration. The
`user_events` table is pruned according to `ANALYTICS_RETENTION_DAYS`, which
defaults to 180 days.
