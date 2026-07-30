# Self-Hosting

Running your own instance of News Dashboard via Docker, Docker Compose, or
Helm.

## Know your role

A **deployment operator** chooses a deployment method, supplies secrets and
environment configuration, operates PostgreSQL and persistent storage,
monitors health, and performs backups and upgrades. An **application
administrator** signs in to manage users and review ingest operations,
statistics, and analytics.

One person can hold both roles, but host or cluster access does not grant
application administrator access. After deployment, continue with
[Administration and operations](/docs/user-guide/administration-and-operations)
for the in-app controls.

## Deployment options

| Option         | Best for                                                            |
| -------------- | ------------------------------------------------------------------- |
| Docker Compose | Single-node deployments using the published GHCR image.             |
| Docker run     | Small installations where you already manage PostgreSQL separately. |
| Helm           | Kubernetes deployments with bundled or external PostgreSQL.         |

For local development, use the root `docker-compose.yml`. For production, use
`docker-compose.prod.yml` or Helm; the development compose file contains
insecure local defaults.

## Production Compose quick start

1. Copy `.env.example` to `.env`.
2. Set strong values for `SESSION_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`,
   `BOOTSTRAP_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, and `NEO4J_PASSWORD`.
3. Start the stack:

   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

4. Verify health:

   ```bash
   curl http://localhost:8080/api/health
   ```

The production Compose stack includes a bundled Neo4j container and wires the
app to it with `NEO4J_*`, so the knowledge graph is enabled as soon as the
stack is up. Backfill existing entities after first start:

```bash
docker compose -f docker-compose.prod.yml exec news-dashboard \
  news-dashboard graph-backfill --limit 250 --days 30
docker compose -f docker-compose.prod.yml exec news-dashboard \
  news-dashboard graph-relationship-backfill --limit 50 --days 7
```

The application image is published as:

```text
ghcr.io/lihor-hub/news-dashboard:latest
ghcr.io/lihor-hub/news-dashboard:v<version>
ghcr.io/lihor-hub/news-dashboard:<commit-sha>
```

Pin a version or commit SHA for production instead of tracking `latest`.

## Production Helm quick start

The production Helm contract terminates application TLS at the Ingress and
keeps the application Service private:

```bash
helm upgrade --install news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard --create-namespace \
  --values ./helm/news-dashboard/values-production.yaml \
  --set image.tag='<immutable-source-sha>' \
  --set-string app.auth.sessionSecret='<from-secret-manager>' \
  --set-string postgresql.password='<from-secret-manager>'
```

Supply secrets and installation-specific persistence at runtime. Do not commit
them to a values file. Before public cutover, verify the ClusterIP Service, TLS
Ingress, backups and restore, rollback revision, and the existing `/keycloak`
route. Caddy cannot share ports 80 and 443 with the ingress controller.

The live appliance procedure requires human access and is tracked in
[issue #1302](https://github.com/lihor-hub/news-dashboard/issues/1302). Follow
[Ingress HTTPS and Caddy migration](/docs/configuration/https-caddy) for the
staged verification and rollback order.

## Required configuration

News Dashboard uses PostgreSQL at runtime. Configure either `DATABASE_URL` or
the split `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD` variables.

At minimum, a production instance also needs:

| Variable                   | Purpose                                                         |
| -------------------------- | --------------------------------------------------------------- |
| `SESSION_SECRET`           | Signs sessions and, unless overridden, digest mark-read tokens. |
| `BOOTSTRAP_ADMIN_USERNAME` | First admin username when no users exist.                       |
| `BOOTSTRAP_ADMIN_PASSWORD` | First admin password when no users exist.                       |
| `POSTGRES_PASSWORD`        | Password for the bundled or configured PostgreSQL user.         |
| `NEO4J_PASSWORD`           | Password for the bundled Neo4j graph store.                     |

See [Configuration](/docs/configuration) for authentication, HTTPS, backup, and
integration guides. The root
[README Configuration section](https://github.com/lihor-hub/news-dashboard#configuration)
is the canonical environment-variable reference.

## Operations

- Use `/api/live` for liveness checks; it does not require database access.
- Use `/api/ready` for readiness checks; it verifies database connectivity.
- Use `/api/health` for load-balancer or manual health checks.
- Enable `/metrics` with `METRICS_ENABLED=true` only when you want Prometheus
  exposition.
- Enable `/docs`, `/redoc`, and `/openapi.json` with `ENABLE_API_DOCS=true`
  only in trusted environments.

To upgrade a Compose deployment, pull the pinned replacement image and restart:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

To roll back, set the image tag to the previous known-good version and run the
same pull/up commands.

## More guides

- [Administration and operations](/docs/user-guide/administration-and-operations)
- [Configuration and integrations](/docs/configuration)
- [CI Runner Setup](ci-runner-setup)
- [Authentication](/docs/configuration/authentication)
- [Neo4j Knowledge Graph](/docs/configuration/neo4j-knowledge-graph)
- [Ingress HTTPS and Caddy migration](/docs/configuration/https-caddy)
- [PostgreSQL Backup and Restore](/docs/configuration/postgres-backup)
