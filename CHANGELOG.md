# Changelog

All notable changes to this project will be documented in this file.
This project adheres to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.21.0] — 2026-06-26

### Added
- Share articles with other users directly within the platform ([#304](https://github.com/lihor-hub/news-dashboard/pull/304))

## [1.20.0] — 2026-06-25

### Changed
- Smarter and more personalised news recommendations; the app now learns from your feedback and improves over time ([#300](https://github.com/lihor-hub/news-dashboard/pull/300))

## [1.19.1] — 2026-06-25

### Fixed
- Stability improvements to keep the app running reliably

## [1.19.0] — 2026-06-25

### Added
- Behind-the-scenes monitoring improvements via Langfuse tracing on all OpenAI calls (embeddings, Ask AI, briefings, body fetch), tagged with user attribution so issues surface faster ([#295](https://github.com/lihor-hub/news-dashboard/pull/295))

## [1.18.0] — 2026-06-25

### Added
- In-app "What's new" changelog popup — see a quick summary of what changed each time the app updates

## [1.17.0] — 2026-06-25

### Added
- Scheduled daily brief — get your brief delivered automatically at a time you choose
- Push notification when your daily brief is ready

## [1.16.1] — 2026-06-24

### Fixed
- "Why recommended" explanation now stays accurate after recommendations update

## [1.16.0] — 2026-06-24

### Added
- Relevance score shown for every article in Today's feed at a glance

## [1.15.11] — 2026-06-24

### Fixed
- Usage insights now correctly reflect which features you actually use

## [1.15.10] — 2026-06-24

### Fixed
- AI and LLM stories now surface sooner when you're just getting started (cold-start scoring fix)

## [1.15.9] — 2026-06-24

### Fixed
- HuggingFace Blog articles now show proper summaries instead of blank ones

## [1.15.8] — 2026-06-24

### Fixed
- Analytics charts now update correctly when switching between 7-day, 30-day, and 90-day views

## [1.15.7] — 2026-06-24

### Fixed
- Activity heatmap now fills the full width of its panel

## [1.15.6] — 2026-06-24

### Added
- Most-read articles now appear in the reading insights panel

## [1.15.5] — 2026-06-24

### Fixed
- Active users and reading minutes are now shown on separate scales for easier reading

## [1.15.4] — 2026-06-24

### Fixed
- Bottom navigation on the brief page now stays put on smaller screens

## [1.15.3] — 2026-06-24

### Added
- Every article in Today's feed now shows a relevance score

### Fixed
- Recommendations refresh correctly after they're recalculated
- Usage insights now reflect the features you use

## [1.15.2] — 2026-06-24

### Fixed
- HuggingFace Blog articles now show proper summaries
- AI and LLM stories surface sooner when you're getting started
- Analytics charts respond to the 7-day, 30-day, and 90-day view filters
- Cleaner activity heatmap and active-users charts

## [1.15.1] — 2026-06-23

### Fixed
- Bottom navigation no longer overlaps content on the briefing page on mobile
- Articles returned from Later no longer reappear in the Later view

## [1.15.0] — 2026-06-23

### Added
- Smarter daily briefing summaries
- Briefings now retry automatically on temporary failures

### Fixed
- Clearer error messages when a briefing cannot be generated

## [1.14.0] — 2026-06-23

### Added
- Analytics dashboard for understanding reader behaviour
- Admin page for adding and managing users

## [1.13.0] — 2026-06-23

### Added
- "Why recommended" explanation accessible from any article view

### Security
- Tightened what the public status endpoint reveals

## [1.12.3] — 2026-06-23

### Fixed
- Data integrity issue when migrating older sources

## [1.12.0] — 2026-06-21

### Added
- Personalised recommendations that refresh on demand and on a daily schedule
- "Why recommended" explanations on every article
- Compact recommendation labels in Today's feed
- Today's feed now balances fresh, novel, and personally relevant stories
- Recommendation model learns from how you triage and read articles

## [1.11.0] — 2026-06-21

### Added
- In-app update notification when a new version is available (all platforms)
- 17 AI/ML X (Twitter) accounts added as curated sources

### Fixed
- After triaging an article you're returned to your list automatically
- Triage confirmation toasts no longer stack; the latest replaces the previous

## [1.10.0] — 2026-06-21

### Changed
- Smoother, more predictable app update delivery

## [1.9.0] — 2026-06-21

### Added
- Desktop app for macOS and Windows

## [1.8.0] — 2026-06-21

### Added
- Native Android app installable on your phone
- On-demand AI insights for any article with readable text
- Polished app icon that adapts to your Android theme
