---
title: Upgrading and rolling back
sidebar_position: 5
---

# Upgrading and rolling back

## Upgrading

Upgrade safely by following these steps in order.

### Pre-Upgrade Checklist

1. **Read the release notes** — check the [CHANGELOG](https://github.com/lihor-hub/news-dashboard/releases) for any breaking changes, config deprecations, or manual steps.
2. **Back up your database** — a backup is your safety net for rollback. See [PostgreSQL Backup and Restore](../configuration/postgres-backup.md) for backup strategies.
3. **Back up app data** — if audio features are enabled, keep the `/data` volume (`news-dashboard-data` in Docker Compose) with your normal backup set so generated MP3 caches survive container replacement.
4. **Check the new image tag** — browse available tags on [GHCR](https://ghcr.io/lihor-hub/news-dashboard) or the [releases page](https://github.com/lihor-hub/news-dashboard/releases).

### Docker Compose (Production)

```bash
# 1. Pull the new image
docker compose -f docker-compose.prod.yml pull

# 2. Restart the stack
docker compose -f docker-compose.prod.yml up -d

# 3. Run database migrations if needed
# The app runs init_db() on startup automatically, but if release notes
# mention a manual migration step, run it explicitly:
docker compose -f docker-compose.prod.yml run --rm news-dashboard news-dashboard init
```

### Kubernetes (Helm)

Use the [chart README](https://github.com/lihor-hub/news-dashboard/blob/main/helm/news-dashboard/README.md) for prerequisites, a
minimal installation, and the values reference. The following flow upgrades
the repository-specific production deployment.

Use the published OCI chart pinned to an application release version (without
its `v` prefix). The chart package uses the corresponding commit-SHA image by
default; production still requires `image.digest` as shown below. See the
[chart versioning policy](https://github.com/lihor-hub/news-dashboard/blob/main/helm/news-dashboard/README.md#versioning-policy).
To deploy the chart from your checkout, replace the OCI reference and
`--version` with `./helm/news-dashboard`.

```bash
(
set -euo pipefail
CHART_VERSION="${CHART_VERSION:?set CHART_VERSION to the published chart version}"
IMAGE_DIGEST="${IMAGE_DIGEST:?set IMAGE_DIGEST to sha256:<64 lowercase hex>}"
# 1. Deploy the exact published image manifest
: "${SESSION_SECRET:?set SESSION_SECRET}"
: "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}"
: "${POSTGRES_HOST_PATH:?set POSTGRES_HOST_PATH}"
source ./scripts/production-deploy-lib.sh
production_cutover_enabled || { echo "Ingress cutover is not enabled" >&2; exit 2; }
prepare_production_helm_secret_files

helm upgrade news-dashboard oci://ghcr.io/lihor-hub/charts/news-dashboard \
  --version "$CHART_VERSION" \
  --namespace news-dashboard --create-namespace \
  --values ./helm/news-dashboard/values-production.yaml \
  --set-string image.digest="${IMAGE_DIGEST}" \
  --set-string postgresql.persistence.hostPath="$POSTGRES_HOST_PATH" \
  --set-file app.auth.sessionSecret="$PRODUCTION_SESSION_SECRET_FILE" \
  --set-file postgresql.password="$PRODUCTION_POSTGRES_PASSWORD_FILE" \
  --reuse-values

# 2. Rollout restarts the deployment automatically.
#    The app runs init_db() on startup.
kubectl -n news-dashboard rollout status deployment/news-dashboard
)
```

See the [chart values reference](https://github.com/lihor-hub/news-dashboard/blob/main/helm/news-dashboard/README.md#values-reference)
for structured runtime configuration and Secret references.

The optional Dify iframe assistant is configured separately under `app.dify`: set
`app.dify.enabled`, `app.dify.baseUrl`, and `app.dify.title`, and provide the
Publish → Embed token via `app.dify.existingSecret` and
`app.dify.appTokenKey`. The chart requires the base URL and Secret when
enabled, and never accepts a Dify service/API key. See the [Dify assistant
guide](../configuration/dify-assistant.md) for an example.

Newsletter IMAP ingest can also be enabled through structured Helm values.
Create a Secret for mailbox credentials, then set the non-secret mailbox
options on `app.newsletter`:

```bash
kubectl -n news-dashboard create secret generic newsletter-imap \
  --from-literal=NEWSLETTER_IMAP_USERNAME='inbox@example.com' \
  --from-literal=NEWSLETTER_IMAP_PASSWORD='replace-with-real-password'

helm upgrade news-dashboard ./helm/news-dashboard \
  --reuse-values \
  --set app.newsletter.imapHost=imap.example.com \
  --set app.newsletter.imapPort=993 \
  --set app.newsletter.imapFolder=INBOX \
  --set app.newsletter.pollMinutes=15 \
  --set app.newsletter.maxMessageBytes=10485760 \
  --set app.newsletter.existingSecret=newsletter-imap
```

When `app.newsletter.imapHost` is empty, the chart does not render newsletter
IMAP env vars and the scheduler does not start the mailbox poller.

Neo4j is available as an optional Helm-managed graph store. See
[Optional Graph Storage](deployment.md#optional-graph-storage) for the values and backfill
commands.

### Migration / Schema Updates

The app calls `init_db()` on every startup, which creates missing tables and
indexes. Schema changes that require a migration step (add column, data
transformation) are documented in the [CHANGELOG](https://github.com/lihor-hub/news-dashboard/releases) release notes
with the exact command to run:

```bash
# Example manual migration step (if release notes call for it):
docker compose -f docker-compose.prod.yml run --rm news-dashboard news-dashboard init
```

If you see a startup error related to a missing column or table, running
`news-dashboard init` (or restarting the container, which calls `init_db`)
typically resolves it.

## Rolling Back

If an upgrade causes issues, roll back using the database backup and the
previous image digest:

```bash
# 1. Stop the new stack
docker compose -f docker-compose.prod.yml down

# 2. Restore the database from your pre-upgrade backup
#    (see the PostgreSQL Backup and Restore guide linked below)

# 3. Set IMAGE_DIGEST in .env to the previously recorded sha256 digest

# 4. Start the previous version
docker compose -f docker-compose.prod.yml up -d
```

Use [PostgreSQL Backup and Restore](../configuration/postgres-backup.md) for
the database restore step.

For an application-only Helm revision rollback, restore the recorded revision
while leaving the current edge unchanged, then verify health before changing
traffic. For the Ingress-to-Caddy edge rollback, do not use `helm rollback`
alone: first restore a guard-compatible NodePort backend, verify it locally,
prepare the saved Caddy application route, release the Ingress listener, start
and verify Caddy locally, and only then reverse DNS or port forwarding. Follow
the exact ordered procedure in
[Ingress HTTPS and Caddy migration](../configuration/https-caddy.md#roll-back).

Rollback is the reason backups are important — always back up the database
**before** starting an upgrade (see the [Pre-Upgrade Checklist](#pre-upgrade-checklist)).

## Backups

Regularly back up your PostgreSQL database. See [PostgreSQL Backup and Restore](../configuration/postgres-backup.md) for:

- Enabling the Helm CronJob backup
- Manual backup and restore procedures
- Verifying dump integrity
- Retention policy configuration

> **Always back up before an upgrade** — this is your rollback path.
