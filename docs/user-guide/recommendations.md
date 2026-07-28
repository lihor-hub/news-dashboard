# Recommendations

Recommendations rank articles in Today according to their general importance
and the preferences learned for your account.

## How scores are formed

The starting score uses article metadata, including importance, category,
tags, and discovery time. Personalization then adjusts it from:

- your affinity for sources, categories, and tags, learned from article
  actions;
- semantic similarity to embedded articles you have starred or marked Done,
  when stored embeddings are available;
- freshness, article importance, and a bounded novelty contribution; and
- active learning goals.

Starring is the strongest positive article action and Done is positive. Skip
and Archive are negative, while Later is neutral. Thumbs-up or thumbs-down
feedback beside **Why recommended?** is a separate, stronger signal.

## Where recommendations appear

Today ranks available articles by their personalized score, falling back to a
general score when personalization is not available yet. Recommendation labels
summarize the score as **Recommended**, **Relevant**, or **Low signal**. Open an
article and select **Why recommended?** to see the factors that contributed,
then use the adjacent thumbs controls if the result was or was not useful.

Normal triage still applies: you can Star, mark Done, send to Later, Skip, or
Archive an article regardless of its recommendation label.

## Reader controls

You control recommendations in two places:

- In **Settings → Personalization**, select **Refresh recommendations** to
  recompute your scores immediately.
- In **Reading DNA → Active nudges**, adjust the per-category weights and
  novelty weight from 0.0× to 3.0×. Changes save and recompute immediately.

A category weight changes that category's direct contribution. The novelty
weight changes the lift for plausible articles that differ from your valued
history; it has no effect when the required stored embeddings are unavailable.

## When scores change

Article actions and explicit recommendation feedback update the signals used
for later scoring. The instance can recalculate stale scores in the background,
and a reader can request an immediate recalculation from Settings. A new
account may initially see general scores until it has useful action history.

## Privacy and optional AI

Recommendation scoring uses data stored in the instance's PostgreSQL database
and does not require an external AI provider. It is calculated for one reader's
account rather than by comparing that reader with other users.

If the deployment operator configures a supported AI provider, the instance can
generate a short explanation for highly ranked articles from article metadata
and recent Starred or Done history. Without that provider, **Why recommended?**
uses the stored score factors instead.
