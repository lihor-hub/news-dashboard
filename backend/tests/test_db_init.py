"""Unit tests for init_db PostgreSQL transaction-safety behaviour.

These tests mock the connect() context manager so they run without Docker.
The key invariant: each schema statement must execute in its own transaction
so that a failing statement does not put psycopg3 into ABORTED state and
prevent every subsequent statement — and the final commit() — from running.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

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


def test_init_db_postgres_continues_after_statement_failure(tmp_path: Any) -> None:
    """A failing schema statement must not prevent subsequent ones from running.

    Before the fix, all 47 statements shared one psycopg3 transaction: a single
    failure left the transaction in ABORTED state, causing every later execute()
    and the final commit() to raise InFailedSqlTransaction.
    """
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
        patch("news_dashboard.db.connect", fake_connect),
        patch("news_dashboard.db.POSTGRES_SCHEMA", fake_schema),
        patch("news_dashboard.db.POSTGRES_MULTIUSER_SCHEMA", []),
    ):
        from news_dashboard.db import init_db

        init_db()  # must not raise

    assert "stmt_ok_1" in applied
    assert "stmt_ok_2" in applied
    assert "WILL_FAIL" not in applied


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
