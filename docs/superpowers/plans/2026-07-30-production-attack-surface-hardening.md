# Production Attack-Surface Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every repository-controlled security gap in GitHub issue #1300 and leave mini-PC-only rollout work in human issue #1302.

**Architecture:** The Helm chart renders a ClusterIP-only, TLS-Ingress-ready, default-deny deployment with explicit workload hardening. Untrusted outbound HTTP uses one DNS-pinned transport that preserves Host/SNI, while browser rendering and push delivery fail closed when they cannot provide the same guarantee. FastAPI emits the canonical CSP; production automation, immutable supply-chain references, and documentation enforce the same deployment contract.

**Tech Stack:** Python 3.14, FastAPI/Starlette, stdlib urllib/http.client/socket/ssl, pytest, React/Vite/PWA, Helm 3, Kubernetes networking.k8s.io/v1, GitHub Actions.

## Global Constraints

- Runtime database behavior remains PostgreSQL-only and uses psycopg parameter style.
- OTP behavior and account auto-registration remain unchanged.
- Production must not render or deploy a news-dashboard NodePort.
- Each untrusted HTTP or HTTPS request and redirect must resolve once, reject the entire answer set if any address is unsafe, dial a validated numeric address, and preserve the original Host header, TLS SNI, and certificate hostname verification.
- Environment HTTP proxies must not bypass the pinned transport.
- Selenium rendering of untrusted public URLs is disabled unless a separately enforced validating egress proxy is configured.
- Operator-configured private service endpoints remain outside the public-web SSRF policy.
- Every Kubernetes workload explicitly sets `automountServiceAccountToken: false`.
- Production Ingress, NetworkPolicy selectors, external-service egress, hostname, and TLS secret remain operator-configurable.
- The application is the canonical source for dynamic CSP directives; only the normalized configured Dify origin may be added to `frame-src`.
- Third-party GitHub Actions use full commit SHAs with version comments.
- Mini-PC installation, DNS/TLS changes, firewall changes, and live cutover are documented but remain in human issue #1302.

---

### Task 1: Render a ClusterIP-only hardened Kubernetes deployment

**Files:**
- Create: `helm/news-dashboard/values-production.yaml`
- Create: `helm/news-dashboard/templates/networkpolicy.yaml`
- Create: `scripts/test_helm_security_hardening.py`
- Modify: `helm/news-dashboard/values.yaml`
- Modify: `helm/news-dashboard/templates/service.yaml`
- Modify: `helm/news-dashboard/templates/ingress.yaml`
- Modify: `helm/news-dashboard/templates/deployment.yaml`
- Modify: `helm/news-dashboard/templates/cronjob.yaml`
- Modify: `helm/news-dashboard/templates/postgres-statefulset.yaml`
- Modify: `helm/news-dashboard/templates/postgres-backup-cronjob.yaml`
- Modify: `helm/news-dashboard/templates/neo4j-statefulset.yaml`
- Modify: `Makefile`

**Interfaces:**
- Consumes: existing chart labels from `news-dashboard.name` and `news-dashboard.fullname`.
- Produces: `values-production.yaml`; `networkPolicy.enabled`, controller selectors, public HTTPS egress, and additional egress configuration; ClusterIP-only Service; hardened pod specs.

- [ ] **Step 1: Add failing rendered-manifest tests**

Create tests that call `helm template` and parse multi-document YAML. Assert:

```python
def test_production_service_is_cluster_ip_without_node_port() -> None:
    rendered = render_chart("--values", "helm/news-dashboard/values-production.yaml")
    service = find_resource(rendered, "Service", "release-news-dashboard")
    assert service["spec"]["type"] == "ClusterIP"
    assert "nodePort" not in service["spec"]["ports"][0]


def test_production_ingress_requires_tls() -> None:
    rendered = render_chart("--values", "helm/news-dashboard/values-production.yaml")
    ingress = find_kind(rendered, "Ingress")
    assert ingress["spec"]["tls"][0]["hosts"] == ["news.lihor.ro"]


def test_all_workloads_disable_service_account_token_mounting() -> None:
    rendered = render_chart("--values", "helm/news-dashboard/values-production.yaml")
    for pod_spec in rendered_pod_specs(rendered):
        assert pod_spec["automountServiceAccountToken"] is False


def test_production_renders_default_deny_and_required_allow_policies() -> None:
    rendered = render_chart("--values", "helm/news-dashboard/values-production.yaml")
    policy_names = resource_names(rendered, "NetworkPolicy")
    assert {
        "release-news-dashboard-default-deny",
        "release-news-dashboard-app",
        "release-news-dashboard-postgres",
    } <= policy_names
```

Also assert restrictive security contexts for app, ingest, PostgreSQL backup,
and Neo4j; DNS and public TCP/443 egress; configurable ingress-controller
selectors; and no literal `NodePort` in the production render.

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/pytest scripts/test_helm_security_hardening.py -v
```

Expected: failures because production values, NetworkPolicies, token settings,
and hardened workload defaults do not exist.

- [ ] **Step 3: Implement the secure chart contract**

Make the Service template reject non-ClusterIP production configuration.
Add production values with:

```yaml
service:
  type: ClusterIP
ingress:
  enabled: true
  className: traefik
  host: news.lihor.ro
  tls:
    - secretName: news-dashboard-tls
      hosts: [news.lihor.ro]
networkPolicy:
  enabled: true
```

Add configurable controller namespace/pod selectors and additional egress
rules. Render default-deny plus minimum app/ingest/PostgreSQL/Neo4j/DNS/HTTPS
allow policies. Add `automountServiceAccountToken: false` to every pod spec.
Harden PostgreSQL/backup/Neo4j only with settings supported by their images.
Keep required data directories writable. Add the new security test to
`make helm-validate`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
.venv/bin/pytest scripts/test_helm_security_hardening.py \
  scripts/test_helm_postgres_backup.py scripts/test_helm_email_secret.py -v
make helm-validate
```

Expected: all tests and Helm lint/templates pass.

- [ ] **Step 5: Commit**

```bash
git add helm/news-dashboard Makefile scripts/test_helm_security_hardening.py
git commit -m "fix: harden Kubernetes production manifests"
```

### Task 2: Pin DNS validation to the actual outbound connection

**Files:**
- Modify: `backend/news_dashboard/url_safety.py`
- Modify: `backend/tests/test_url_safety.py`
- Modify: `backend/news_dashboard/body_fetch.py`
- Modify: `backend/tests/test_body_fetch.py`

**Interfaces:**
- Consumes: existing `UnsafeUrlError`, `validate_server_fetch_url`, and `open_server_fetch_url` callers.
- Produces: a resolved-target value and HTTP/HTTPS handlers that dial numeric addresses while preserving hostname semantics; the public `open_server_fetch_url(request, timeout=...)` signature remains stable.

- [ ] **Step 1: Add failing transport tests**

Add deterministic socket/connection tests that prove:

```python
def test_open_dials_the_validated_numeric_address_without_second_dns_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # First resolution is public; any later hostname lookup would be metadata IP.
    # Assert create_connection receives ("203.0.113.10", 80), never a hostname.


def test_https_uses_original_hostname_for_sni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Assert the numeric address is dialed and wrap_socket receives
    # server_hostname="example.test".


def test_redirect_resolves_validates_and_pins_each_hop() -> None:
    # Public first hop followed by a private redirect must raise UnsafeUrlError
    # before the private address is dialed.


def test_mixed_public_and_private_dns_answers_are_rejected() -> None:
    # Preserve the fail-closed all-answer-set rule.
```

Cover IPv4, IPv6, non-default ports, Host headers, trailing-dot
canonicalization, malformed ports/userinfo/control characters, and disabled
environment proxies.

Add a body-fetch test proving `_fetch_capped_html` uses
`open_server_fetch_url` and preserves the byte cap rather than calling
`httpx.stream`.

- [ ] **Step 2: Verify RED**

Run:

```bash
source .env && .venv/bin/pytest \
  backend/tests/test_url_safety.py backend/tests/test_body_fetch.py -v
```

Expected: the dial receives a hostname or the new API is absent, and body fetch
still uses `httpx`.

- [ ] **Step 3: Implement the pinned transport**

Introduce a typed resolved-target object. Resolve each URL once, reject any
unsafe answer, and have custom `HTTPConnection`/`HTTPSConnection` plus urllib
handlers dial the selected numeric sockaddr. Preserve the original host for
Host/SNI/certificate verification. Use `ProxyHandler({})`. Re-run resolution
and validation for every redirect. Preserve the existing public opener
signature and exception contract.

Replace `_fetch_capped_html`'s direct `httpx.stream` with the central opener
while retaining response-size limits, timeout behavior, content checks, and
error mapping.

- [ ] **Step 4: Verify GREEN and type safety**

Run:

```bash
source .env && .venv/bin/pytest \
  backend/tests/test_url_safety.py backend/tests/test_body_fetch.py -v
make lint
make typecheck
```

Expected: focused tests, lint, mypy, ty, and pyrefly pass.

- [ ] **Step 5: Commit**

```bash
git add backend/news_dashboard/url_safety.py backend/news_dashboard/body_fetch.py \
  backend/tests/test_url_safety.py backend/tests/test_body_fetch.py
git commit -m "fix: pin validated fetch addresses"
```

### Task 3: Fail closed for browser rendering and push endpoints

**Files:**
- Modify: `backend/news_dashboard/selenium_client.py`
- Modify: `backend/news_dashboard/scraper.py`
- Modify: `backend/news_dashboard/body_fetch.py`
- Modify: `backend/news_dashboard/push.py`
- Modify: `backend/tests/test_url_safety.py`
- Modify: `backend/tests/test_scraper.py`
- Modify: `backend/tests/test_content_extraction.py`
- Modify: `backend/tests/test_push_notifications.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: Task 2's pinned public-fetch policy.
- Produces: Selenium public rendering disabled by default unless `PUBLIC_RENDERER_EGRESS_PROXY` is configured; push endpoints reject DNS answers that cannot be proven public and pinned by an approved transport.

- [ ] **Step 1: Add failing fail-closed tests**

Add tests:

```python
def test_public_url_does_not_fall_back_to_selenium_without_egress_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PUBLIC_RENDERER_EGRESS_PROXY", raising=False)
    # Static extraction failure must not invoke fetch_spa_html.


def test_push_subscription_rejects_hostname_that_resolves_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # validate_push_subscription raises ValueError for a private DNS answer.


def test_push_delivery_fails_closed_without_pinned_transport() -> None:
    # A user-controlled hostname must not reach pywebpush through an
    # unvalidated second-resolution path.
```

Also cover safe public endpoints and configuration parsing without exposing
operator-configured private service URLs to this policy.

- [ ] **Step 2: Verify RED**

Run:

```bash
source .env && .venv/bin/pytest \
  backend/tests/test_scraper.py backend/tests/test_content_extraction.py \
  backend/tests/test_push_notifications.py -v
```

Expected: Selenium is invoked without the proxy gate and push hostname
resolution is not pinned/fail-closed.

- [ ] **Step 3: Implement the gates**

Prevent public content extraction from invoking Selenium unless an explicit
validating egress proxy is configured. Validate that configuration as an HTTP
or HTTPS URL without logging credentials. Document the variable in
`.env.example`.

For Web Push, use the narrowest supported injectable session/transport that
dials the validated address while retaining endpoint TLS hostname semantics.
If `pywebpush` cannot accept such a transport, fail closed for hostname
endpoints and document the operational limitation; do not claim preflight-only
DNS validation closes rebinding.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
source .env && .venv/bin/pytest \
  backend/tests/test_scraper.py backend/tests/test_content_extraction.py \
  backend/tests/test_push_notifications.py backend/tests/test_url_safety.py -v
make lint
make typecheck
```

Expected: focused tests and Python gates pass.

- [ ] **Step 5: Commit**

```bash
git add .env.example backend/news_dashboard backend/tests
git commit -m "fix: fail closed for unpinned public fetches"
```

### Task 4: Add a production-compatible Content Security Policy

**Files:**
- Modify: `backend/news_dashboard/security_headers.py`
- Modify: `backend/news_dashboard/dify.py`
- Modify: `backend/tests/test_security_headers.py`
- Modify: `backend/tests/test_dify_config.py`
- Modify: `frontend/vite.config.ts`
- Create or modify as required by the existing Vite entry: `frontend/src/registerServiceWorker.ts`
- Modify: frontend tests adjacent to service-worker registration if present

**Interfaces:**
- Consumes: `public_dify_config()` normalized configuration and existing FastAPI security-header middleware.
- Produces: `content_security_policy() -> str`; all responses carry CSP; only the validated Dify origin is added to `frame-src`; service-worker registration requires no inline script.

- [ ] **Step 1: Add failing CSP tests**

Add assertions:

```python
def test_default_csp_is_applied_to_success_and_not_found_responses() -> None:
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "object-src 'none'" in response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "'unsafe-inline'" not in script_src(response)


def test_csp_allows_only_normalized_dify_origin_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIFY_CHAT_BASE_URL", "https://chat.example.test/path/")
    assert "frame-src 'self' https://chat.example.test" in content_security_policy()
    assert "/path" not in frame_src(content_security_policy())
```

Cover `https://api.github.com`, required data/blob resource types, invalid Dify
configuration, disabled Dify, HSTS coexistence, and route-set stricter CSP
preservation. Add a frontend/build assertion that service-worker registration
is external rather than injected inline.

- [ ] **Step 2: Verify RED**

Run:

```bash
source .env && .venv/bin/pytest \
  backend/tests/test_security_headers.py backend/tests/test_dify_config.py -v
npm run test:frontend --prefix frontend
```

Expected: CSP is absent and the current PWA registration strategy is not proven
compatible.

- [ ] **Step 3: Implement CSP and external registration**

Generate the policy from fixed directives plus the normalized Dify origin.
Keep inline styles temporarily allowed, but do not allow inline scripts.
Apply CSP through existing middleware with `setdefault`. Adjust Vite/PWA
registration to use an external module while preserving update behavior,
offline caching, and the manifest.

- [ ] **Step 4: Verify GREEN across backend and frontend**

Run:

```bash
source .env && .venv/bin/pytest \
  backend/tests/test_security_headers.py backend/tests/test_dify_config.py \
  backend/tests/test_spa_static.py -v
npm run lint --prefix frontend
npm run format:check --prefix frontend
npm run typecheck --prefix frontend
npm run test:frontend --prefix frontend
npm run build --prefix frontend
```

Expected: backend tests and all frontend gates pass.

- [ ] **Step 5: Commit**

```bash
git add backend/news_dashboard/security_headers.py backend/news_dashboard/dify.py \
  backend/tests frontend
git commit -m "fix: enforce a production content security policy"
```

### Task 5: Pin repository-controlled supply-chain references

**Files:**
- Create: `scripts/test_supply_chain_pins.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/trivy-scan.yml`
- Modify: `.github/workflows/docs.yml`
- Modify: `.github/workflows/dependency-review.yml`
- Modify: `.github/workflows/nightly.yml`
- Modify: `.github/workflows/pr-timing.yml`
- Modify: `Dockerfile`
- Modify: `helm/news-dashboard/values.yaml`
- Modify: `docker-compose.prod.yml`

**Interfaces:**
- Produces: full-SHA action references with version comments; immutable
production/base image references where verified; a mechanical enforcement test.

- [ ] **Step 1: Add a failing pin-enforcement test**

Create tests that parse workflow YAML text and image references:

```python
ACTION_REF = re.compile(r"uses:\\s+[^\\s]+@([0-9a-f]{40})(?:\\s+#\\s+v[^\\s]+)?$")


def test_third_party_actions_are_pinned_to_full_commit_shas() -> None:
    for workflow in WORKFLOWS:
        assert_no_floating_action_refs(workflow)


def test_production_container_references_are_immutable() -> None:
    assert_no_latest_or_unpinned_production_images()
```

Local actions (`./...`) are exempt. Require readable version comments for
third-party actions.

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/pytest scripts/test_supply_chain_pins.py -v
```

Expected: tag-based action refs and mutable image refs fail.

- [ ] **Step 3: Resolve and apply immutable references**

Resolve every currently used action tag to its upstream full commit SHA and
retain the human-readable tag as a comment. Resolve current supported base,
PostgreSQL, and Neo4j image digests using registry manifests. Preserve
architecture compatibility; do not invent digests. Allow CI-built application
images to use a source-SHA tag only where the workflow cannot consume the
registry-produced digest in the same job, and encode that explicit exception in
the test.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
.venv/bin/pytest scripts/test_supply_chain_pins.py scripts/test_trivy_workflows.py -v
docker build --check .
```

Expected: pin tests, Trivy workflow tests, and Dockerfile validation pass.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows Dockerfile helm/news-dashboard/values.yaml \
  docker-compose.prod.yml scripts/test_supply_chain_pins.py
git commit -m "chore: pin production supply-chain references"
```

### Task 6: Migrate deployment automation and publish the operator runbook

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/deploy-local-k8s.sh`
- Modify: `scripts/test_ci_deploy_namespace.py`
- Modify: `scripts/test_caddy_source_of_truth.py`
- Modify: `deploy/Caddyfile`
- Modify: `README.md`
- Modify: `docs/SELF_HOSTING.md`
- Modify: `website/docs/configuration/https-caddy.md`
- Modify: `website/docs/architecture/index.md`
- Modify: `website/docs/architecture/product-spec.md`
- Modify: `website/docs/self-hosting/index.md`

**Interfaces:**
- Consumes: Task 1's production values and Task 4's application CSP.
- Produces: no NodePort deployment flags or smoke checks; Ingress-based
production validation; migration/rollback and PostgreSQL exposure runbook
linked to human issue #1302.

- [ ] **Step 1: Update tests first**

Change CI/deployment source-of-truth tests to assert:

```python
def test_production_deploy_uses_cluster_ip_and_ingress() -> None:
    workflow = CI_WORKFLOW.read_text()
    assert "service.type=NodePort" not in workflow
    assert "service.nodePort=30088" not in workflow
    assert "values-production.yaml" in workflow


def test_public_smoke_check_uses_https_hostname() -> None:
    assert "http://localhost:30088" not in CI_WORKFLOW.read_text()


def test_docs_link_the_manual_appliance_rollout_issue() -> None:
    assert "issues/1302" in SELF_HOSTING.read_text()
```

Also assert that Caddy is no longer documented as the application TLS source
of truth, the Keycloak preservation requirement is present, rollback precedes
removal of the old route, and host PostgreSQL guidance covers listener,
`pg_hba.conf`, firewall, TLS, backups, and restore verification.

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/pytest scripts/test_ci_deploy_namespace.py \
  scripts/test_caddy_source_of_truth.py -v
```

Expected: current NodePort/Caddy assertions and deployment commands fail the
new contract.

- [ ] **Step 3: Implement automation and documentation migration**

Make CI and the deployment helper apply `values-production.yaml` plus
secret/runtime overrides, then validate the Ingress endpoint without assuming
mini-PC access in PR CI. Remove the application's Caddy reverse proxy while
preserving/documenting the Keycloak migration boundary.

Update all listed documentation sources consistently. Start with the target
Ingress architecture, then give prerequisites, staged cutover, verification,
rollback, PostgreSQL host controls, and the explicit handoff to #1302. Never
include appliance secrets or private inventory.

- [ ] **Step 4: Verify GREEN and documentation consistency**

Run:

```bash
.venv/bin/pytest scripts/test_ci_deploy_namespace.py \
  scripts/test_caddy_source_of_truth.py \
  scripts/test_helm_security_hardening.py -v
make helm-validate
```

Expected: deployment-source and documentation tests pass, and the final chart
still validates.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml scripts/deploy-local-k8s.sh \
  scripts/test_ci_deploy_namespace.py scripts/test_caddy_source_of_truth.py \
  deploy/Caddyfile README.md docs/SELF_HOSTING.md website/docs
git commit -m "docs: prepare the ingress appliance migration"
```

### Task 7: Run repository-wide security verification

**Files:**
- Modify only if failures are caused by Tasks 1–6; amend the causal task rather than adding unrelated cleanup.

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: fresh evidence that the complete repository-side hardening works together.

- [ ] **Step 1: Verify the dedicated PostgreSQL test service**

Run:

```bash
podman ps --filter name=nd-test-pg
```

If absent, bootstrap it using the repository-supported setup. Confirm `.env`
targets `localhost:55432/news_dashboard_test` without printing secret values.

- [ ] **Step 2: Run all mandatory gates**

Run:

```bash
export PATH="$PWD/.venv/bin:$PATH"
source .env
export PGOPTIONS='-c max_parallel_workers_per_gather=0'
make lint
make typecheck
make test
make helm-validate
npm run build --prefix frontend
```

Expected: every command exits zero with no warnings treated as errors.

- [ ] **Step 3: Verify acceptance criteria from rendered artifacts**

Render production Helm output and inspect it for ClusterIP, TLS Ingress,
NetworkPolicies, workload token settings, security contexts, and immutable
image references. Confirm repository search finds no production NodePort and no
unpinned third-party workflow action:

```bash
helm template news-dashboard helm/news-dashboard \
  --values helm/news-dashboard/values-production.yaml > /tmp/news-dashboard-production.yaml
rg -n "NodePort|nodePort: 30088|uses: .+@v[0-9]" \
  .github helm scripts deploy docs website README.md
```

Expected: no production/deployment violation; any historical or rollback
mention is explicitly documented and not rendered/applied.

- [ ] **Step 4: Commit only causal verification fixes**

```bash
git status --short
```

If verification required a causal fix, commit it under the matching task's
message. Otherwise create no empty commit.
