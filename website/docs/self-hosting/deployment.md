---
title: Deployment
sidebar_position: 1
---

# Deployment

**Note**: The GHCR package must be made public (or accessible via pull secret) for this to work.

> This is a one-time maintainer action: go to the repository's Packages settings,
> select the `ghcr.io/lihor-hub/news-dashboard` package, and change its visibility to Public.
> If the package stays private, configure the production `GHCR_TOKEN` Actions
> secret with `read:packages` so CI can create the cluster pull secret. Public
> packages do not need `GHCR_TOKEN`; the deploy workflow leaves
> `image.pullSecretName` empty in that mode.

## Docker Compose: Dev vs Production

The repository provides two Docker Compose files:

| File                      | Purpose                                                                     |
| ------------------------- | --------------------------------------------------------------------------- |
| `docker-compose.yml`      | Local development only (builds from source, insecure dev defaults)          |
| `docker-compose.prod.yml` | Production deployment (uses published image, requires secure configuration) |

> **Warning**: Never use `docker-compose.yml` for production. It contains insecure defaults suitable only for local development.

## Running with Docker Compose (Production)

### Prerequisites

- Docker or container runtime
- Required environment variables (see [Environment variables](environment-variables.md))

### Step 1: Create Environment File

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
# Edit .env with your secure values
```

See [Environment variables](environment-variables.md) for configuration options.

### Step 2: Start the Stack

```bash
docker compose -f docker-compose.prod.yml up -d
```

The compose file will fail fast if `IMAGE_DIGEST` or required secrets
(`SESSION_SECRET`, `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`,
`POSTGRES_PASSWORD`, `NEO4J_PASSWORD`) are not set.

`docker-compose.prod.yml` also mounts the named `news-dashboard-data` volume at
`/data` and sets `DATA_DIR=/data`. Generated article audio and briefing podcast
MP3 caches live under `/data/audio`, so keep that volume backed by persistent
storage in production. If you run the container manually with `docker run`, pass
both `-e DATA_DIR=/data` and `-v news-dashboard-data:/data`; otherwise audio
files are lost when the app container is recreated.

The production Compose stack also starts a bundled `neo4j:5-community`
container and injects `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and
`NEO4J_DATABASE=neo4j` into the app so the knowledge graph is enabled by
default. After first start, backfill existing cached entities:

```bash
docker compose -f docker-compose.prod.yml exec news-dashboard \
  news-dashboard graph-backfill --limit 250 --days 30
docker compose -f docker-compose.prod.yml exec news-dashboard \
  news-dashboard graph-relationship-backfill --limit 50 --days 7
```

### Verifying the Deployment

```bash
# Check service status
docker compose -f docker-compose.prod.yml ps

# Check health endpoint
curl http://localhost:8080/api/health
# Should return: {"status":"ok"}
```

## Supported Architectures

Published `latest` and commit-SHA image tags contain both `linux/amd64` (x86-64)
and `linux/arm64` (AArch64) images. Docker Compose and Kubernetes automatically
select the image matching the host. ARM64 includes Apple Silicon Linux VMs,
ARM servers, and Raspberry Pi devices running a **64-bit** OS; 32-bit ARMv7
is not supported.

Inspect the index and its platform-specific digests before pinning a deployment:

```bash
docker buildx imagetools inspect ghcr.io/lihor-hub/news-dashboard:latest
```

Pinning the index digest preserves automatic architecture selection. Each
architecture has its own SPDX SBOM attested to its child image digest; build
provenance is attested to the complete index digest. Use the corresponding child
digest when verifying an architecture's SBOM, rather than the index digest.

Maintainers can select `validate_multiarch_images` in the **CI / CD** workflow's
manual-run inputs to build local OCI archives on a GitHub-hosted runner without
publishing or deploying. The `multiarch-validation` artifact records both child
digests, digest-verified SBOM/provenance statements, and amd64-versus-multiarch
build times. Both timed builds disable layer reuse, although the second can reuse
downloaded base images. The frontend builds on the builder's native platform;
only target-dependent runtime steps require ARM64 emulation on an x86-64 runner.

## Image Tags and Versioning

The image is available with the following tags:

- `ghcr.io/lihor-hub/news-dashboard:latest` - Rolling update to the most recent release
- `ghcr.io/lihor-hub/news-dashboard:<commit-sha>` - Exact commit (e.g., `a1b2c3d4e5f6`)

For production deployments, resolve the published manifest digest and set
`IMAGE_DIGEST=sha256:<64 lowercase hex characters>`. Tags and commit-SHA tags
are useful discovery aliases, but the production entry points deploy the digest.

### Selecting the production Compose image

`docker-compose.prod.yml` requires `IMAGE_DIGEST` and builds the reference as
`ghcr.io/lihor-hub/news-dashboard@${IMAGE_DIGEST}`.

Then pull and restart:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### Verifying Image Provenance and SBOM

Every image pushed to GHCR from a push to `main` is attested with a
[SLSA build provenance](https://slsa.dev/) statement and a signed SBOM
(SPDX), generated in `.github/workflows/ci.yml` and verifiable with the
[GitHub CLI](https://cli.github.com/):

From a checkout of a published `main` commit, resolve its SHA tag once, then
verify immutable references. This example selects ARM64; use `amd64` for x86-64.
It requires Docker Buildx, `jq`, and an authenticated GitHub CLI.

```bash
IMAGE=ghcr.io/lihor-hub/news-dashboard
COMMIT_SHA=$(git rev-parse HEAD)
ARCH=arm64
INDEX_DIGEST=$(docker buildx imagetools inspect "$IMAGE:$COMMIT_SHA" \
  --format '{{json .Manifest}}' | jq -er '.digest')

# Verify the complete index was built by this repository's CI.
gh attestation verify "oci://$IMAGE@$INDEX_DIGEST" \
  --repo lihor-hub/news-dashboard

# Resolve and verify the selected architecture's SBOM.
CHILD_DIGEST=$(docker buildx imagetools inspect "$IMAGE@$INDEX_DIGEST" --raw | \
  jq -er --arg arch "$ARCH" \
    '.manifests[] | select(.platform.os == "linux" and .platform.architecture == $arch) | .digest')
gh attestation verify "oci://$IMAGE@$CHILD_DIGEST" \
  --repo lihor-hub/news-dashboard --predicate-type https://spdx.dev/Document
```

Both verification commands exit non-zero if the digest lacks a matching signed
attestation from this repository or the signature cannot be verified against
GitHub's Sigstore-backed OIDC identity.

## Production Helm quick start

For a minimal Kubernetes installation and the full values reference, see the
[chart README](https://github.com/lihor-hub/news-dashboard/blob/main/helm/news-dashboard/README.md).
The following recipe targets the repository-specific production deployment.

The production Helm contract terminates application TLS at the Ingress and
keeps the application Service private:

```bash
(
set -euo pipefail
IMAGE_DIGEST="${IMAGE_DIGEST:?set IMAGE_DIGEST to sha256:<64 lowercase hex>}"
: "${SESSION_SECRET:?set SESSION_SECRET}"
: "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}"
: "${POSTGRES_HOST_PATH:?set POSTGRES_HOST_PATH}"
source ./scripts/production-deploy-lib.sh
production_cutover_enabled || { echo "Ingress cutover is not enabled" >&2; exit 2; }
prepare_production_helm_secret_files

helm upgrade --install news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard --create-namespace \
  --values ./helm/news-dashboard/values-production.yaml \
  --set-string image.digest="${IMAGE_DIGEST}" \
  --set-string postgresql.persistence.hostPath="$POSTGRES_HOST_PATH" \
  --set-file app.auth.sessionSecret="$PRODUCTION_SESSION_SECRET_FILE" \
  --set-file postgresql.password="$PRODUCTION_POSTGRES_PASSWORD_FILE"
)
```

Supply secrets and installation-specific persistence at runtime. Do not commit
them to a values file or pass their values through Helm's `--set` arguments.
The shared helper uses protected temporary files and removes them on exit.
Private/custom endpoints require a policy-only strict JSON additional-egress
values file. Use `deploy/additional-egress-values.example.json` as the shape and
persist it through `ADDITIONAL_EGRESS_VALUES_FILE` for manual deploys or the
production GitHub environment variable `ADDITIONAL_EGRESS_VALUES` for CI. Never
put credentials in this non-secret NetworkPolicy input. YAML-only syntax,
aliases, merge keys, comments, and multiple documents are rejected.
Before public cutover, verify the ClusterIP Service, TLS Ingress, backups and
restore, rollback revision, and the existing `/keycloak` route. Caddy cannot
share ports 80 and 443 with the ingress controller.

The live appliance procedure requires human access and is tracked in
[issue #1302](https://github.com/lihor-hub/news-dashboard/issues/1302). Follow
[Ingress HTTPS and Caddy migration](../configuration/https-caddy.md) for the
staged verification and backend-first rollback order. Leave
`INGRESS_CUTOVER_ENABLED` unset until that procedure is ready; the main workflow
will publish and scan without touching the live release.

## Production Kubernetes Ingress

The production architecture is:

```text
Internet → TLS Ingress → ClusterIP Service → News Dashboard
```

Use `helm/news-dashboard/values-production.yaml`. It enables the hostname and
TLS Ingress, restricts the application Service to `ClusterIP`, and enables
NetworkPolicies for the configured ingress-controller selectors. Caddy is not
the application TLS source of truth. The repository Caddyfile retains only the
legacy same-host Keycloak route so its separate migration boundary stays
visible.

The public egress policy allows HTTPS and standard authenticated mail ports only
to globally routable addresses. Private/custom endpoints require
`networkPolicy.additionalEgress`. Copy
`deploy/additional-egress-values.example.json` to a protected operator path and
set `ADDITIONAL_EGRESS_VALUES_FILE` on every manual deployment. For CI, store
the same policy-only strict JSON in the production environment variable
`ADDITIONAL_EGRESS_VALUES`; it persists across Helm upgrades and must not
contain credentials. YAML-only syntax, aliases, merge keys, comments, and
multiple documents are rejected.

Live appliance installation and cutover are intentionally not automated from
pull-request CI. Complete the DNS/TLS, ingress-controller, firewall, Keycloak,
and rollback rehearsal in
[human rollout issue #1302](https://github.com/lihor-hub/news-dashboard/issues/1302).
Do not add credentials or private inventory to that issue or this repository.
The detailed staged procedure is in
[Ingress HTTPS and Caddy migration](../configuration/https-caddy.md).
Until that procedure is ready, leave `INGRESS_CUTOVER_ENABLED` unset: main CI
will still build, publish, and scan the image but will exit before any live
release or cluster mutation. Set it to exactly `true` only in the approved
cutover window.

Before removing the old application route:

1. Back up PostgreSQL and verify a restore on a separate instance.
2. Save the current Helm revision and live Caddy configuration.
3. Configure the production `POSTGRES_HOST_PATH` runtime variable for the
   existing data directory, then stage the production values. Verify the
   Ingress through its target address while preserving the public hostname and
   TLS validation.
4. Prepare and rehearse rollback to the previous Helm revision and Caddy route.
5. Preserve the existing Keycloak route behind an equivalent higher-priority
   Ingress route. Verify its login and callback flow.
6. Only then make the ingress controller the sole owner of ports 80 and 443.

### Host PostgreSQL controls

When Kubernetes connects to PostgreSQL running on the host, the database must
be reachable from the selected cluster network without becoming a public
service:

- Set PostgreSQL `listen_addresses` to the specific host or cluster-facing
  interface. Avoid `*`; if it is temporarily unavoidable, the firewall and
  `pg_hba.conf` rules below must still restrict every connection.
- Add the narrowest `pg_hba.conf` `hostssl` rule for the application database,
  role, and actual pod or node source CIDR. Use `scram-sha-256`; never use
  `trust` or a public `0.0.0.0/0` rule.
- Restrict the host firewall to TCP 5432 from that same cluster source network.
  Confirm expected connections succeed and connections from an unrelated
  network are denied.
- Enable PostgreSQL TLS with operator-managed server certificates and protect
  the private key with PostgreSQL-readable file permissions. Configure the
  application DSN with certificate verification (`sslmode=verify-full` and the
  trusted CA) when names and certificates are available; do not commit
  certificate material.
- Keep encrypted, access-controlled backups outside the database host and
  define retention for both logical dumps and any WAL/base-backup strategy.
- Perform restore verification regularly: restore a current backup into an
  isolated PostgreSQL instance, run integrity/application queries, and confirm
  `/api/ready` succeeds against the restored copy before calling the backup
  usable.

After the cutover, inspect the PostgreSQL listener, `pg_hba.conf`, firewall,
TLS negotiation, backup job, and most recent restore verification as one
control set. Record sanitized evidence in issue #1302.

## Optional Graph Storage

Neo4j support is off by default. In Helm installs, set `neo4j.enabled=true` to
render a Neo4j StatefulSet, ClusterIP Service, credentials Secret, and
persistent storage. The app still requires PostgreSQL for primary data storage.

The most common values are:

```yaml
neo4j:
  enabled: true
  auth:
    user: neo4j
    password: 'replace-with-a-long-random-password'
  persistence:
    size: 10Gi
    storageClassName: fast-storage
```

Use `neo4j.auth.existingSecret` and `neo4j.auth.passwordKey` when credentials
are managed outside Helm. The Secret must also include `NEO4J_AUTH` in
`<user>/<password>` form so the Neo4j container can initialize authentication.

For a chart-managed Neo4j Secret, pass a password at install or upgrade time:

```bash
helm upgrade news-dashboard ./helm/news-dashboard \
  --reuse-values \
  --set neo4j.enabled=true \
  --set neo4j.auth.user=neo4j \
  --set-string neo4j.auth.password='replace-with-a-long-random-password'
```

For a pre-existing Secret, create the password key used by the app and
`NEO4J_AUTH` used by the Neo4j container:

```bash
kubectl -n news-dashboard create secret generic news-dashboard-neo4j-auth \
  --from-literal=NEO4J_PASSWORD='replace-with-a-long-random-password' \
  --from-literal=NEO4J_AUTH='neo4j/replace-with-a-long-random-password'

helm upgrade news-dashboard ./helm/news-dashboard \
  --reuse-values \
  --set neo4j.enabled=true \
  --set neo4j.auth.existingSecret=news-dashboard-neo4j-auth \
  --set neo4j.auth.user=neo4j \
  --set neo4j.auth.passwordKey=NEO4J_PASSWORD
```

Persistent storage is enabled by default when Neo4j is enabled. Tune it with
`neo4j.persistence.size`, `neo4j.persistence.storageClassName`,
`neo4j.persistence.existingClaim`, or `neo4j.persistence.hostPath`; set
`neo4j.persistence.enabled=false` only for disposable test installs.
