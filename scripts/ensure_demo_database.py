"""Create the Postgres database used for demo-mode screenshot capture.

`DEMO_DATABASE_URL` (or a `news_dashboard_demo` sibling of `DATABASE_URL`) must
name a database on an already-running Postgres server; Postgres cannot create
a database from within a connection to that same database, so this connects
to the server's `postgres` maintenance database first and creates the target
database if it does not already exist. Safe to re-run.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit, urlunsplit

import psycopg


def _demo_database_url() -> str:
    explicit = os.getenv("DEMO_DATABASE_URL")
    if explicit:
        return explicit
    base = os.getenv("DATABASE_URL")
    if not base:
        print("DATABASE_URL or DEMO_DATABASE_URL must be set", file=sys.stderr)
        sys.exit(1)
    parts = urlsplit(base)
    return urlunsplit((parts.scheme, parts.netloc, "/news_dashboard_demo", "", ""))


def main() -> None:
    demo_url = _demo_database_url()
    parts = urlsplit(demo_url)
    db_name = parts.path.lstrip("/")
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))

    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{db_name}"')
            print(f"created database {db_name}")
        else:
            print(f"database {db_name} already exists")

    print(demo_url)


if __name__ == "__main__":
    main()
