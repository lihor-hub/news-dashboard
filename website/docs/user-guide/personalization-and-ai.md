---
title: Personalization and AI
sidebar_position: 7
---

# Personalization and AI

Personalization starts with your own article actions. AI-assisted views build
on that corpus, but several of them are optional because a deployment operator
must configure the server-side provider or storage they use.

## Recommendations

Recommendations score candidate articles from local signals such as source,
category, tags, discovery time, and your previous actions. Starred and Done
articles are positive signals, Skip is negative, and Later is neutral.
Recommended items can appear in Today with a relevance indicator and a reason.

Open **Settings → Personalization** and select **Refresh recommendations** to
recompute your scores immediately. If you have little history, read, star, or
skip a few articles first. Recommendation scoring itself uses data in the
instance's PostgreSQL database and does not require an external AI provider.

See [Recommendations](recommendations.md) for scoring and feed controls.

## Ask

**Ask** answers questions over articles available to your account and returns
cited articles that you can open. It can also recognize supported workflow
requests, show a proposed action plan, and wait for your approval before
changing article state.

Ask requires the deployment operator to configure a supported server-side AI
provider. If it is unavailable, contact the instance operator; adding a key is
not a reader setting. By default, Ask searches your Starred and Done articles
and needs enough material in that corpus. Select **Include all non-archived
articles** on the Ask page to widen the corpus when you want Today, Later,
Skipped, and other non-archived articles considered too.

## AI Watchlists

In **Settings → AI Watchlists**, describe a topic or goal, preview recent
matches, give the watchlist a label, and add it. Enabled watchlists evaluate
new material in the background and can create notifications for matches. They
never star, archive, or otherwise triage an article for you.

Matching can use the configured AI provider when one is available and falls
back to deterministic article search and scoring when it is not. Notification
delivery still depends on the instance and device configuration described in
[Settings and account data](settings-and-account.md).

## AI Memory

**Settings → AI Memory** stores explicit preferences or goals for your
account. Add a memory yourself, edit it, or deactivate it when it no longer
applies. **Learn from recent reading** can create a small set of memories from
your recent Reading DNA patterns without requiring an external model.

Active memories provide additional personal context to supported generated
features such as Ask and briefings. Review them periodically; they are visible
and controllable in Settings, and they are included in personal data
export/restore.

## Topic Map

**Topic Map** groups articles from the last seven days by embedding similarity.
Select a cluster outline to inspect its summary and articles, or select a point
to open the article.

This view needs enough recent articles with stored embeddings. Generating new
embeddings is a server-side AI capability configured by the deployment
operator; existing stored embeddings can still populate the map. An empty map
can simply mean that the instance has not generated enough embeddings yet.

## AI Stats

**AI Stats** offers 7-, 14-, and 30-day views:

- **Word Cloud** derives weighted terms locally from recent titles and
  summaries.
- **Embedding Space** projects stored article embeddings, so its coverage
  depends on server-generated embeddings.
- **Knowledge Graph** shows extracted entities and relationships. The instance
  can use optional graph storage and otherwise falls back to cached entity data
  where possible.

See [Knowledge Graph](knowledge-graph.md) for relationship meanings,
provenance, and how graph context can support Ask.

## Who controls what

| Capability                    | Reader control                                           | Instance control                                     |
| ----------------------------- | -------------------------------------------------------- | ---------------------------------------------------- |
| Recommendations               | Reading actions and manual refresh                       | Recommendation feature settings                      |
| Ask                           | Question, corpus scope, and approval of proposed actions | AI provider credentials                              |
| AI Watchlists                 | Query, label, enabled state, and deletion                | Background evaluation and notification support       |
| AI Memory                     | Add, learn, edit, and deactivate memories                | Availability of generated features that consume them |
| Topic Map and embedding views | Time range or selected cluster                           | AI embedding provider and processing                 |
| Knowledge Graph               | Time range, filters, and selected entity                 | Entity extraction and optional graph storage         |
