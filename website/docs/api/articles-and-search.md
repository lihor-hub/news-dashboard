---
title: Articles and search
sidebar_position: 3
---

# Articles and search

Articles are the core resource. Every article belongs to a source, carries a
triage state, and can be annotated with highlights and tags.

## Listing articles

```
GET /api/articles
```

Returns the [standard collection envelope](index.md#collections).

| Parameter | Type | Notes |
|-----------|------|-------|
| `status` | string | Filter by workflow status. |
| `state` | string | Filter by triage state (`new`, `read`, `saved`, `skipped`, `archived`). |
| `starred` | boolean | Restrict to starred articles. |
| `category` | string | Filter by category. |
| `tag_id` | integer | Restrict to articles carrying a tag. |
| `limit` | integer | `1..500`, default `100`. |
| `offset` | integer | `>= 0`, default `0`. |

## Reading one article

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/articles/{article_id}` | GET | Metadata for a single article. |
| `/api/articles/{article_id}/body` | GET | The extracted article body. |
| `/api/articles/{article_id}/body` | POST | Trigger or refresh body extraction. |
| `/api/articles/{article_id}/audio` | POST | Generate a spoken version. |

Body text is fetched and extracted separately from ingestion, so a freshly
ingested article may have metadata before it has a body. `GET` returns what is
stored; `POST` asks the backend to (re-)extract from the source URL.

## Triage

Triage is the primary write path. Each verb is a narrow `PATCH` rather than a
general article update, which keeps the audit trail meaningful:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/articles/{article_id}/status` | PATCH | Set workflow status. |
| `/api/articles/{article_id}/state` | PATCH | Set triage state. |
| `/api/articles/{article_id}/star` | PATCH | Toggle starred. |
| `/api/articles/{article_id}/later` | PATCH | Mark for later. |

There is also a token-authenticated public route used by email digests, so a
"mark as read" link works without a login session:

```
GET /api/articles/{article_id}/read?token=...
```

## Saving an external URL

```
POST /api/articles/save-url
```

Ingests an arbitrary URL as an article for the calling user, without adding a
recurring source. This is what the browser extension and share targets use.

## Search

```
GET /api/search
```

| Parameter | Type | Notes |
|-----------|------|-------|
| `q` | string | Space-separated search terms. |
| `limit` | integer | `1..200`, default `50`. |
| `offset` | integer | `>= 0`, default `0`. |
| `states` | string[] | Repeatable; restrict to these triage states. |
| `categories` | string[] | Repeatable. |
| `sources` | string[] | Repeatable; source slugs. |
| `starred_only` | boolean | Default `false`. |
| `include_archived` | boolean | Default `false`. Archived articles are excluded unless set. |
| `date_range` | string | Default `all`. |
| `tag_id` | integer | Restrict to a tag. |

Repeatable parameters are passed by repeating the key:
`?states=new&states=saved`.

### Saved searches

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/search/saved` | GET | List saved searches. |
| `/api/search/saved` | POST | Save the current query and filters. |
| `/api/search/saved/{search_id}` | PATCH | Rename or update. |
| `/api/search/saved/{search_id}` | DELETE | Remove. |

## Highlights

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/articles/{article_id}/highlights` | GET | List highlights on an article. |
| `/api/articles/{article_id}/highlights` | POST | Create one. |
| `/api/articles/{article_id}/highlights/{highlight_id}` | DELETE | Remove one. |

Highlights are per-user and anchor into the extracted body, so re-extracting
a body can affect how they resolve.

## Tags and collections

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/tags` | GET | List your tags. |
| `/api/tags` | POST | Create a tag. |
| `/api/tags/{tag_id}` | PATCH | Rename or restyle. |
| `/api/tags/{tag_id}` | DELETE | Delete a tag. |
| `/api/tags/{tag_id}/articles` | GET | Articles carrying a tag. |
| `/api/articles/{article_id}/tags` | GET | Tags on an article. |
| `/api/articles/{article_id}/tags` | POST | Attach a tag. |
| `/api/articles/{article_id}/tags/{tag_id}` | DELETE | Detach a tag. |

## Reading list

An explicitly ordered queue, separate from tags and triage state:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/reading-list` | GET | List queued items in order. |
| `/api/reading-list` | POST | Add an item. |
| `/api/reading-list/reorder` | POST | Reorder the queue. |
| `/api/reading-list/import` | POST | Bulk import. |
| `/api/reading-list/{item_id}` | PATCH | Update an item. |
| `/api/reading-list/{item_id}` | DELETE | Remove an item. |

## AI-derived views

These endpoints run retrieval or generation and are slower than plain reads.
They depend on article embeddings, which are produced during ingestion.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/articles/{article_id}/insights` | GET | Generated insights for an article. |
| `/api/articles/{article_id}/perspectives` | GET | Contrasting coverage of the same story. |
| `/api/articles/topic-map` | GET | Topic clustering across your articles. |
| `/api/ask` | POST | Ask a question across your corpus. |
| `/api/summary` | GET | A generated summary view. |

Embedding similarity is executed as SQL `<=>` queries against an HNSW index in
PostgreSQL, which is why the [pgvector
extension](../architecture/index.md) is a hard requirement rather than an
optional extra.

## Reading progress

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/users/me/streak` | GET | Current reading streak. |
| `/api/users/me/achievements` | GET | Unlocked achievements. |
| `/api/users/me/reading-dna` | GET | Aggregate reading profile. |
