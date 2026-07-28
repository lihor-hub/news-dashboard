# Administration and operations

Use the application’s administrator pages for user management and day-to-day
ingestion oversight. Use deployment configuration and infrastructure tooling
for secrets, scheduling authority, health monitoring, backups, and upgrades.

These are separate roles even when one person holds both:

| Role                      | Where the work happens                                                 | Responsibilities                                                                                                                                   |
| ------------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Application administrator | Signed-in News Dashboard UI                                            | Create users, inspect ingest activity, control the in-process schedule, and review instance statistics and analytics.                              |
| Deployment operator       | Container host, Compose stack, Kubernetes cluster, or hosting platform | Configure authentication and integrations, operate PostgreSQL, choose the scheduler authority, monitor services, back up data, and deploy updates. |

Administrator pages and their APIs reject non-admin accounts. A deployment
operator does not automatically become an application administrator; use the
instance’s configured authentication method to grant application access.

## Manage users

Sign in with an administrator account and open **Users** (`/admin`).

- Create a username and copy the generated password immediately. The password
  is shown once and cannot be retrieved later.
- With local password authentication, select **Grant administrator access**
  when the new account should administer the application. You can also delete
  other local accounts from this page.
- With Keycloak authentication and administrator provisioning configured, new
  accounts receive a temporary Keycloak password. Keycloak owns account
  deletion and passwords, while `KEYCLOAK_ADMIN_USERNAMES` determines which
  usernames receive application administrator access. The Users list contains
  application users who have signed in at least once, so a newly provisioned
  Keycloak user appears there after their first sign-in.

For a new local-password installation, `BOOTSTRAP_ADMIN_USERNAME` and
`BOOTSTRAP_ADMIN_PASSWORD` create the first administrator only when no users
exist. Changing those values later does not update an existing administrator’s
password; store the configured values as deployment secrets.

See [Authentication configuration](https://docs.lihor.ro/docs/configuration/authentication)
for local-password and Keycloak setup.

## Understand feed responsibilities

**Feeds → Sources** (`/feeds`) is a reader-level page, not an
administrator-only control plane. Each signed-in user can:

- subscribe to or unsubscribe from shared sources;
- add and remove private sources;
- mark sources as high priority;
- import or export OPML; and
- review source health and cleanup suggestions.

Those choices affect that account’s subscriptions or private sources. Use the
[Sources and subscriptions guide](sources.md) for the complete reader
workflow.

The other Feeds tabs are restricted to application administrators:

| Page                             | Use it to                                                                                                                                                 |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Schedule** (`/feeds/schedule`) | Check scheduler state, fetch feeds now, change or pause the in-process ingest interval, run duplicate cleanup, and inspect recent scheduled-job outcomes. |
| **Runs** (`/feeds/runs`)         | Review ingest start time, duration, source count, new-article count, and errors; expand a run for its per-source breakdown.                               |
| **Logs** (`/feeds/logs`)         | Watch the current ingest run or replay output from the last completed run.                                                                                |

The Logs page is an ingest stream, not a durable archive of application or
platform logs. Use container or cluster logging for startup failures,
tracebacks, restarts, and historical retention.

## Control scheduling safely

The Schedule page controls interval ingestion only when the application’s
in-process scheduler is authoritative. If it reports **External schedule**,
interval controls are disabled because the deployment operator has set
`INGEST_INTERVAL_SCHEDULER_ENABLED=false`; for Helm deployments, the ingest
CronJob can be the external authority.

Keep exactly one ingest scheduler active. Deployment operators set the initial
in-process cadence with `INGEST_INTERVAL_MINUTES`, or configure the Helm
CronJob schedule. Application administrators can still use **Fetch now** to
start an immediate ingest and **Remove duplicates** to run duplicate cleanup.

After a manual or scheduled ingest:

1. Open **Runs** and check the error count.
2. Expand a failed run to identify the affected source and its error.
3. Open **Logs** while reproducing the problem if you need the live ingest
   output.
4. Check the deployment’s durable logs when the stream disconnects or the
   process restarts.

## Read statistics and analytics

Both pages are administrator-only, but they answer different questions:

- **Stats** (`/stats`) shows corpus and workflow health: article counts,
  triage rates, ingest volume, source quality, and category mix.
- **Analytics** (`/analytics`) aggregates usage across users, including active
  users, time spent, sessions, route and feature usage, article reading, and AI
  quality signals.

Analytics only reflects events that the instance and its users allow.
Deployment operators can set `ANALYTICS_ENABLED=false` to stop event ingestion
instance-wide, and each user can opt out under **Settings → Privacy**.
`ANALYTICS_RETENTION_DAYS` controls how long recorded events are retained.

## Deployment-operator checklist

Use the [Self-Hosting guide](https://docs.lihor.ro/docs/self-hosting) for
deployment methods, health endpoints, upgrades, rollbacks, and sizing. Keep the
[README configuration reference](https://github.com/lihor-hub/news-dashboard#configuration)
as the canonical environment-variable catalogue.

For routine operations:

- monitor `/api/live` for process liveness and `/api/ready` for database-backed
  readiness;
- expose `/metrics` only when `METRICS_ENABLED=true`, and keep it behind an
  internal network or access policy;
- retain platform logs independently of the in-app ingest stream;
- back up PostgreSQL and persistent app data before upgrades; and
- configure integrations through the focused
  [Configuration guides](https://docs.lihor.ro/docs/configuration) rather than
  copying variable lists between runbooks.

If an application control is unavailable, first check the signed-in account’s
administrator status. If the control is visible but reports an external
authority or missing provider, the deployment operator must change the
corresponding deployment configuration.
