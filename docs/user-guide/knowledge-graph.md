# Knowledge Graph

The Knowledge Graph in AI Stats shows named entities found in recent articles
and how they connect.

- Circles are entities such as people, organizations, products, and places.
- Solid edges mean the entities appeared in the same article.
- Dashed edges are typed relationships extracted from article text, such as
  "led by" or "acquired".
- Selecting an entity shows supporting articles and relationship provenance.

Use the relationship filter to focus on all connections, co-occurrence only, or
typed relationships. If Neo4j is not enabled on your instance, the graph still
uses cached entity data where possible, but typed relationship exploration and
Ask AI graph context may be unavailable.

Ask AI can use graph context when it answers over retrieved articles. The answer
still cites articles; graph context is shown separately so you can see which
entity relationships influenced the response.
