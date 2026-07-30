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

## Stage the Ingress

Deploy the chart with the production values plus secrets and installation-
specific storage values. CI and `scripts/deploy-local-k8s.sh` use the same
contract:

```bash
helm upgrade --install news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard --create-namespace \
  --values ./helm/news-dashboard/values-production.yaml \
  --set image.tag='<immutable-source-sha>' \
  --set-string app.auth.sessionSecret='<from-secret-manager>' \
  --set-string postgresql.password='<from-secret-manager>'
```

Do not copy literal secrets into a values file or an issue. If the installation
uses the repository's production CI or `scripts/deploy-local-k8s.sh`, configure
`POSTGRES_HOST_PATH` at runtime for the existing host-backed PostgreSQL data.
Both entry points fail before Helm when it is missing, so a cutover cannot
silently initialize an empty volume. Other installations can use a chart
persistent-volume configuration appropriate to their cluster.

Inspect the staged resources before changing the public route:

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
2. Retain the pre-cutover Caddy configuration and its service enablement state.
3. Confirm the previous release can restore its former application route.
4. Record the DNS or port-owner reversal needed to return traffic to Caddy.
5. Confirm the pre-cutover PostgreSQL backup and restore verification.
6. Set explicit rollback triggers: failed health, failed login/callback,
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
4. Move DNS or the router forwarding target to the Ingress endpoint.
5. Keep the saved pre-cutover Caddy configuration until the observation window
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

1. Reverse the DNS or port-owner change so traffic returns to the saved Caddy
   route.
2. Run `helm -n news-dashboard rollback news-dashboard <previous-revision>`.
3. Restore and validate the saved pre-cutover Caddy configuration, then restart
   its service.
4. Verify the application health endpoint and both authentication modes through
   the old route.
5. Restore PostgreSQL only when the application rollback requires a
   data-incompatible schema reversal. Preserve the failed state and logs first.

Do not delete the staged Ingress evidence until the failure is understood. A
Helm rollback does not reverse DNS, host listeners, firewall rules, or database
changes; each must be restored and verified separately.
