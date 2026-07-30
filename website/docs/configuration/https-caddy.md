---
title: Ingress HTTPS and Caddy migration
sidebar_position: 3
---

# Publish News Dashboard through the TLS Ingress

The production Helm contract publishes the application through a TLS-enabled
Kubernetes Ingress:

```text
Internet → ingress controller :443 → Ingress → ClusterIP Service → app :8080
```

`helm/news-dashboard/values-production.yaml` is the application routing source
of truth. It enables the Ingress for `news.lihor.ro`, requires the
`news-dashboard-tls` Secret, restricts the Service to `ClusterIP`, and enables
NetworkPolicies for the configured ingress-controller labels. Pull-request CI
lints and renders this contract without connecting to the production appliance.

Caddy is no longer the application's TLS or routing source of truth.
`deploy/Caddyfile` retains only the existing same-host `/keycloak` proxy as an
explicit migration boundary. Do not run Caddy and an ingress controller that
both bind host ports 80 and 443.

The live appliance work requires operator access to DNS, TLS, the host firewall,
and the existing identity provider. Track and record that work in
[human rollout issue #1302](https://github.com/lihor-hub/news-dashboard/issues/1302);
do not place appliance addresses, credentials, or certificate material in the
repository.

## Prerequisites

Before changing the public route:

- Confirm the cluster has an Ingress controller whose namespace and pod labels
  match `networkPolicy.ingressController` in the production values.
- Provision or validate the TLS Secret named by `ingress.tls[].secretName`.
- Confirm DNS can be moved to the Ingress endpoint and that ports 80 and 443
  will have only one owner after cutover.
- Export the current Helm values and note the current release revision.
- Back up PostgreSQL and complete a restore verification on a separate
  database or disposable instance.
- Save the live Caddy configuration outside the repository. The repository
  Caddyfile is Keycloak-only and is not an application rollback configuration.
- Decide how `/keycloak` will reach the existing identity provider after the
  Ingress takes ports 80 and 443. You must preserve the existing Keycloak route
  and test its health and OAuth redirect URI before moving application traffic.

Never expose the application Service temporarily to make testing easier. Use
the Ingress address with hostname and TLS validation.

## Render and inspect the Ingress

Do not apply the production overlay while the live Caddy route still depends on
the current release's backend. Render it without cluster access or activation:

```bash
./scripts/deploy-local-k8s.sh --render > /tmp/news-dashboard-production.yaml
```

Render mode uses dummy secret files and explicitly clears the legacy host path
to exercise the PVC branch. It never builds, pushes, or calls `kubectl`. Inspect
the result and render any installation-specific storage overlay separately
without committing its path.

For live apply, do not copy literal secrets into a values file, an issue, or
Helm's argument list. The shared helper writes exact secret bytes to mode-0600
temporary files, including commas, braces, backslashes, and embedded newlines,
then removes them on exit. Configure `POSTGRES_HOST_PATH` at runtime for the
existing host-backed PostgreSQL data. Both apply entry points fail before Helm
when it is missing, so a cutover cannot silently initialize an empty volume.

The production workflow defaults to publishing the image without applying this
overlay. Set `INGRESS_CUTOVER_ENABLED=true` only after every prerequisite,
staged check, Keycloak route, listener, and rollback check in issue #1302 is
ready. The local helper enforces the same gate for live apply;
`scripts/deploy-local-k8s.sh --render` renders the target manifests with dummy
secrets and an explicit PVC selection without requiring activation.

During the approved cutover window, apply through the gated workflow or local
helper. Then inspect the resources before changing the public route:

```bash
kubectl -n news-dashboard get service news-dashboard-news-dashboard \
  -o jsonpath='{.spec.type}{"\n"}'
kubectl -n news-dashboard get ingress news-dashboard-news-dashboard
kubectl -n news-dashboard describe ingress news-dashboard-news-dashboard
kubectl -n news-dashboard rollout status \
  deployment/news-dashboard-news-dashboard --timeout=120s
```

The Service must report `ClusterIP`. The Ingress must show the intended
hostname, TLS Secret, and controller class.

Test the staged controller without publishing private inventory. Replace the
placeholder locally and do not paste the resulting address into the issue:

```bash
curl --resolve 'news.lihor.ro:443:<ingress-address>' \
  https://news.lihor.ro/api/health
```

Require an HTTP 200 response whose body contains `"status":"ok"` and a valid
certificate for `news.lihor.ro`.

## Prepare rollback

Complete this before touching the old public route:

1. Record the current and staged revisions from
   `helm -n news-dashboard history news-dashboard`.
2. Save the current release values in a protected local file so authentication
   and integration settings are available during rollback:

   ```bash
   (
   umask 077
   : "${ROLLBACK_VALUES_FILE:?set a protected local rollback values path}"
   helm get values news-dashboard --namespace news-dashboard --output yaml \
     >"$ROLLBACK_VALUES_FILE"
   chmod 600 "$ROLLBACK_VALUES_FILE"
   )
   ```

   Treat this file as a secret, because release values can contain credentials.
3. Retain the pre-cutover Caddy configuration and its service enablement state.
4. Confirm the previous release can restore its former application route.
5. Record the DNS or port-owner reversal needed to return traffic to Caddy.
6. Confirm the pre-cutover PostgreSQL backup and restore verification.
7. Set explicit rollback triggers: failed health, failed login/callback,
   invalid TLS, missing Keycloak route, or unexpected public listening ports.

Do not remove the previous release or saved Caddy configuration during the
observation window.

## Remove the old application route

Only continue after the staged health check and rollback rehearsal succeed.

1. Install and verify the equivalent Ingress route for `/keycloak`, including
   the existing public base URL and callback behavior.
2. Recheck that the application Ingress cannot capture `/keycloak` before the
   identity-provider route.
3. Stop the public Caddy listener and let the ingress controller become the sole
   owner of ports 80 and 443.
4. Set `INGRESS_CUTOVER_ENABLED=true` in the protected production environment
   and rerun the main deployment, or invoke the local helper with that exact
   value. This is the first point at which automation may replace the live
   release with the production overlay.
5. Verify the Ingress health and Keycloak route locally through the intended
   hostname.
6. Move DNS or the router forwarding target to the Ingress endpoint only after
   the local checks pass.
7. Keep the saved pre-cutover Caddy configuration until the observation window
   and rollback rehearsal are complete.

If Keycloak must remain behind Caddy, stop here. Caddy and the ingress
controller cannot safely compete for the same public sockets; migrate the
Keycloak route first rather than accepting an authentication outage.

## Verify the public deployment

Run these checks from outside the appliance network:

```bash
curl --fail --show-error --silent https://news.lihor.ro/api/health
curl --fail --show-error --silent --head https://news.lihor.ro/
curl --show-error --silent --dump-header - --output /dev/null \
  https://news.lihor.ro/auth/login
```

Also verify:

- the certificate hostname, issuer, and expiry;
- HTTP redirects to HTTPS;
- local-password login and the Keycloak redirect/callback flow, when enabled;
- `/keycloak` does not fall through to the application SPA;
- security headers, including the application-generated Content Security
  Policy;
- `kubectl get service` shows no externally reachable application Service;
- the host firewall exposes only the intended public ports.

Record results in issue #1302 without including secrets or private addresses.

## Roll back

Trigger rollback immediately if any prepared condition fails:

### Restore the rollback backend

Keep public traffic on the current Ingress while restoring the old backend.
Reuse the live release values to preserve authentication and integrations, and
keep `ingress.enabled=true` so the Ingress and temporary NodePort coexist. The
explicit `production=false` override is required because production mode's
ClusterIP guard rejects the temporary NodePort. Keep the protected saved values
file as the recovery reference if the live release metadata is unavailable:

```bash
(
: "${SESSION_SECRET:?set SESSION_SECRET}"
: "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}"
: "${POSTGRES_HOST_PATH:?set POSTGRES_HOST_PATH}"
: "${ROLLBACK_IMAGE_TAG:?set ROLLBACK_IMAGE_TAG}"
: "${ROLLBACK_NODE_PORT:?set ROLLBACK_NODE_PORT from the saved release}"
: "${ROLLBACK_VALUES_FILE:?set the saved values path}"
test -r "$ROLLBACK_VALUES_FILE"
source ./scripts/production-deploy-lib.sh
prepare_production_helm_secret_files

helm upgrade --install news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard \
  --reuse-values \
  --set production=false \
  --set ingress.enabled=true \
  --set networkPolicy.enabled=false \
  --set service.type=NodePort \
  --set service.nodePort="$ROLLBACK_NODE_PORT" \
  --set image.tag="$ROLLBACK_IMAGE_TAG" \
  --set-string postgresql.persistence.hostPath="$POSTGRES_HOST_PATH" \
  --set-file app.auth.sessionSecret="$PRODUCTION_SESSION_SECRET_FILE" \
  --set-file postgresql.password="$PRODUCTION_POSTGRES_PASSWORD_FILE"
)
```

### Verify the rollback backend locally

Do not redirect traffic yet:

```bash
curl --fail --show-error --silent \
  "http://127.0.0.1:${ROLLBACK_NODE_PORT}/api/health"
```

Require `"status":"ok"` and verify the expected database before continuing.
Then confirm the still-live Ingress remains healthy:

```bash
curl --fail --show-error --silent https://news.lihor.ro/api/health
```

Both checks must pass at the same time before changing listeners.

### Prepare the saved Caddy application route

Confirm the saved pre-cutover configuration contains both the application
backend and `/keycloak`, then validate it without starting its listener:

```bash
sudo caddy validate --config "$SAVED_CADDY_CONFIG"
```

### Release the Ingress listener

Stop or detach the ingress controller from host ports 80 and 443 using the
controller-specific command recorded during rollback preparation. Confirm both
ports are free before starting Caddy. Do not change DNS or router forwarding.

### Start Caddy

Install the saved application configuration, then start or reload Caddy:

```bash
sudo install -m 0644 "$SAVED_CADDY_CONFIG" /etc/caddy/Caddyfile
sudo systemctl start caddy
sudo systemctl reload caddy
```

### Verify Caddy locally

Keep external routing unchanged until the old edge is healthy:

```bash
curl --fail --show-error --silent \
  --resolve 'news.lihor.ro:443:127.0.0.1' \
  https://news.lihor.ro/api/health
```

Also verify `/keycloak` and the login callback through the local Caddy listener.
For example, check the Keycloak route without changing public DNS:

```bash
curl --fail --show-error --silent --head \
  --resolve 'news.lihor.ro:443:127.0.0.1' \
  https://news.lihor.ro/keycloak/
```

### Change DNS or port ownership

Only after both local checks pass, reverse any DNS, load-balancer, or router
change that is still needed to send public traffic to Caddy. Then repeat the
external health and authentication checks.

### Disable the old Ingress

Only after Caddy owns and serves application and Keycloak traffic, disable or
delete the application Ingress and verify that doing so does not disturb the
Caddy route. Do not remove the saved values or Caddy configuration until the
rollback observation window closes.

Restore PostgreSQL only when the application rollback requires a
data-incompatible schema reversal. Preserve the failed state and logs first.

Do not delete the staged Ingress evidence until the failure is understood. A
Helm rollback does not reverse DNS, host listeners, firewall rules, or database
changes; each must be restored and verified separately.
