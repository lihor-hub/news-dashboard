"""Shared pytest fixtures for backend tests.

The ``pg_url`` fixture starts a PostgreSQL container via testcontainers and
initialises the full schema once per test session.  Tests that depend on it
are skipped automatically when testcontainers is not installed or when Docker
is not reachable (e.g. on a dev machine without Docker Desktop).

The ``pg_clean`` fixture truncates briefing/article/source rows before each
test so every integration test starts from a known empty state.

Auth: ``override_auth`` is an autouse fixture that patches ``require_auth``
and ``require_admin`` to return a fake admin user so existing API tests keep
working without needing real sessions.  Auth-specific tests that need real
session behaviour should clear ``app.dependency_overrides`` themselves.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from news_dashboard.db import init_db

# Load .env from the repo root when running locally (no-op in CI where the
# variables are injected by the GitHub Actions service container instead).
_env_file = Path(__file__).parent.parent.parent / ".env"
if _env_file.exists():
    with _env_file.open() as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

# Ensure SESSION_SECRET is set for all tests so auth module can load.
os.environ.setdefault("TEST_SESSION_SECRET", "test-secret-key-not-for-production")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-apply markers based on fixture usage.

    Any test that requests ``pg_url`` or ``pg_clean`` is tagged ``db`` so
    ``pytest -m "not db"`` reliably excludes all Postgres-dependent tests
    without requiring manual marker decoration in every test file.
    """
    db_mark = pytest.mark.db
    for item in items:
        fixtures: list[str] = getattr(item, "fixturenames", [])
        if "pg_url" in fixtures or "pg_clean" in fixtures:
            item.add_marker(db_mark, append=True)


_SCHEMA_SWEEP_LOCK_KEY = 727271


def sweep_stale_test_schemas(dsn: str) -> None:
    """Drop leaked ``test_%`` schemas from crashed pytest-xdist runs.

    Guarded by a Postgres advisory lock. This must only be called before any
    xdist worker has created its own ``test_{worker_id}`` schema (i.e. from
    ``pytest_configure`` in the xdist *master* process, never from a worker's
    ``pg_url`` fixture) — otherwise the sweep can race with, and drop, a
    schema another already-running worker is actively using.
    """
    import psycopg
    from psycopg import sql

    with psycopg.connect(dsn, autocommit=True) as conn:
        lock_row = conn.execute(
            "SELECT pg_try_advisory_lock(%s)", (_SCHEMA_SWEEP_LOCK_KEY,)
        ).fetchone()
        got_lock = lock_row is not None and lock_row[0]
        if not got_lock:
            return
        try:
            rows = conn.execute(
                r"SELECT schema_name FROM information_schema.schemata "
                r"WHERE schema_name LIKE 'test\_%' ESCAPE '\'"
            ).fetchall()
            for (schema_name,) in rows:
                conn.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
                )
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_SCHEMA_SWEEP_LOCK_KEY,))


def pytest_configure(config: pytest.Config) -> None:
    """Sweep leaked test_% schemas once, before any xdist worker spawns.

    Runs only in the xdist *master* process (or a plain non-xdist run), never
    in a worker, so it always executes before any worker creates its own
    schema — avoiding a race where the sweep drops a schema another worker
    is actively using.
    """
    del config
    if os.environ.get("PYTEST_XDIST_WORKER"):
        return
    service_url = os.environ.get("TEST_DATABASE_URL")
    if service_url:
        sweep_stale_test_schemas(service_url)


_FAKE_ADMIN = {
    "id": 1,
    "username": "testadmin",
    "email": None,
    "is_admin": True,
    "created_at": "2026-01-01T00:00:00",
    "last_login_at": None,
}


@pytest.fixture(autouse=True)
def override_auth() -> Generator[None]:
    """Inject a fake admin user into all tests that use the FastAPI app.

    Auth-specific tests that need real session behaviour should call
    ``app.dependency_overrides.clear()`` at the start of the test.
    """
    from news_dashboard.auth import require_admin, require_auth
    from news_dashboard.main import app

    app.dependency_overrides[require_auth] = lambda: _FAKE_ADMIN
    app.dependency_overrides[require_admin] = lambda: _FAKE_ADMIN
    yield
    app.dependency_overrides.pop(require_auth, None)
    app.dependency_overrides.pop(require_admin, None)


@pytest.fixture(scope="session")
def pg_url() -> Generator[str]:
    """Start a PostgreSQL container and return a psycopg-compatible DSN.

    CI can provide TEST_DATABASE_URL via a GitHub Actions service container,
    avoiding Docker-in-pytest startup hangs. Locally, skip automatically if
    testcontainers is not installed or if the Docker daemon is unreachable.
    """
    import psycopg

    service_url = os.environ.get("TEST_DATABASE_URL")
    container = None

    if not service_url:
        try:
            from testcontainers.postgres import PostgresContainer
        except ImportError:
            pytest.skip(
                "testcontainers package not installed (pip install testcontainers[postgres])"
            )

        try:
            container = PostgresContainer("postgres:16")
            container.start()
        except Exception as exc:
            pytest.skip(f"PostgreSQL container could not start (Docker unavailable?): {exc}")

        # Build a plain postgresql:// URL compatible with psycopg3.
        raw = container.get_connection_url()
        service_url = raw.replace("postgresql+psycopg2://", "postgresql://").replace(
            "postgresql+psycopg://", "postgresql://"
        )

    # If running with pytest-xdist, isolate each worker with its own schema.
    worker_id = os.environ.get("PYTEST_XDIST_WORKER")
    worker_schema = None
    original_url = service_url

    if service_url and worker_id and worker_id != "master":
        worker_schema = f"test_{worker_id}"

        # Create/recreate the schema using the base DSN
        from psycopg import sql

        with psycopg.connect(original_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(worker_schema))
            )
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(worker_schema)))

        # Append connection options to set search_path
        separator = "&" if "?" in original_url else "?"
        service_url = f"{original_url}{separator}options=-csearch_path%3D{worker_schema}"

    orig_db_url = os.environ.get("DATABASE_URL")
    if service_url:
        os.environ["DATABASE_URL"] = service_url

    if service_url:
        init_db(database_url=service_url)

    yield service_url

    if orig_db_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = orig_db_url

    if worker_schema and original_url:
        try:
            from psycopg import sql

            with psycopg.connect(original_url, autocommit=True) as conn:
                conn.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(worker_schema)
                    )
                )
        except Exception:  # noqa: S110
            pass

    if container:
        container.stop()


@pytest.fixture
def pg_clean(pg_url: str) -> str:
    """Truncate all test-managed tables and return the DB URL.

    ``RESTART IDENTITY CASCADE`` resets serial sequences and propagates
    truncation to child tables via FK constraints, giving each test a
    fully clean slate without needing a separate container per test.
    """
    import psycopg

    with psycopg.connect(pg_url, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE user_article_recommendations, user_article_state, user_sources,"
            " user_interest_profiles, user_settings, user_push_subscriptions,"
            " article_highlights, article_shares, user_events, briefing_articles, briefings,"
            " ingest_run_sources, ingest_runs, scheduled_job_runs, article_tags, user_tags,"
            " articles, sources, users"
            " RESTART IDENTITY CASCADE"
        )
    return pg_url
