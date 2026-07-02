"""Tests for the stale test_% schema sweep used by the pg_url fixture."""

from __future__ import annotations

import os

import pytest


def test_sweep_stale_test_schemas() -> None:
    """The sweep drops leaked test_% schemas, and is a no-op when another
    session already holds the sweep's advisory lock.

    Both behaviors are exercised in a single test (rather than two separate
    tests) because the sweep coordinates via a *global* Postgres advisory
    lock: under pytest-xdist, separate tests can land on different worker
    processes and race on that lock, so the "lock already held" scenario
    must be driven from within one test to stay deterministic.
    """
    import psycopg
    from conftest import _SCHEMA_SWEEP_LOCK_KEY, sweep_stale_test_schemas

    service_url = os.environ.get("TEST_DATABASE_URL")
    if not service_url:
        pytest.skip("TEST_DATABASE_URL not set")

    decoy_schema = "test_leaked_decoy_schema"
    locked_decoy_schema = "test_leaked_locked_decoy_schema"

    with psycopg.connect(service_url, autocommit=True) as conn:
        # Case 1: a leaked schema is dropped when the lock is free.
        conn.execute(f'DROP SCHEMA IF EXISTS "{decoy_schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{decoy_schema}"')

        sweep_stale_test_schemas(service_url)

        row = conn.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
            (decoy_schema,),
        ).fetchone()
        assert row is None

        # Case 2: sweep is a no-op when another session holds the lock.
        conn.execute(f'DROP SCHEMA IF EXISTS "{locked_decoy_schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{locked_decoy_schema}"')

        with psycopg.connect(service_url, autocommit=True) as holder_conn:
            holder_conn.execute("SELECT pg_advisory_lock(%s)", (_SCHEMA_SWEEP_LOCK_KEY,))
            try:
                sweep_stale_test_schemas(service_url)

                row = conn.execute(
                    "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                    (locked_decoy_schema,),
                ).fetchone()
                assert row is not None
            finally:
                holder_conn.execute("SELECT pg_advisory_unlock(%s)", (_SCHEMA_SWEEP_LOCK_KEY,))
                conn.execute(f'DROP SCHEMA IF EXISTS "{locked_decoy_schema}" CASCADE')
