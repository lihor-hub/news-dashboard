"""Tests for the stale test_% schema sweep used by the pg_url fixture."""

from __future__ import annotations

import os
import uuid

import pytest


def test_sweep_stale_test_schemas() -> None:
    """The sweep drops leaked test_% schemas, and is a no-op when another
    session already holds the sweep's advisory lock.

    Runs against a scratch database created just for this test, never
    against ``TEST_DATABASE_URL`` itself: under pytest-xdist that DSN's
    default database is shared by every worker's live ``test_{worker_id}``
    schema, and ``sweep_stale_test_schemas`` drops *all* ``test_%`` schemas
    it finds — so invoking it there would nuke sibling workers' active
    schemas mid-run. Postgres advisory locks are also scoped per-database,
    so the scratch database gives the "lock already held" case (driven
    within the same test, see above) a clean slate too.
    """
    import psycopg
    from conftest import _SCHEMA_SWEEP_LOCK_KEY, sweep_stale_test_schemas
    from psycopg import sql

    service_url = os.environ.get("TEST_DATABASE_URL")
    if not service_url:
        pytest.skip("TEST_DATABASE_URL not set")

    base_url, _, _dbname = service_url.rpartition("/")
    scratch_db = f"schema_sweep_scratch_{uuid.uuid4().hex[:12]}"
    scratch_url = f"{base_url}/{scratch_db}"
    admin_url = f"{base_url}/postgres"

    with psycopg.connect(admin_url, autocommit=True) as admin_conn:
        try:
            admin_conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(scratch_db)))
        except psycopg.errors.InsufficientPrivilege:
            pytest.skip("connected role lacks CREATEDB; cannot build an isolated scratch database")
    try:
        decoy_schema = "test_leaked_decoy_schema"
        locked_decoy_schema = "test_leaked_locked_decoy_schema"

        with psycopg.connect(scratch_url, autocommit=True) as conn:
            # Case 1: a leaked schema is dropped when the lock is free.
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(decoy_schema)))

            sweep_stale_test_schemas(scratch_url)

            row = conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (decoy_schema,),
            ).fetchone()
            assert row is None

            # Case 2: sweep is a no-op when another session holds the lock.
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(locked_decoy_schema)))

            with psycopg.connect(scratch_url, autocommit=True) as holder_conn:
                holder_conn.execute("SELECT pg_advisory_lock(%s)", (_SCHEMA_SWEEP_LOCK_KEY,))
                try:
                    sweep_stale_test_schemas(scratch_url)

                    row = conn.execute(
                        "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                        (locked_decoy_schema,),
                    ).fetchone()
                    assert row is not None
                finally:
                    holder_conn.execute("SELECT pg_advisory_unlock(%s)", (_SCHEMA_SWEEP_LOCK_KEY,))
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin_conn:
            admin_conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(scratch_db)
                )
            )
