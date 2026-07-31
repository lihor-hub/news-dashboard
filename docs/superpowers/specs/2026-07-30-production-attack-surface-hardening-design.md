# Production Attack-Surface Hardening Design

## Goal

Close the repository-controlled production hardening gaps from GitHub issue
#1300 while separating operations that require access to the deployed mini PC
into a dedicated, human-run rollout issue.

OTP behavior and account auto-registration remain unchanged.

## Delivery Boundary

This change owns everything that can be prepared and verified from the
repository:

- a ClusterIP-only application service and TLS-ready Kubernetes Ingress;
- least-privilege NetworkPolicies and hardened workload defaults;
- DNS-rebinding-safe public URL fetching;
- a production-compatible Content Security Policy;
- immutable supply-chain references where practical;
- regression tests, Helm validation, and operator documentation.

The follow-up issue owns operations that require the mini PC or its surrounding
infrastructure:

- install and configure the selected ingress controller;
- provision or validate DNS and TLS;
- perform the live NodePort-to-Ingress cutover and rollback rehearsal;
- validate host firewall rules and PostgreSQL exposure;
- verify the deployed headers, routes, and absence of a public NodePort.

Repository automation must not assume those operations have already happened.

## Public Traffic and Ingress

The Helm chart will keep the application Service as `ClusterIP`. A production
values file will enable an Ingress with a required hostname and TLS secret,
secure redirect behavior, and compatible browser-security headers. The
production deployment workflow and local deployment helper will stop rendering
or applying a news-dashboard NodePort.

The Ingress is the intended application TLS terminator. Caddy will no longer be
the application routing source of truth. Documentation will explain that the
live appliance cutover must preserve the existing Keycloak route and must avoid
having Caddy and the ingress controller compete for ports 80 and 443.

Because controller labels and namespaces differ by installation, the chart will
make the allowed ingress-controller namespace and pod labels configurable. The
production values and documentation will provide the intended appliance
settings without hard-coding a universal controller identity.

## Network and Workload Isolation

NetworkPolicy support will be enabled for production and configurable for other
installations. Policies will:

- default-deny ingress and egress for chart workloads;
- permit ingress-controller traffic to the application;
- permit application and ingest workloads to reach bundled PostgreSQL and,
  when enabled, Neo4j;
- permit DNS resolution;
- permit required public HTTPS egress;
- expose configurable egress rules for external PostgreSQL, SMTP, Keycloak,
  and other operator-selected services.

Every workload will explicitly set `automountServiceAccountToken: false`.
Application and ingest security settings will remain restrictive. PostgreSQL,
backup, and Neo4j settings will be tightened only where their upstream images
support the setting: no privilege escalation, dropped capabilities, runtime
seccomp, non-root execution where compatible, and explicit writable storage
instead of making required data paths read-only.

## DNS-Rebinding-Safe Fetching

`url_safety.py` will become the single transport boundary for untrusted public
HTTP and HTTPS fetches.

For each request or redirect hop it will:

1. parse and validate the URL;
2. resolve the hostname once;
3. reject the entire answer set if any address is non-public;
4. select a validated numeric address;
5. connect directly to that address;
6. preserve the original hostname for the HTTP `Host` header, TLS SNI, and
   certificate hostname verification.

The transport will disable environment-proxy routing unless a future explicit,
validated proxy mode is added. URLs will never be rewritten to IP literals.
Redirects will be independently resolved, validated, and pinned.

The AI body-extraction path will use the same transport instead of validating
and then calling `httpx` by hostname.

Browser rendering cannot inherit Python socket pinning. Selenium fallback for
untrusted public URLs will therefore be disabled by default. A future renderer
may be enabled only behind a validating egress proxy with direct renderer
egress blocked. Push-subscription delivery will receive an equivalent
repository-side hardening or fail-closed validation so user-controlled
endpoints cannot become a separate rebinding path. Operator-configured private
service URLs such as PostgreSQL, Keycloak, SMTP, and Langfuse remain outside the
public-web SSRF policy.

## Content Security Policy

The application middleware will emit a CSP on all responses, including errors.
The production policy will default resources to the same origin, deny objects
and framing, restrict form and base targets, and allow only required resource
types.

Known compatibility allowances are:

- inline styles while the React application still uses inline style objects;
- `https://api.github.com` for release lookups;
- blob/data sources required by media and PWA behavior;
- the normalized origin of the configured Dify iframe, when Dify is enabled.

The policy will never interpolate an arbitrary Dify URL. Inline PWA script
registration will be externalized or otherwise made compatible without adding
`'unsafe-inline'` to `script-src`. API documentation behavior will receive a
focused test or an explicitly scoped development-only exception.

Ingress headers will mirror the compatible baseline. The application remains
the canonical source for dynamically generated directives such as the Dify
origin.

## Supply-Chain References

Third-party GitHub Actions will be pinned to full commit SHAs with version
comments. Container references used by production manifests and build stages
will use immutable digests where the repository can verify and maintain them.
Tests will reject newly introduced floating action references and insecure
production image defaults.

Application images produced by CI will continue to be associated with the
source commit. Runtime deployment should consume a digest when the registry
output makes it available.

## Verification

The work will follow red-green-refactor cycles and add focused coverage for:

- ClusterIP-only production rendering and TLS-ready Ingress;
- NetworkPolicy rules and disabled service-account token mounting;
- workload security contexts;
- numeric-address dialing with preserved Host/SNI;
- private redirect and DNS-rebinding rejection;
- removal of the direct `httpx` public-fetch bypass;
- Selenium and push-endpoint fail-closed behavior;
- CSP behavior with Dify disabled and enabled;
- immutable action and production-image references;
- consistency between deployment automation and operator documentation.

Required validation includes focused pytest runs, `make helm-validate`, Python
lint and type checks, frontend lint/type/test/build checks if the PWA bootstrap
changes, the full repository test suite against the dedicated PostgreSQL test
container, and the normal pull-request CI and merge queue.

## Documentation and Manual Follow-Up

Repository documentation will describe the target architecture, migration
sequence, rollback conditions, and remaining host-level PostgreSQL controls.
It will link to a separate GitHub issue containing the exact mini-PC procedure.

That issue will be labelled for human execution rather than autonomous agent
pickup because it requires appliance credentials, DNS/TLS control, firewall
inspection, and live service validation.
