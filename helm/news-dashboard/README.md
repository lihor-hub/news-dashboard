# News Dashboard Helm chart

Deploy the application and, optionally, PostgreSQL, scheduled ingestion, and
logical database backups. PostgreSQL is required; Neo4j is an optional graph
store and does not replace it.

## Prerequisites

- A Kubernetes cluster, `kubectl` access, and Helm 3 or later
- A checkout of this repository; run the example from the repository root
- Access to the application image in GHCR, with a `kubernetes.io/dockerconfigjson`
  Secret in the release namespace if the package requires authentication
- A default StorageClass for the PVC-based example below, or an explicit
  `postgresql.persistence.storageClassName`
- An ingress controller and DNS/TLS configuration if enabling Ingress

The defaults include deployment-specific settings: Keycloak is enabled,
`image.pullSecretName` is `ghcr-pull-secret`, and PostgreSQL uses a host path.
Override these for your cluster. The example below uses local-password login,
a PVC, and port forwarding.

## Install or upgrade

Prepare files containing a long random session secret, a PostgreSQL password,
and bootstrap administrator credentials outside the repository. Set
`SESSION_SECRET_FILE`, `POSTGRES_PASSWORD_FILE`, `ADMIN_USERNAME_FILE`, and
`ADMIN_PASSWORD_FILE` to their paths. Restrict their permissions to the owner;
do not commit them. Keep the session secret and database password stable across
upgrades unless performing an intentional rotation.

Choose the published application release version, without its `v` prefix, for
`CHART_VERSION`. The OCI chart uses that release's exact application commit as
its default image tag.

```bash
CHART_VERSION="${CHART_VERSION:?set CHART_VERSION to the published chart version}"
kubectl create namespace news-dashboard --dry-run=client -o yaml | kubectl apply -f -
kubectl --namespace news-dashboard create secret generic news-dashboard-admin \
  --from-file=BOOTSTRAP_ADMIN_USERNAME="$ADMIN_USERNAME_FILE" \
  --from-file=BOOTSTRAP_ADMIN_PASSWORD="$ADMIN_PASSWORD_FILE" \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install news-dashboard oci://ghcr.io/lihor-hub/charts/news-dashboard \
  --version "$CHART_VERSION" \
  --namespace news-dashboard --create-namespace \
  --set app.auth.keycloak.enabled=false \
  --set-string app.auth.bootstrapAdmin.existingSecret=news-dashboard-admin \
  --set-string app.publicBaseUrl=http://localhost:8080 \
  --set-string postgresql.persistence.hostPath= \
  --set-file app.auth.sessionSecret="$SESSION_SECRET_FILE" \
  --set-file postgresql.password="$POSTGRES_PASSWORD_FILE"
```

For source builds, replace the OCI reference and `--version` argument with
`./helm/news-dashboard`. This uses the chart in your checkout.

Create the `ghcr-pull-secret` image-pull Secret in the same namespace before
installing. If your chosen image is publicly pullable, explicitly set
`image.pullSecretName` to an empty string instead. For a specific published
image, set `image.digest` to its `sha256:` manifest digest or override `image.tag`.

The install notes print the service address and port-forward command. With the
release name above, the application Service is
`news-dashboard-news-dashboard`. Bootstrap credentials create an administrator
only when the database has no users; changing the Secret does not reset an
existing account's password.

For public access, configure Ingress and set `app.publicBaseUrl` to the actual
browser-facing URL. The repository's [production overlay](values-production.yaml)
has additional TLS, digest, service, and network-policy safeguards. Follow the
[production deployment runbook](../../docs/SELF_HOSTING.md#kubernetes-helm)
before applying it; the minimal example above does not enable production mode.

## Versioning policy

Published chart `version` and `appVersion` both equal the application release
version, without the `v` prefix. A chart configuration fix should use a `fix:`
commit (or `feat:` for new behavior) so the normal release workflow produces a
new version. Documentation-only changes wait for the next application release.
Do not commit generated version bumps: the tracked metadata is the source
fallback, and CI injects the release version only into the packaged chart.

The package's default image tag is the exact commit behind the release tag.
Production installations still supply an immutable registry `image.digest`.
The image pipeline publishes `latest` and commit-SHA tags; the chart does not
assume a `v<version>` image tag exists.

The release job waits up to 30 minutes for that commit's image, then packages
and pushes `news-dashboard-<version>.tgz` to `oci://ghcr.io/lihor-hub/charts`.
An unavailable image fails the job without publishing its chart. If this wait
times out, fix or finish image publication and rerun the failed release job;
rerunning the entire release workflow finds the existing tag and creates no
new release.

## Values reference

Defaults below describe the source [values.yaml](values.yaml). Published
packages replace `image.tag` with the exact release commit as described above.
Keep installation-specific settings in your own values file and secrets outside
version control. The full
file also documents security contexts, resources, and optional integrations.

| Value | Default | Purpose |
|-------|---------|---------|
| `image.repository` | `ghcr.io/lihor-hub/news-dashboard` | Application image repository. |
| `image.tag` | Pinned commit in `values.yaml` | Used when no digest is set. |
| `image.digest` | `""` | Overrides tag; a valid `sha256:` digest is required in production. |
| `image.pullPolicy` | `IfNotPresent` | Kubernetes image pull policy. |
| `image.pullSecretName` | `ghcr-pull-secret` | Existing registry Secret; empty only for publicly pullable images. |
| `service.type` | `ClusterIP` | Production requires ClusterIP; NodePort/LoadBalancer are available outside production. |
| `service.port` | `8080` | Application Service port. |
| `service.nodePort` | `""` | Optional fixed NodePort when type is NodePort. |
| `app.publicBaseUrl` | `""` | Browser-facing absolute URL for outbound links; configure for email delivery. |
| `app.auth.sessionSecret` | `""` | Required session-signing secret; pass with `--set-file`. |
| `app.auth.keycloak.enabled` | `true` | Disable for local-password authentication. |
| `app.auth.bootstrapAdmin.existingSecret` | `""` | Existing Secret for initial local administrator credentials. |
| `app.postgresExternal.host` | `""` | External PostgreSQL host when bundled PostgreSQL is disabled. |
| `app.postgresExternal.port` | `5432` | External PostgreSQL port. |
| `app.postgresExternal.database` | `""` | External database name. |
| `app.postgresExternal.username` | `""` | External database role. |
| `app.postgresExternal.passwordSecretName` | `""` | Existing Secret holding the external database password. |
| `app.postgresExternal.passwordSecretKey` | `POSTGRES_PASSWORD` | Password key in that Secret. |
| `app.databaseUrl.existingSecret` | `""` | Alternative Secret holding a complete PostgreSQL connection URL. |
| `app.databaseUrl.key` | `DATABASE_URL` | Connection URL key. |
| `postgresql.enabled` | `true` | Deploy bundled PostgreSQL. |
| `postgresql.password` | `""` | Required for bundled PostgreSQL; pass with `--set-file`. |
| `postgresql.database` / `postgresql.username` | `news_dashboard` | Bundled database and role. |
| `postgresql.persistence.enabled` | `true` | Use a PVC when hostPath is empty. |
| `postgresql.persistence.hostPath` | `/home/ioachim-minipc/news-dashboard-postgres-data` | Single-node storage; overrides PVC selection. Clear for PVC storage. |
| `postgresql.persistence.size` | `2Gi` | Requested PVC size. |
| `postgresql.persistence.storageClassName` | `""` | Empty uses the cluster's default StorageClass. |
| `postgresql.backup.enabled` | `false` | Enable bundled PostgreSQL logical-backup CronJob. |
| `postgresql.backup.schedule` | `0 2 * * *` | Daily backup schedule. |
| `postgresql.backup.retentionDays` | `7` | Retain logical dumps for this many days. |
| `postgresql.backup.hostPath` | `""` | Required backup directory when enabled; use a path separate from live data. |
| `ingestCronJob.enabled` | `true` | Deploy scheduled ingestion. |
| `ingestCronJob.schedule` | `17 */6 * * *` | Ingestion schedule. |
| `ingestCronJob.concurrencyPolicy` | `Forbid` | Prevent overlapping scheduled jobs. |
| `ingress.enabled` | `false` | Create an Ingress for `ingress.host`. |
| `ingress.host` | `news.lihor.ro` | Override with your hostname. |
| `ingress.className` | `""` | Ingress controller class. |
| `ingress.tls` | `[]` | TLS host/Secret entries. |
| `app.config.metricsEnabled` / `app.config.enableApiDocs` | `false` | Enable metrics or interactive API docs. |
| `app.config.analyticsRetentionDays` / `app.config.corsOrigins` | `""` | Override analytics retention or CORS origins. |
| `app.sentry.existingSecret` | `""` | Existing Secret containing optional Sentry DSNs. |

## External PostgreSQL

Set `postgresql.enabled=false`, then choose either all required
`app.postgresExternal` connection fields and password Secret, or
`app.databaseUrl.existingSecret` with a full PostgreSQL URL. Leave `app.postgresExternal.host` empty when using the URL Secret; a configured
external host takes precedence. The database must be reachable from application
and ingestion pods. Disabling the bundled database also disables its backup
CronJob; arrange backups with your external database operator.

## Validation

From the repository root, run `make helm-validate` to execute render checks,
lint the chart, and render default, production, and external-database variants.
