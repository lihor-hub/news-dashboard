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


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "postgres: marks tests that require a live PostgreSQL instance",
    )


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
    service_url = os.environ.get("TEST_DATABASE_URL")
    if service_url:
        init_db(database_url=service_url)
        yield service_url
        return

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers package not installed (pip install testcontainers[postgres])")

    try:
        container = PostgresContainer("postgres:16")
        container.start()
    except Exception as exc:
        pytest.skip(f"PostgreSQL container could not start (Docker unavailable?): {exc}")

    # Build a plain postgresql:// URL compatible with psycopg3.
    # get_connection_url() returns a SQLAlchemy-style URL with driver prefix;
    # strip the driver component so psycopg3 recognises the scheme.
    raw = container.get_connection_url()
    url = raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    init_db(database_url=url)

    yield url

    container.stop()


@pytest.fixture
def pg_clean(pg_url: str) -> str:
    """Truncate all test-managed tables and return the DB URL.

    ``RESTART IDENTITY CASCADE`` resets serial sequences and propagates
    truncation to child tables via FK constraints, giving each test a
    fully clean slate without needing a separate container per test.
    """
    import psycopg

    with psycopg.connect(pg_url) as conn:
        conn.execute(
            "TRUNCATE user_article_recommendations, user_article_state, user_sources,"
            " briefing_articles, briefings, articles, sources, users RESTART IDENTITY CASCADE"
        )
        conn.commit()
    return pg_url
