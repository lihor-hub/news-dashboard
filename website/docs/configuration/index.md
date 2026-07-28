# Configuration

Environment variables, feature flags, and integrations such as Keycloak
authentication, Caddy/HTTPS, and Postgres backups.

| Guide                                                 | Use it to                                                                     |
| ----------------------------------------------------- | ----------------------------------------------------------------------------- |
| [Authentication (Keycloak)](authentication)           | Choose local-password or Keycloak sign-in and configure administrator access. |
| [Dify assistant](dify-assistant)                      | Add a host-owned launcher for an optional Dify WebApp iframe.                 |
| [HTTPS with Caddy](https-caddy)                       | Terminate TLS and publish a self-hosted instance safely.                      |
| [PostgreSQL Backup and Restore](postgres-backup)      | Schedule, create, verify, and restore database backups.                       |
| [Newsletter ingestion via IMAP](newsletter-ingestion) | Add newsletters to user feeds through a configured mailbox.                   |
| [Neo4j Knowledge Graph](neo4j-knowledge-graph)        | Enable graph storage and backfill entities and relationships.                 |
| [MCP server](mcp-server)                              | Enable scoped, read-only article access for an external AI client.            |
| [RSS client sync (Google Reader API)](greader-sync)   | Connect a compatible RSS client with a per-user token.                        |

See the root [README](https://github.com/lihor-hub/news-dashboard#configuration)
for the full environment variable reference.

## Email delivery

Email delivery remains disabled until the deployment provides a complete SMTP
configuration and an absolute, browser-facing `APP_BASE_URL`. Enabling email
controls in a user's settings does not make delivery available by itself.

| Variable       | Description                                                                         |
| -------------- | ----------------------------------------------------------------------------------- |
| `SMTP_HOST`    | SMTP relay hostname.                                                                |
| `SMTP_PORT`    | SMTP relay port.                                                                    |
| `SMTP_USER`    | SMTP login username.                                                                |
| `SMTP_PASS`    | SMTP login password. Store this outside version control.                            |
| `SMTP_FROM`    | Sender address used for outbound messages.                                          |
| `SMTP_TLS`     | Transport mode: `starttls`, `ssl`, or `none`.                                       |
| `APP_BASE_URL` | Absolute public URL used for links in email, independent of Keycloak configuration. |

`SMTP_USERNAME` and `SMTP_PASSWORD` remain supported for legacy OTP email
deployments. OTP-specific `OTP_SMTP_*` values retain precedence when set. With
Helm, configure the non-secret values under `app.email`, set
`app.publicBaseUrl`, and provide credentials through `app.email.existingSecret`;
the chart does not render credential values into the Deployment.

For email links, `APP_BASE_URL` takes precedence over the compatibility
variables `NEWS_DASHBOARD_BASE_URL` and `NEWS_DASHBOARD_URL`, in that order.
