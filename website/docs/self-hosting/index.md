# Self-Hosting

Running your own instance of News Dashboard via Docker, Docker Compose, or
Helm.

## Deployment options

| Option | Best for |
|--------|----------|
| Docker Compose | Single-node deployments using the published GHCR image. |
| Docker run | Small installations where you already manage PostgreSQL separately. |
| Helm | Kubernetes deployments with bundled or external PostgreSQL. |

For local development, use the root `docker-compose.yml`. For production, use
`docker-compose.prod.yml` or Helm; the development compose file contains
insecure local defaults.

## Production Compose quick start

1. Copy `.env.example` to `.env`.
2. Set strong values for `SESSION_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`,
   `BOOTSTRAP_ADMIN_PASSWORD`, and `POSTGRES_PASSWORD`.
3. Start the stack:

   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

4. Verify health:

   ```bash
   curl http://localhost:8080/api/health
   ```

The application image is published as:

```text
ghcr.io/lihor-hub/news-dashboard:latest
ghcr.io/lihor-hub/news-dashboard:v<version>
ghcr.io/lihor-hub/news-dashboard:<commit-sha>
```

Pin a version or commit SHA for production instead of tracking `latest`.

## Required configuration

News Dashboard uses PostgreSQL at runtime. Configure either `DATABASE_URL` or
the split `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD` variables.

At minimum, a production instance also needs:

| Variable | Purpose |
|----------|---------|
| `SESSION_SECRET` | Signs sessions and, unless overridden, digest mark-read tokens. |
| `BOOTSTRAP_ADMIN_USERNAME` | First admin username when no users exist. |
| `BOOTSTRAP_ADMIN_PASSWORD` | First admin password when no users exist. |
| `POSTGRES_PASSWORD` | Password for the bundled or configured PostgreSQL user. |

See [Configuration](/docs/configuration) for authentication, HTTPS, backup, and
integration guides.

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

- [CI Runner Setup](ci-runner-setup)
- [Authentication](/docs/configuration/authentication)
- [HTTPS with Caddy](/docs/configuration/https-caddy)
- [PostgreSQL Backup and Restore](/docs/configuration/postgres-backup)
