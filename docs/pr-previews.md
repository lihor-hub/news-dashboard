# PR previews and the staging demo backend

Pull-request previews of the frontend talk to a shared staging backend at
`https://stage.news.lihor.ro`. That backend runs the regular application image
in `DEMO_MODE`: it seeds deterministic sample articles and a read-only guest
account on startup.

Production (`news.lihor.ro`, [`values-production.yaml`](../helm/news-dashboard/values-production.yaml))
is unaffected. It keeps its own release, namespace, and values, and the
operator deploys it by hand.

## For contributors

- Each PR that touches the frontend gets a **Vercel** preview link from the
  Vercel bot. Sign in with `guest` / `demo`.
- The preview is **read-only**: saving, starring, settings changes, and other
  writes return `403 Guest accounts cannot modify data`.
- Only the frontend is built from your branch. `/api`, `/auth`, and `/email`
  are proxied to the staging backend, which runs the latest `main` image. If
  your PR changes the API or the backend, the preview won't show that. Verify
  it locally (`docker compose -f docker-compose.demo.yml up` or the
  [development setup](../CONTRIBUTING.md#development-setup)).
- PRs that change no frontend files (`frontend/`, `public/`, `index.html`,
  `package*.json`, `vite.config.ts`, `tsconfig*.json`, the build check
  scripts, `vercel.json`) skip the preview build.
- Data is shared and reset whenever staging restarts. Don't expect anything to
  persist.

## Vercel project

[`vercel.json`](../vercel.json) uses Vercel
[Services](https://vercel.com/docs/services) with a single static `app`
service. It runs `npm run build` and serves `frontend/dist`. Its rewrites
proxy `/api/*`, `/auth/*`, and `/email/*` to `https://stage.news.lihor.ro`,
then fall back to `/index.html` for SPA routes. `git.deploymentEnabled.main`
is `false`, so Vercel never deploys `main`. Production lives on Kubernetes.

The Vercel project is `news-dashboard` in the `ioachim-lihors-projects` scope.
To set it up again (Vercel dashboard):

1. **Add New → Project**, import `lihor-hub/news-dashboard` through the Vercel
   GitHub App. Keep the root directory at the repository root. The framework
   (Vite), build command, and output come from `vercel.json`. Leave the
   dashboard build overrides off.
2. Set **Node.js Version** to the newest offered (24.x). See the note below.
3. No environment variables are needed. The SPA calls relative `/api` paths.
4. Optional: in GitHub branch protection, make the **Vercel** status check
   required.
5. Preview hostnames must match `app.config.csrfTrustedOriginRegex` in
   `values-staging.yaml` (scope `ioachim-lihors-projects`). If the project
   moves scope, update it and `helm upgrade` staging.

> **Node.js version:** `package.json` pins `engines.node` to `>=26 <27`, but
> Vercel's build image offers Node.js 24.x and 22.x. If Vercel rejects the
> engines range, the preview build fails until that is resolved. The frontend
> build itself succeeds on Node 22/24.

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
