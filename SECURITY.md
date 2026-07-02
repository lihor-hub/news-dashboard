# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Preferred: use GitHub's private reporting form for this repository —
[Report a vulnerability](https://github.com/lihor-hub/news-dashboard/security/advisories/new)
(Security tab → "Report a vulnerability"). This opens a private advisory
visible only to maintainers until a fix is ready.

Fallback: if you cannot use GitHub's private reporting, email
**ioachim.lihor@gmail.com** with:

- A description of the vulnerability and its impact.
- Steps to reproduce, or a proof-of-concept if available.
- Affected version or commit SHA.

We will acknowledge reports within **5 business days** and aim to provide a
fix or mitigation plan within **30 days**, depending on severity and
complexity. Please give us a reasonable window to release a fix before any
public disclosure.

## Supported versions

News Dashboard does not maintain long-lived release branches. Only the
latest published release is supported with security fixes.

| Version         | Supported          |
| ---------------- | ------------------ |
| Latest `1.x` release | :white_check_mark: |
| Older `1.x` releases  | :x:                 |

If you are running an older version, please upgrade to the latest release
before reporting — the issue may already be fixed.

## Security-relevant configuration

This app has real security surface worth getting right when self-hosting:

- **`SESSION_SECRET`** — signs session cookies and (unless `TOKEN_SECRET` is
  set) digest mark-read tokens. Use a strong, unique, randomly generated
  value in any deployment reachable outside your own machine.
- **`BOOTSTRAP_ADMIN_USERNAME`** / **`BOOTSTRAP_ADMIN_PASSWORD`** — set the
  first local admin account. Never leave these at their local-development
  defaults in a reachable deployment.
- **`FREE_LLM_API_KEY`** / **`OPENAI_API_KEY`** — third-party API credentials
  for AI features. Treat as secrets; do not commit them.
- **`VAPID_PRIVATE_KEY`** — private key for Web Push notifications.
- **Keycloak (`KEYCLOAK_*`)** — optional external auth; when enabled, review
  [Authentication (Keycloak)](https://docs.lihor.ro/docs/configuration/authentication) for the trust model.

See the [Configuration](README.md#configuration) table in the README for the
full list of environment variables. Never commit secrets, API keys, database
credentials, or production session values to the repository — use
environment variables or your deployment platform's secret store.
