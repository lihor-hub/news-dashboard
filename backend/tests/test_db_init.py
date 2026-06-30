"""Unit tests for init_db PostgreSQL transaction-safety behaviour.

These tests mock the connect() context manager so they run without Docker.
The key invariant: schema failures must surface while successful runs remain
cached on the hot path.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

_SIMULATED_FAILURE = "simulated: column already exists"


def test_init_db_postgres_applies_all_statements(tmp_path: Any) -> None:
    """Every statement in POSTGRES_SCHEMA + POSTGRES_MULTIUSER_SCHEMA is executed."""
    applied: list[str] = []

    @contextmanager
    def fake_connect(db_path: Any = None, database_url: Any = None) -> Any:
        class _Conn:
            def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
                applied.append(sql.strip())

        yield _Conn()

    fake_schema = ["CREATE TABLE a", "CREATE TABLE b", "CREATE TABLE c"]

    with (
        patch("news_dashboard.db.connect", fake_connect),
        patch("news_dashboard.db.POSTGRES_SCHEMA", fake_schema),
        patch("news_dashboard.db.POSTGRES_MULTIUSER_SCHEMA", []),
    ):
        from news_dashboard.db import init_db

        init_db()

    assert applied == fake_schema


def test_init_db_postgres_failure_surfaces_and_is_not_cached(
    tmp_path: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing schema statement must raise and retry on the next init_db()."""
    applied: list[str] = []

    @contextmanager
    def fake_connect(db_path: Any = None, database_url: Any = None) -> Any:
        class _Conn:
            def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
                if sql.strip() == "WILL_FAIL":
                    raise RuntimeError(_SIMULATED_FAILURE)
                applied.append(sql.strip())

        yield _Conn()

    fake_schema = ["stmt_ok_1", "WILL_FAIL", "stmt_ok_2"]

    with (
        caplog.at_level(logging.ERROR, logger="news_dashboard.db"),
        patch("news_dashboard.db.connect", fake_connect),
        patch("news_dashboard.db.POSTGRES_SCHEMA", fake_schema),
        patch("news_dashboard.db.POSTGRES_MULTIUSER_SCHEMA", []),
    ):
        from news_dashboard.db import SchemaInitializationError, init_db

        token = tmp_path / "partial-schema.db"
        with pytest.raises(SchemaInitializationError, match="WILL_FAIL"):
            init_db(token)

        with pytest.raises(SchemaInitializationError, match="WILL_FAIL"):
            init_db(token)

    assert applied == ["stmt_ok_1", "stmt_ok_1"]
    assert "WILL_FAIL" not in applied
    assert "stmt_ok_2" not in applied
    assert "Schema initialization failed on statement: WILL_FAIL" in caplog.text


def test_init_db_postgres_each_statement_uses_own_connection(tmp_path: Any) -> None:
    """connect() must be called once per statement, not once for all statements."""
    connect_calls: list[str] = []
    statements_per_call: list[list[str]] = []

    @contextmanager
    def fake_connect(db_path: Any = None, database_url: Any = None) -> Any:
        this_call: list[str] = []
        statements_per_call.append(this_call)
        connect_calls.append("open")

        class _Conn:
            def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
                this_call.append(sql.strip())

        yield _Conn()

    fake_schema = ["stmt_a", "stmt_b", "stmt_c"]

    with (
        patch("news_dashboard.db.connect", fake_connect),
        patch("news_dashboard.db.POSTGRES_SCHEMA", fake_schema),
        patch("news_dashboard.db.POSTGRES_MULTIUSER_SCHEMA", []),
    ):
        from news_dashboard.db import init_db

        init_db()

    assert len(connect_calls) == 3, "expected one connect() call per statement"
    for per_call in statements_per_call:
        assert len(per_call) == 1, "each connection must execute exactly one statement"


def test_init_db_postgres_caches_successful_schema_runs(tmp_path: Any) -> None:
    """Repeated hot-path init_db() calls should not replay every schema statement."""
    connect_calls: list[str] = []

    @contextmanager
    def fake_connect(db_path: Any = None, database_url: Any = None) -> Any:
        connect_calls.append("open")

        class _Conn:
            def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
                return None

        yield _Conn()

    fake_schema = ["CREATE TABLE cache_test_a", "CREATE TABLE cache_test_b"]

    with (
        patch("news_dashboard.db.connect", fake_connect),
        patch("news_dashboard.db.POSTGRES_SCHEMA", fake_schema),
        patch("news_dashboard.db.POSTGRES_MULTIUSER_SCHEMA", []),
    ):
        from news_dashboard.db import init_db

        token = tmp_path / "cache-test.db"
        init_db(token)
        init_db(token)

    assert len(connect_calls) == len(fake_schema)
