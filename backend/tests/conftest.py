"""Shared pytest fixtures for backend tests.

The ``pg_url`` fixture starts a PostgreSQL container via testcontainers and
initialises the full schema once per test session.  Tests that depend on it
are skipped automatically when testcontainers is not installed or when Docker
is not reachable (e.g. on a dev machine without Docker Desktop).

The ``pg_clean`` fixture truncates briefing/article/source rows before each
test so every integration test starts from a known empty state.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from news_dashboard.db import init_db


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "postgres: marks tests that require a live PostgreSQL instance",
    )


@pytest.fixture(scope="session")
def pg_url() -> Generator[str]:
    """Start a PostgreSQL container and return a psycopg-compatible DSN.

    Skips automatically if testcontainers is not installed or if the Docker
    daemon is unreachable (graceful degradation for environments without
    Docker).
    """
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
            "TRUNCATE briefing_articles, briefings, articles, sources RESTART IDENTITY CASCADE"
        )
        conn.commit()
    return pg_url
