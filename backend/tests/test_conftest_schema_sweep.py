"""Tests for the stale test_% schema sweep used by the pg_url fixture."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from hashlib import sha256
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_path_schema_cleanup_commits_each_drop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each schema drop releases PostgreSQL locks before the next drop."""
    import news_dashboard.db as db_module

    connection = MagicMock()
    connection_context = MagicMock()
    connection_context.__enter__.return_value = connection
    monkeypatch.setattr(db_module, "_open_connection", lambda _dsn: connection_context)

    db_module.drop_path_test_schemas(["test_a", "test_b"], "postgresql://example/test")

    assert connection.execute.call_count == 2
    assert connection.commit.call_count == 2


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


def test_sweep_skips_schemas_owned_by_a_still_alive_process() -> None:
    """PID-suffixed schemas whose owning process is still running are not dropped.

    Two concurrent pytest sessions sharing one TEST_DATABASE_URL must not be
    able to destroy each other's live worker schema: the sweep only treats a
    ``test_<workerid>_<pid>`` schema as stale once that PID is gone.
    """
    import psycopg
    from conftest import sweep_stale_test_schemas
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
        alive_schema = f"test_gw0_{os.getpid()}"

        with psycopg.connect(scratch_url, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(alive_schema)))

            sweep_stale_test_schemas(scratch_url)

            row = conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (alive_schema,),
            ).fetchone()
            assert row is not None
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin_conn:
            admin_conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(scratch_db)
                )
            )


def test_sweep_drops_schemas_owned_by_a_dead_process() -> None:
    """PID-suffixed schemas whose owning process has exited are genuinely stale."""
    import psycopg
    from conftest import sweep_stale_test_schemas
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
        # A short-lived subprocess whose PID is guaranteed dead once it exits.
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait(timeout=5)
        dead_schema = f"test_gw1_{proc.pid}"

        with psycopg.connect(scratch_url, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(dead_schema)))

            sweep_stale_test_schemas(scratch_url)

            row = conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (dead_schema,),
            ).fetchone()
            assert row is None
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin_conn:
            admin_conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(scratch_db)
                )
            )


def test_session_cleanup_drops_only_registered_path_schemas() -> None:
    """Successful sessions drop their own hash schemas without sweeping live workers."""
    import psycopg
    from psycopg import sql

    from news_dashboard.db import connect, drop_registered_path_test_schemas

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
        token = Path("news-dashboard-test-schemas") / uuid.uuid4().hex / "test.db"
        path_schema = f"test_{sha256(str(token).encode('utf-8')).hexdigest()[:16]}"
        live_worker_schema = f"test_gw0_{os.getpid()}"

        with psycopg.connect(scratch_url, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(live_worker_schema)))

        with connect(token, database_url=scratch_url):
            pass

        drop_registered_path_test_schemas(scratch_url)

        with psycopg.connect(scratch_url, autocommit=True) as conn:
            path_row = conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (path_schema,),
            ).fetchone()
            live_worker_row = conn.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s",
                (live_worker_schema,),
            ).fetchone()

        assert path_row is None
        assert live_worker_row is not None
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin_conn:
            admin_conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(scratch_db)
                )
            )


def test_successful_pytest_session_leaves_no_hash_schemas() -> None:
    """A successful representative Path-backed pytest run cleans up its schema."""
    import psycopg
    from psycopg import sql

    service_url = os.environ.get("TEST_DATABASE_URL")
    if not service_url:
        pytest.skip("TEST_DATABASE_URL not set")

    base_url, _, _dbname = service_url.rpartition("/")
    scratch_db = f"schema_session_scratch_{uuid.uuid4().hex[:12]}"
    scratch_url = f"{base_url}/{scratch_db}"
    admin_url = f"{base_url}/postgres"

    with psycopg.connect(admin_url, autocommit=True) as admin_conn:
        try:
            admin_conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(scratch_db)))
        except psycopg.errors.InsufficientPrivilege:
            pytest.skip("connected role lacks CREATEDB; cannot build an isolated scratch database")
    try:
        env = os.environ.copy()
        env["DATABASE_URL"] = scratch_url
        env["TEST_DATABASE_URL"] = scratch_url
        env["PYTEST_ADDOPTS"] = ""
        env.pop("PYTEST_XDIST_WORKER", None)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-n0",
                "backend/tests/test_pgvector_migration.py::test_vector_extension_is_available",
            ],
            check=True,
            cwd=Path(__file__).parents[2],
            env=env,
            timeout=60,
        )

        with psycopg.connect(scratch_url, autocommit=True) as conn:
            rows = conn.execute(
                r"""
                SELECT schema_name FROM information_schema.schemata
                WHERE schema_name ~ '^test_[0-9a-f]{16}$'
                """
            ).fetchall()
        assert rows == []
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin_conn:
            admin_conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(scratch_db)
                )
            )
