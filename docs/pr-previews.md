# PR previews and the staging demo backend

Pull-request previews of the frontend talk to a shared staging backend at
`https://stage.news.lihor.ro`. That backend runs the regular application image
in `DEMO_MODE`: it seeds deterministic sample articles and a read-only guest
account on startup.

Production (`news.lihor.ro`, [`values-production.yaml`](../helm/news-dashboard/values-production.yaml))
is unaffected. It keeps its own release, namespace, and values, and the
operator deploys it by hand.

## Frontend Node.js compatibility

The root frontend supports Node 24.18+ and Node 26. Vercel uses the latest
supported Node 24 release selected by the root `package.json` engine range;
CI's primary frontend lane and the production image remain on Node 26.
A separate **Frontend compatibility (Node 24)** job verifies engine-strict
installation, typechecking, frontend tests, and the production build. Its
result is included in the required **Test & build** check.

Do not bypass engine checks to make a preview deploy. If Vercel reports an
unsupported Node version, check the deployment log and the root package and
lockfile engine ranges. A green frontend build verifies Node compatibility;
it does not by itself verify the preview's backend connectivity.

## Staging backend

[`values-staging.yaml`](../helm/news-dashboard/values-staging.yaml) layers on
the chart defaults:

| Setting | Staging value |
|---------|---------------|
| Host / TLS | `stage.news.lihor.ro`, Traefik, Secret `news-dashboard-stage-tls` |
| Image | `ghcr.io/lihor-hub/news-dashboard:latest` (the floating tag from `main`), `pullPolicy: Always` |
| Auth | local password auth, no Keycloak |
| Data | `app.config.demoMode: true` → `DEMO_MODE`; ephemeral Postgres (`emptyDir`), reseeded on restart |
| Extras | no backups, no Neo4j, small resource limits |
| Preview origins | `app.config.csrfTrustedOriginRegex` → `CSRF_TRUSTED_ORIGIN_REGEX` (see [Security notes](#security-notes)) |

### Operator runbook

1. **DNS**: create an `A`/`AAAA` (or `CNAME`) record for
   `stage.news.lihor.ro` pointing at the same ingress endpoint as
   `news.lihor.ro`.
2. **TLS**: provision the `news-dashboard-stage-tls` Secret in the
   `news-dashboard-stage` namespace the same way production's
   `news-dashboard-tls` is provisioned, covering `stage.news.lihor.ro`.
3. **Image pull**: if the GHCR package is private, copy `ghcr-pull-secret`
   into the `news-dashboard-stage` namespace.
4. **Install or upgrade**:

   ```bash
   kubectl create namespace news-dashboard-stage --dry-run=client -o yaml | kubectl apply -f -
   helm upgrade --install news-dashboard-stage helm/news-dashboard \
     -n news-dashboard-stage \
     -f helm/news-dashboard/values-staging.yaml \
     --set-string app.auth.sessionSecret="$(openssl rand -hex 32)" \
     --set-string postgresql.password="$(openssl rand -hex 24)"
   ```

   Reuse the same secrets on later upgrades (for example from a local,
   uncommitted values file). A new `sessionSecret` only logs out existing
   sessions. Postgres is ephemeral, so a new password is harmless.
5. **Pick up a newer `main` image**:
   `kubectl -n news-dashboard-stage rollout restart deploy/news-dashboard-stage`.
6. **Check**: `curl -fsS https://stage.news.lihor.ro/api/ready`. Then sign in
   at `https://stage.news.lihor.ro/login` as `guest` / `demo`.

## Security notes

- The guest account is read-only. The `reject_guest_writes` middleware rejects
  every unsafe request from a guest session except the login routes.
- Through a Vercel rewrite, the browser sends the preview's origin
  (`https://news-dashboard-…vercel.app`). The backend, however, sees Host
  `stage.news.lihor.ro`. The CSRF origin guard would otherwise reject
  cookie-authenticated mutations from previews. `CSRF_TRUSTED_ORIGIN_REGEX`
  adds a full-match allowlist for those origins. It is unset by default, and
  only `values-staging.yaml` sets it, restricted to this project's preview
  hostnames under the Vercel scope `ioachim-lihors-projects`. If the Vercel
  project moves to another scope, update the regex. The pattern is defense in depth,
  not the primary control. A project in another Vercel account could claim a
  matching `*.vercel.app` alias, but `SameSite=Strict` already keeps the
  staging cookie off cross-site requests. The worst case is staging-only and
  limited to a read-only demo.
- The session cookie is host-only (no `Domain`), `Secure`, and
  `SameSite=Strict`. Through the rewrite it is stored for the preview host,
  and `vercel.app` is on the Public Suffix List. As a result, other Vercel
  sites are cross-site and never receive it.
