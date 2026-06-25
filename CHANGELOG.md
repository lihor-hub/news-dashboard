# Changelog

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
