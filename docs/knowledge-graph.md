# Knowledge Graph Architecture

News Dashboard keeps PostgreSQL as the application database. Articles, users,
sources, workflow state, embeddings, briefings, auth, analytics, and scheduler
history remain in PostgreSQL.

Neo4j is optional graph storage for article/entity data:

- `Article` nodes mirror article IDs and titles needed for graph provenance.
- `Entity` nodes use stable IDs from canonical name and type, such as
  `org:openai`.
- `(:Article)-[:MENTIONS]->(:Entity)` records entity mentions.
- `(:Entity)-[:RELATED_TO]->(:Entity)` records extracted typed relationships
  with `relationship_type`, `label`, `confidence`, and `article_id`.

When Neo4j is disabled or unavailable, the app falls back to the PostgreSQL
`articles.entities` cache for the existing knowledge graph endpoint. Ask AI
continues to work from article retrieval and simply omits graph context.

## Data Flow

1. Entity extraction stores validated JSON in `articles.entities`.
2. If `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` are configured, the same
   entities are written through to Neo4j.
3. `news-dashboard graph-backfill` syncs existing cached entities into Neo4j.
4. `news-dashboard graph-relationship-backfill` extracts typed relationships
   from cached-entity articles and writes them to Neo4j.
5. `/api/ai-stats/knowledge-graph` scopes visible articles in PostgreSQL first,
   then asks Neo4j for graph edges only for those article IDs.
6. Ask AI retrieves articles with pgvector as before, then adds bounded Neo4j
   relationship context for those already-selected source articles.

## Operations

Run entity backfill after enabling Neo4j:

```bash
news-dashboard graph-backfill --limit 250 --days 30
```

Run relationship extraction after entities are synced:

```bash
news-dashboard graph-relationship-backfill --limit 50 --days 7
```

The scheduler also runs entity extraction and typed relationship extraction on
intervals. Tune them with `ENTITY_EXTRACTION_INTERVAL_MINUTES` and
`ENTITY_RELATIONSHIP_EXTRACTION_INTERVAL_MINUTES`.

Back up Neo4j with the same storage discipline as PostgreSQL: snapshot the
Neo4j PVC or host path while the pod is quiesced, or use Neo4j-admin tooling in
your cluster runbook.
