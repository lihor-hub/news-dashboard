# Self-Hosting

**Note**: The GHCR package must be made public (or accessible via pull secret) for this to work.
> This is a one-time maintainer action: go to the repository's Packages settings, 
> select the `ghcr.io/lihor-hub/news-dashboard` package, and change its visibility to Public.

This guide explains how to deploy News Dashboard for production use using the published Docker image from GitHub Container Registry (GHCR).

## Running the Published Image

Instead of building from source, you can run the pre-built image from GHCR:

### Prerequisites

- PostgreSQL database (version 16+)
- Docker or container runtime
- Required environment variables (see [Configuration](#configuration))

### Step 1: Start PostgreSQL

```bash
docker run --rm -d \
  --name news-dashboard-postgres \
  -e POSTGRES_DB=news_dashboard \
  -e POSTGRES_USER=news_dashboard \
  -e POSTGRES_PASSWORD=your-secure-password-here \
  -v news-dashboard-postgres-data:/var/lib/postgresql/data \
  -p 5432:5432 \
  postgres:16-alpine
```

### Step 2: Run the Application

```bash
docker run -d \
  --name news-dashboard \
  -p 8080:8080 \
  --link news-dashboard-postgres:postgres \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB=news_dashboard \
  -e POSTGRES_USER=news_dashboard \
  -e POSTGRES_PASSWORD=your-secure-password-here \
  -e SESSION_SECRET="$(openssl rand -hex 32)" \
  -e BOOTSTRAP_ADMIN_USERNAME=admin \
  -e BOOTSTRAP_ADMIN_PASSWORD=your-secure-password-here \
  --restart unless-stopped \
  ghcr.io/lihor-hub/news-dashboard:latest
```

> **Note**: Replace `your-secure-password-here` with strong, unique values for production use.

### Using Docker Compose

For a more manageable setup, you can use Docker Compose:

Create a `docker-compose.yml` file:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: news_dashboard
      POSTGRES_USER: news_dashboard
      POSTGRES_PASSWORD: your-secure-password-here
    volumes:
      - news-dashboard-postgres:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

  news-dashboard:
    image: ghcr.io/lihor-hub/news-dashboard:latest
    ports:
      - "8080:8080"
    environment:
      POSTGRES_HOST: postgres
      - POSTGRES_PORT: "5432"
      - POSTGRES_DB: news_dashboard
      - POSTGRES_USER: news_dashboard
      - POSTGRES_PASSWORD: your-secure-password-here
      - SESSION_SECRET: ${SESSION_SECRET}
      - BOOTSTRAP_ADMIN_USERNAME: ${BOOTSTRAP_ADMIN_USERNAME}
      - BOOTSTRAP_ADMIN_PASSWORD: ${BOOTSTRAP_ADMIN_PASSWORD}
      # Add other required environment variables as needed
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

volumes:
  news-dashboard-postgres:
```

Create a `.env` file with your configuration:

```env
SESSION_SECRET=your-session-secret-here
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=your-secure-password-here
# Add other required variables as needed
```

Then start the stack:
```bash
docker compose up -d
```

## Image Tags and Versioning

The image is available with the following tags:

- `ghcr.io/lihor-hub/news-dashboard:latest` - Rolling update to the most recent release
- `ghcr.io/lihor-hub/news-dashboard:v<version>` - Specific version (e.g., `v1.21.0`)
- `ghcr.io/lihor-hub/news-dashboard:<commit-sha>` - Exact commit (e.g., `a1b2c3d4e5f6`)

For production deployments, we recommend pinning to a specific version or commit SHA to ensure consistency and prevent unexpected updates.

Example of pinning to a specific version:
```bash
docker run -d \
  # ... other options ...
  ghcr.io/lihor-hub/news-dashboard:v1.21.0
```

Or pinning to a commit SHA:
```bash
docker run -d \
  # ... other options ...
  ghcr.io/lihor-hub/news-dashboard:a1b2c3d4e5f67890
```

## Configuration

See the [README Configuration section](../README.md#configuration) for the complete list of environment variables.

**Important**: Never commit secrets to version control. Use environment variables or a `.env` file (not committed to Git) to manage sensitive values like:
- `SESSION_SECRET`
- `BOOTSTRAP_ADMIN_PASSWORD`
- `POSTGRES_PASSWORD`
- API keys for AI features (`OPENAI_API_KEY`, `FREE_LLM_API_KEY`, etc.)

## Health Check

Verify your instance is healthy:
```bash
curl http://localhost:8080/api/health
# Should return: {"status":"ok"}

curl http://localhost:8080/api/health/details
# Returns detailed health information
```

## Upgrading

To upgrade to a newer version:

1. Pull the new image: `docker pull ghcr.io/lihor-hub/news-dashboard:<new-tag>`
2. Stop the current container: `docker stop news-dashboard`
3. Remove the container: `docker rm news-dashboard`
4. Start the new container with the same configuration
5. Run database migrations if needed: `docker run --rm --link news-dashboard-postgres:postgres -e POSTGRES_HOST=postgres -e POSTGRES_PORT=5432 -e POSTGRES_DB=news_dashboard -e POSTGRES_USER=news_dashboard -e POSTGRES_PASSWORD=your-password ghcr.io/lihor-hub/news-dashboard:<new-tag> news-dashboard init`

## Backups

Regularly back up your PostgreSQL database. See [POSTGRES_BACKUP.md](./POSTGRES_BACKUP.md) for backup strategies.

## Next Steps

- Consider setting up HTTPS with a reverse proxy (see [CADDY_HTTPS_SETUP.md](./CADDY_HTTPS_SETUP.md))
- Configure optional features like AI capabilities, Keycloak SSO, or Web Push notifications
- Set up regular backups of your PostgreSQL data