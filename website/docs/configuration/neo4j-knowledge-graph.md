---
sidebar_position: 8
---

# Neo4j Knowledge Graph

Neo4j is optional graph storage for entity and relationship data. PostgreSQL
remains the application database.

Enable the chart-managed Neo4j service:

```bash
helm upgrade news-dashboard ./helm/news-dashboard \
  --reuse-values \
  --set neo4j.enabled=true \
  --set-string neo4j.auth.password='replace-with-a-long-random-password'
```

For externally managed credentials, create a Secret containing both the app
password key and `NEO4J_AUTH` for the Neo4j container:

```bash
kubectl create secret generic news-dashboard-neo4j-auth \
  --from-literal=NEO4J_PASSWORD='replace-with-a-long-random-password' \
  --from-literal=NEO4J_AUTH='neo4j/replace-with-a-long-random-password'
```

Then install with:

```bash
helm upgrade news-dashboard ./helm/news-dashboard \
  --reuse-values \
  --set neo4j.enabled=true \
  --set neo4j.auth.existingSecret=news-dashboard-neo4j-auth
```

Useful values:

| Value | Purpose |
| --- | --- |
| `neo4j.enabled` | Renders the Neo4j StatefulSet, Service, Secret, and storage. |
| `neo4j.auth.user` | Neo4j username, default `neo4j`. |
| `neo4j.auth.password` | Chart-managed password; prefer a secret override in production. |
| `neo4j.auth.existingSecret` | Existing Secret for credentials. |
| `neo4j.persistence.size` | PVC size when using chart-managed storage. |
| `neo4j.persistence.existingClaim` | Existing PVC name. |
| `neo4j.persistence.hostPath` | Single-node host path storage. |

After enabling Neo4j, backfill existing cached entities:

```bash
news-dashboard graph-backfill --limit 250 --days 30
news-dashboard graph-relationship-backfill --limit 50 --days 7
```
