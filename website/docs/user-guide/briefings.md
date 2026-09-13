---
title: Briefings
sidebar_position: 6
---

# Briefings

The **Current-Day Report** is a generated overview of news from your available
sources. Its current-day window is the previous 24 hours of article discovery,
not a midnight-to-midnight calendar day. Workflow state does not restrict the
candidate pool: marking an article Done or Skipped does not remove it from
that window.

## Generate and revisit a briefing

Open **Brief** to read the latest briefing or generate your first one. Once a
briefing exists, **Refresh** generates another. A briefing combines a headline,
summary, story sections, and cited articles; follow the citations for the
source material. Source subscriptions and priorities influence the available
news. AI generation requires the instance's configured provider.

Open **Briefing History** to revisit saved briefings. If the latest briefing or
history request fails, use **Retry** before treating it as empty or generating
a replacement.

## Audio and podcast subscriptions

Choose **Create Podcast** on a briefing to generate its conversational audio.
When it is ready, use the audio player to listen. Generation needs the
instance's configured AI and server-side audio services; browser speech alone
does not generate a podcast file.

In **Briefing History**, use **Subscribe as a podcast** to copy your personal
feed URL into a podcast app. Treat the URL as a secret. Regenerating the feed
URL revokes the old one, so update any podcast app that used it.

## Scheduled delivery

Open **Settings → Daily Brief** to choose delivery time and timezone. Configure
**Email briefing** and **Push notifications** there when the instance supports
them. Email delivery needs an account email address and server-side mail
configuration. Push needs browser permission and server VAPID configuration.
Use the email preview control to test delivery before relying on the schedule.

## Troubleshooting

- **No articles to brief:** check source subscriptions and recent source
  health in **Feeds → Sources**. The report needs articles discovered within
  the rolling 24-hour window; try again after ingestion finds new articles.
- **Generation fails:** follow the error shown on Brief. If AI is unavailable,
  ask the instance operator to check provider configuration. Today remains
  usable without a generated briefing.
- **Audio fails:** check that podcast generation completed, then retry playback
  and check browser audio permissions. For a generation error, the operator
  should check the configured audio provider.
- **Podcast app cannot load the feed:** verify the copied URL and network
  connection. If you regenerated the URL, replace the old subscription URL.
- **Delivery does not arrive:** check delivery time, timezone, email enablement,
  and browser push permission in Settings. Use the email preview; the operator
  can investigate mail or push configuration if that fails.

## Privacy

Briefings are scoped to your available sources and stored in the application
database. Configured AI and audio providers may receive the content needed to
generate a briefing or podcast. Anyone holding your podcast feed URL can use
it, so revoke and replace the URL if it has been shared unintentionally.
