# PostgreSQL Backup and Restore

The Helm chart ships an optional scheduled backup CronJob that creates timestamped
compressed PostgreSQL logical dumps (pg_dump custom format) and prunes old files
according to a configurable retention policy.

## Enabling backups

Set the following values (override in your `values.yaml` or via `--set`):

```yaml
postgresql:
  backup:
    enabled: true
    schedule: "0 2 * * *"      # daily at 02:00 UTC (cron syntax)
    retentionDays: 7            # delete dumps older than this many days
    hostPath: /home/ioachim-minipc/news-dashboard-postgres-backups
```

> **Important:** `hostPath` must be different from `postgresql.persistence.hostPath`
> (the live data directory).  The CronJob mounts the backup directory separately
> to prevent the retention cleanup from touching live data.

Apply with:

```bash
helm upgrade news-dashboard ./helm/news-dashboard \
  --set postgresql.backup.enabled=true \
  --set postgresql.backup.hostPath=/home/ioachim-minipc/news-dashboard-postgres-backups \
  --reuse-values
```

## Where dumps are stored

Dumps are written to the configured `hostPath` directory on the cluster node with
filenames of the form:

```
news_dashboard_20260628T020001Z.dump
```

Each dump uses `pg_dump -Fc` (custom binary format), which is compact, parallel-
restore capable, and safe for long-term storage.

## Triggering a manual backup

You can run the backup job immediately without waiting for the schedule:

```bash
kubectl -n news-dashboard create job \
  --from=cronjob/news-dashboard-news-dashboard-postgres-backup \
  manual-backup-$(date +%Y%m%d)
```

Watch the job logs:

```bash
kubectl -n news-dashboard logs -l job-name=manual-backup-... -f
```

## Restoring a dump

### 1. Copy the dump to a local machine (optional)

```bash
# From the node host, copy via scp or mount the backup directory directly.
scp ioachim-minipc:/home/ioachim-minipc/news-dashboard-postgres-backups/news_dashboard_20260628T020001Z.dump .
```

### 2. Restore into the running Helm PostgreSQL pod

```bash
# Find the postgres pod name:
POD=$(kubectl -n news-dashboard get pod -l app.kubernetes.io/name=news-dashboard-postgres -o jsonpath='{.items[0].metadata.name}')

# Copy the dump into the pod:
kubectl -n news-dashboard cp news_dashboard_20260628T020001Z.dump "${POD}:/tmp/restore.dump"

# Drop and recreate the target database, then restore:
kubectl -n news-dashboard exec -it "${POD}" -- bash -c "
  psql -U news_dashboard -d postgres -c 'DROP DATABASE IF EXISTS news_dashboard;'
  psql -U news_dashboard -d postgres -c 'CREATE DATABASE news_dashboard;'
  pg_restore -U news_dashboard -d news_dashboard /tmp/restore.dump
"
```

### 3. Restore into a fresh Helm deployment

Deploy the chart without the application (or with replicas=0), then follow step 2.
Once the restore is confirmed, scale the application back up:

```bash
kubectl -n news-dashboard scale deployment news-dashboard --replicas=1
```

## Verifying a dump (without restoring to production)

```bash
# Inspect the dump table of contents:
pg_restore --list news_dashboard_20260628T020001Z.dump | head -40

# Restore into a throwaway local container:
docker run --rm -e POSTGRES_PASSWORD=test -p 5433:5432 -d --name pg-verify postgres:16-alpine
sleep 3
pg_restore -h 127.0.0.1 -p 5433 -U postgres -d postgres \
  --create news_dashboard_20260628T020001Z.dump
docker stop pg-verify
```

## Disabling backups

```bash
helm upgrade news-dashboard ./helm/news-dashboard \
  --set postgresql.backup.enabled=false \
  --reuse-values
```

This removes the CronJob from the cluster; existing dump files on the host are
not deleted.
