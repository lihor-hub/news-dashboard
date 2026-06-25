# Changelog

## 1.18.0
- Show a "What's new" popup highlighting changes after the app updates to a new version

## 1.17.0
- Auto-schedule the daily brief with a configurable delivery time
- Send push notifications when a new daily brief is ready

## 1.16.1
- Fix stale "Why recommended" cache after recommendations recalculate

## 1.16.0
- Show a numeric relevance score on each article card in Today's feed

## 1.15.11
- Populate the analytics Feature usage panel by emitting feature events

## 1.15.10
- Add AI/LLM to the cold-start category bonus in the recommendation score

## 1.15.9
- Fix empty summaries for HuggingFace Blog articles

## 1.15.8
- Make analytics charts respond to the 7d/30d/90d time filter

## 1.15.7
- Fix activity heatmap width to fill the panel

## 1.15.6
- Emit article dwell telemetry to populate the most-read panel

## 1.15.5
- Split active-users and minutes onto separate Y axes

## 1.15.4
- Keep the brief page bottom navbar within the viewport

## 1.15.3
- Show numeric relevance score on each article card in Today's feed
- Invalidate article cache after recommendations recalculate
- Fix analytics Feature usage panel by emitting feature events

## 1.15.2
- Fix empty summaries for HuggingFace Blog articles
- Add AI/LLM to cold-start category bonus in recommendation score
- Make analytics charts respond to 7d/30d/90d time filter
- Fix activity heatmap width and active-users chart axes

## 1.15.1
- Fix briefing page bottom navbar overlapping content on mobile
- Drop returned snoozes from the Later view

## 1.15.0
- Briefing summarization via custom OpenAI-compatible endpoint
- Retry briefing generation on transient AI failures
- Surface upstream errors from the briefing AI endpoint

## 1.14.0
- Admin user-behavior analytics dashboard
- Admin page to provision users (Keycloak-aware)

## 1.13.0
- Expose recommendation score on single-article read path
- Fix: stop leaking internal DB details from public health endpoint

## 1.12.3
- Fix coercion of source values in SQLite-to-Postgres migration

## 1.12.0
- On-demand and daily personalized recommendation refresh
- Recalculate and observe stale recommendation scores
- Expose inspectable recommendation explanations ("Why recommended")
- Show compact recommendation labels in Today's feed
- Blend novelty and freshness into Today ranking
- Add semantic similarity to hybrid recommendation score
- Learn behavioral affinity from workflow actions
- Rank Today feed by personalized recommendation scores

## 1.11.0
- In-app update-available notification for all platforms
- Add 17 AI/ML X (Twitter) accounts via Nitter RSS
- Navigate back to article list after triage action on article page
- Fix triage toasts stacking — they now replace each other

## 1.10.0
- Automatic semantic versioning via Conventional Commits

## 1.9.0
- Electron desktop app (wraps news.lihor.ro, distributed via GitHub Releases)

## 1.8.0
- Android APK signed release via GitHub Actions
- TWA (Trusted Web Activity) native Android wrapper
- On-demand AI insights require article body text before generating
- Monochrome icon for Android 13+ themed icons
