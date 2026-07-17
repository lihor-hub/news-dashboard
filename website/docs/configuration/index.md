# Configuration

Environment variables, feature flags, and integrations such as Keycloak
authentication, Caddy/HTTPS, and Postgres backups.

- [Authentication (Keycloak)](authentication)
- [HTTPS with Caddy](https-caddy)
- [PostgreSQL Backup and Restore](postgres-backup)
- [Newsletter ingestion via IMAP](newsletter-ingestion)
- [Neo4j Knowledge Graph](neo4j-knowledge-graph)

See the root [README](https://github.com/lihor-hub/news-dashboard#configuration)
for the full environment variable reference.

## Email delivery

Email delivery remains disabled until the deployment provides a complete SMTP
configuration and an absolute, browser-facing `APP_BASE_URL`. Enabling email
controls in a user's settings does not make delivery available by itself.

| Variable | Description |
|----------|-------------|
| `SMTP_HOST` | SMTP relay hostname. |
| `SMTP_PORT` | SMTP relay port. |
| `SMTP_USER` | SMTP login username. |
| `SMTP_PASS` | SMTP login password. Store this outside version control. |
| `SMTP_FROM` | Sender address used for outbound messages. |
| `SMTP_TLS` | Transport mode: `starttls`, `ssl`, or `none`. |
| `APP_BASE_URL` | Absolute public URL used for links in email, independent of Keycloak configuration. |

`SMTP_USERNAME` and `SMTP_PASSWORD` remain supported for legacy OTP email
deployments. OTP-specific `OTP_SMTP_*` values retain precedence when set. With
Helm, configure the non-secret values under `app.email`, set
`app.publicBaseUrl`, and provide credentials through `app.email.existingSecret`;
the chart does not render credential values into the Deployment.
