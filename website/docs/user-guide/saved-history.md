---
title: Saved and read history
sidebar_position: 8
---

# Saved and read history

Use **Later** for articles to revisit, **Starred** for references, and
**Archive** for articles tucked out of normal views. **Done** records that you
have finished reviewing an article; opening an article alone does not mark it
Done. A star is independent of workflow state.

## Find an article again

| Where | What to find |
|-------|--------------|
| **Later** | Articles set aside for future reading. |
| **Starred** | Articles you have starred. |
| **Archive** | Archived articles, still searchable. |
| **Search → State → Done** | Articles you marked Done. |

Use [Search filters and Saved Views](search.md#filters) to combine state,
source, category, date, tag, or starred status. Include archived articles when
looking beyond active views. You can reopen a result and change its triage
state or star again.

## Reading DNA and organization

**Reading DNA** summarizes your reading mix and recommendation controls,
including category/source activity, streaks, goals, and related learning tools.
Your interactions are scoped to your account. See
[Recommendations](recommendations.md) for how your actions affect ranking, and
[Organize and learn](organize-and-learn.md) for Collections and other ways to
retain useful articles.

## Export and restore

In **Settings → Data Export**, choose **Download archive** to save a JSON
archive of your reading history, article metadata and workflow state,
briefings, source subscriptions, and preferences. Cached article body text and
secrets such as passwords, session tokens, and push keys are excluded.

Choose **Restore archive** to select a previously downloaded JSON file.
Existing articles, briefings, AI memories, subscriptions, and preferences are
matched and updated instead of duplicated. The result reports added, updated,
and skipped counts. Restore writes only to your current account and requires
the archive schema version supported by the running server.

Source restoration covers enabled/disabled shared subscriptions and private
sources owned by your account. It does not take over another user's private
source. Preferences include recommendation weights, onboarding choices, and
notification settings; secret credentials and push subscriptions must be set
up separately. See [Settings and account data](settings-and-account.md) for the
full data-management workflow.

## Retention and troubleshooting

Snoozed articles can return when their timer expires. Analytics events are
pruned according to `ANALYTICS_RETENTION_DAYS` (default 180 days); that is
separate from deleting your article history.

If history appears missing, verify your account and Search filters before
restoring a backup. If restore fails, read the displayed error and use an
archive with the schema version supported by the running server. Keep downloaded archives private:
they contain personal reading activity even though secrets are excluded.
