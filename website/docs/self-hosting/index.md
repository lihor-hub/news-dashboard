---
sidebar_position: 0
---

# Self-Hosting

Deploy and operate News Dashboard with PostgreSQL and persistent app storage.
Use production Compose for a single host, Docker run with an existing database,
or Helm for Kubernetes. Start with deployment and configuration, then verify
health and backups before exposing the instance.

| Guide | Use it to |
| ----- | --------- |
| [Deployment](deployment.md) | Choose a runtime, pin and verify images, configure Ingress and host PostgreSQL, and enable Neo4j. |
| [Environment variables](environment-variables.md) | Configure credentials, AI, email, privacy, security, and optional integrations. |
| [Health and probes](health-and-probes.md) | Choose readiness/liveness checks and configure Docker or Kubernetes probes. |
| [Monitoring and metrics](monitoring-and-metrics.md) | Monitor ingestion, scrape private Prometheus metrics, and configure error tracking. |
| [Upgrading and rolling back](upgrading-and-rolling-back.md) | Back up data, apply migrations, and restore the previous application or edge safely. |
| [Background jobs](background-jobs.md) | Choose one ingest scheduler and control scheduled operations. |
| [Sizing and tuning](sizing-and-tuning.md) | Estimate resources and storage, adjust cadence, and tune retention. |

## Know Your Role

A **deployment operator** chooses a deployment method, supplies secrets and
environment configuration, operates PostgreSQL and persistent storage,
monitors health, and performs backups and upgrades. An **application
administrator** signs in to manage users and review ingest operations,
statistics, and analytics.

One person can hold both roles, but host or cluster access does not grant
application administrator access. After deployment, continue with
[Administration and operations](../user-guide/administration-and-operations.md)
for the in-app controls.

## Related operator guides

- [Configuration and integrations](../configuration/index.md)
- [CI Runner Setup](ci-runner-setup.md)
- [Authentication](../configuration/authentication.md)
- [Neo4j Knowledge Graph](../configuration/neo4j-knowledge-graph.md)
- [Ingress HTTPS and Caddy migration](../configuration/https-caddy.md)
- [PostgreSQL Backup and Restore](../configuration/postgres-backup.md)
