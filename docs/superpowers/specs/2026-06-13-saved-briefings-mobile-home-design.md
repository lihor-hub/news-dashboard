# Saved Briefings Mobile Home Design

## Context

News Dashboard is a private, PostgreSQL-backed personal news reader. It already supports feed ingestion, workflow states, search, an article reader with full-body fetch, and an Ask AI page with citations.

The next improvement should make the app more useful on a phone. The selected direction is an intelligence-first mobile home that answers: "What changed since my last visit?" The existing raw feed-reading behavior must remain available.

## Goals

- Make the default mobile entry point a saved AI briefing, not a raw article queue.
- Generate briefings from current-day source articles so the app stays useful even after triage.
- Save each generated briefing as a durable artifact with timestamp, scope, content, and cited source articles.
- Keep the current Today feed and article workflow intact.
- Make citations lead directly into the existing article reader.

## Non-Goals

- Do not replace the Today feed or remove feed-reading workflows.
- Do not change article workflow states.
- Do not redesign ingestion, source health, or scheduler operations.
- Do not add SQLite runtime support or database abstraction layers.
- Do not make Ask AI the primary entry point in this slice.

## Product Shape

Add a new **Brief** experience as the default home screen. It shows the latest saved briefing and provides a clear action to generate a new one.

The old feed behavior remains available as **Today**. Users who want to read the feed directly should still have a first-class route and navigation item.

Recommended navigation:

- `/` renders Brief.
- `/today` renders the current Today inbox feed.
- `/inbox` redirects to `/today`.
- Mobile bottom navigation shows `Brief`, `Today`, `Later`, `Starred`, and `More`.
- Desktop rail shows `Brief`, `Today`, `Later`, `Starred`, `Search`, `Ask`, then operational views.

The Brief screen includes:

- Latest saved briefing.
- Generated timestamp, article count, and covered time window.
- Primary action to generate a new brief.
- Secondary action to review the raw Today feed.
- Executive summary.
- Three to six briefing sections.
- Cited article chips or cards that open `/a/:id`.
- Empty, loading, and AI-configuration error states.

## Data Model

Runtime database code must use PostgreSQL-specific SQL and psycopg `%s` parameters.

Add a `briefings` table:

- `id`: primary key.
- `created_at`: generation timestamp.
- `scope`: text scope identifier, initially `current_day`.
- `since_at`: lower bound for considered article discovery time.
- `until_at`: upper bound for considered article discovery time.
- `status`: `complete` or `failed`.
- `title`: generated short title.
- `summary`: generated executive summary.
- `content`: `jsonb` structured briefing payload.
- `model`: model used for generation.
- `error`: nullable error detail for failed attempts.

Add a `briefing_articles` table:

- `briefing_id`: foreign key to `briefings`.
- `article_id`: foreign key to `articles`.
- `section_index`: nullable section position.
- `citation_index`: nullable citation position within a section.

Store structured content as JSONB for the first implementation because the useful briefing shape may evolve. Expected content shape:

```json
{
  "sections": [
    {
      "title": "Agent frameworks are tightening production workflows",
      "body": "LangGraph and observability updates point toward more production-grade agent systems.",
      "citations": [123, 456]
    }
  ],
  "worth_opening": [123, 789]
}
```

A separate `briefing_sections` table is intentionally deferred until the section shape stabilizes.

## Backend API

Add briefing endpoints:

- `GET /api/briefings/latest`: return the latest saved briefing, or an empty state payload.
- `GET /api/briefings`: return saved briefing history.
- `GET /api/briefings/{id}`: return one briefing with cited article metadata.
- `POST /api/briefings`: generate and save a new briefing.

`POST /api/briefings` behavior:

- Select candidate articles from the current-day report corpus, not the Today Feed.
- Use a current-day window rather than the previous briefing's `until_at`.
- Set `until_at` to generation time.
- Include articles regardless of Workflow State, so already-opened, starred, done, skipped, and later articles still contribute to the report.
- Keep source subscription scoping for the current user.
- Cap candidates to 40 articles, ordered by importance score and recency.
- Require AI configuration. Missing `OPENAI_API_KEY` or disabled AI should return a clear configured-state error.
- Validate generated JSON before saving.
- Save one `briefings` row and join rows for every cited article.

If there are no candidate articles, the endpoint should return a low-signal empty response and avoid saving a meaningless briefing.

## Briefing Generation

The generated briefing should be structured for mobile scanning:

- Short title.
- One-paragraph executive summary.
- Three to six sections.
- Each section has a title, concise body, and citation article IDs.
- A short `worth_opening` list of the highest-signal article IDs.

The prompt should ask for concise synthesis and explicitly require citations from the provided article IDs only. The backend should reject citations that do not match the candidate set.

## Frontend UX

Add a `BriefPage`.

Primary states:

- **Latest briefing**: render title, metadata, summary, sections, citation chips/cards, and actions.
- **Empty**: explain that no briefing has been generated yet; offer Generate and Review feed actions.
- **Generating**: keep layout stable and show progress.
- **AI not configured**: show a clear setup message without hiding the Today feed path.
- **Generation failed**: show retry and Review feed actions.

Citation behavior:

- Tapping a citation opens `/a/:id`.
- Article reader remains the deep reading surface.
- The Brief page should not duplicate the full reader.

Visual direction:

- Mobile-first density.
- Compact header.
- Clear hierarchy between summary, sections, and citations.
- No marketing-style landing page.
- The raw feed remains one tap away.

## Testing

Backend tests:

- Briefing tables initialize correctly.
- Latest briefing returns an empty state when no saved brief exists.
- Candidate selection includes eligible current-day articles in the time window regardless of Workflow State.
- Generated briefing saves JSON content and article join rows.
- Invalid generated citations are rejected or removed.
- Missing AI configuration returns a clear error.
- PostgreSQL SQL uses psycopg parameter style.

Frontend tests:

- `/` renders Brief by default.
- `/today` renders the existing Today feed.
- Mobile navigation includes both Brief and Today.
- Empty, loading, configured-error, and failed-generation states render.
- Citation interactions navigate to article reader routes.

## Rollout

Implement without removing existing feed workflows:

1. Add backend storage and read endpoints.
2. Add generation endpoint and validation.
3. Add `BriefPage` and route it without changing existing Today behavior.
4. Switch `/` to Brief and move the old inbox page to `/today`.
5. Update mobile and desktop navigation.
6. Keep redirects for legacy routes.

## Fixed Defaults

- Briefing generation uses the app's current-day window.
- Briefing generation considers at most 40 candidate articles.
