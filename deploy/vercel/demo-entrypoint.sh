#!/bin/sh
# Entrypoint for the Vercel PR-preview demo backend (deploy/vercel/Dockerfile).
#   seed  - build time: create the demo database under $PGDEMO_SEED
#   serve - runtime: copy it to $PGDATA, start PostgreSQL, run the API
set -eu

SESSION_SECRET=$(cat /etc/news-dashboard/session_secret)
export SESSION_SECRET

as_postgres() {
    runuser -u postgres -- "$@"
}

start_postgres() {
    # Socket-only, tuned for a disposable read-mostly database. mmap dynamic
    # shared memory avoids depending on the size of /dev/shm.
    as_postgres "$PG_BIN/pg_ctl" -D "$1" -w -l "$1/postgres.log" start -o "\
        -c listen_addresses='' -c unix_socket_directories=/tmp \
        -c dynamic_shared_memory_type=mmap -c shared_buffers=16MB \
        -c max_parallel_workers_per_gather=0 -c fsync=off \
        -c synchronous_commit=off -c full_page_writes=off"
}

case "${1:-serve}" in
seed)
    install -d -o postgres -g postgres -m 0700 "$PGDEMO_SEED"
    as_postgres "$PG_BIN/initdb" -D "$PGDEMO_SEED" -U news_dashboard \
        --auth=trust --encoding=UTF8 --no-sync >/dev/null
    start_postgres "$PGDEMO_SEED"
    as_postgres "$PG_BIN/createdb" -h /tmp -U news_dashboard news_dashboard
    news-dashboard init
    news-dashboard seed-demo
    as_postgres "$PG_BIN/pg_ctl" -D "$PGDEMO_SEED" -w stop
    rm -f "$PGDEMO_SEED/postgres.log"
    ;;
serve)
    rm -rf "$PGDATA"
    cp -a "$PGDEMO_SEED" "$PGDATA"
    install -d -m 0755 "$DATA_DIR"
    start_postgres "$PGDATA"
    exec uvicorn news_dashboard.main:app --app-dir backend \
        --host 0.0.0.0 --port "${PORT:-80}"
    ;;
*)
    echo "usage: demo-entrypoint seed|serve" >&2
    exit 2
    ;;
esac
