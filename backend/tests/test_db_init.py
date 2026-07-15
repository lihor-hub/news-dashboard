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
_UNEXPECTED_ROLLBACK = "rollback should not be called on success"


def test_init_db_postgres_applies_all_statements(tmp_path: Any) -> None:
    """Every statement in POSTGRES_SCHEMA + POSTGRES_MULTIUSER_SCHEMA is executed."""
    applied: list[str] = []
    commits: list[str] = []

    @contextmanager
    def fake_connect(db_path: Any = None, database_url: Any = None) -> Any:
        class _Conn:
            def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
                applied.append(sql.strip())

            def commit(self) -> None:
                commits.append("commit")

            def rollback(self) -> None:
                raise AssertionError(_UNEXPECTED_ROLLBACK)

        yield _Conn()

    fake_schema = ["CREATE TABLE a", "CREATE TABLE b", "CREATE TABLE c"]

    with (
        patch("news_dashboard.db.connect", fake_connect),
        patch("news_dashboard.db.POSTGRES_SCHEMA", fake_schema),
        patch("news_dashboard.db.POSTGRES_MULTIUSER_SCHEMA", []),
        patch("news_dashboard.db.POSTGRES_POST_BACKFILL_SCHEMA", []),
        patch("news_dashboard.db._ensure_vector_extension", lambda *_a, **_k: None),
        patch("news_dashboard.db._backfill_embedding_vectors", lambda *_a, **_k: 0),
    ):
        from news_dashboard.db import init_db

        init_db()

    assert applied == fake_schema
    assert commits == ["commit"] * len(fake_schema)


def test_init_db_postgres_failure_surfaces_and_is_not_cached(
    tmp_path: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing schema statement must raise and retry on the next init_db()."""
    applied: list[str] = []
    commits: list[str] = []
    rollbacks: list[str] = []

    @contextmanager
    def fake_connect(db_path: Any = None, database_url: Any = None) -> Any:
        class _Conn:
            def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
                if sql.strip() == "WILL_FAIL":
                    raise RuntimeError(_SIMULATED_FAILURE)
                applied.append(sql.strip())

            def commit(self) -> None:
                commits.append("commit")

            def rollback(self) -> None:
                rollbacks.append("rollback")

        yield _Conn()

    fake_schema = ["stmt_ok_1", "WILL_FAIL", "stmt_ok_2"]

    with (
        caplog.at_level(logging.ERROR, logger="news_dashboard.db"),
        patch("news_dashboard.db.connect", fake_connect),
        patch("news_dashboard.db.POSTGRES_SCHEMA", fake_schema),
        patch("news_dashboard.db.POSTGRES_MULTIUSER_SCHEMA", []),
        patch("news_dashboard.db.POSTGRES_POST_BACKFILL_SCHEMA", []),
        patch("news_dashboard.db._ensure_vector_extension", lambda *_a, **_k: None),
        patch("news_dashboard.db._backfill_embedding_vectors", lambda *_a, **_k: 0),
    ):
        from news_dashboard.db import SchemaInitializationError, init_db

        token = tmp_path / "partial-schema.db"
        with pytest.raises(SchemaInitializationError, match="WILL_FAIL"):
            init_db(token)

        with pytest.raises(SchemaInitializationError, match="WILL_FAIL"):
            init_db(token)

    assert applied == ["stmt_ok_1", "stmt_ok_1"]
    assert commits == ["commit", "commit"]
    assert rollbacks == ["rollback", "rollback"]
    assert "WILL_FAIL" not in applied
    assert "stmt_ok_2" not in applied
    assert "Schema initialization failed on statement: WILL_FAIL" in caplog.text


def test_init_db_postgres_reuses_one_connection_per_schema_phase(tmp_path: Any) -> None:
    """Schema phases reuse sessions while each statement commits independently."""
    connect_calls: list[str] = []
    statements_per_call: list[list[str]] = []
    commits: list[str] = []

    @contextmanager
    def fake_connect(db_path: Any = None, database_url: Any = None) -> Any:
        this_call: list[str] = []
        statements_per_call.append(this_call)
        connect_calls.append("open")

        class _Conn:
            def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
                this_call.append(sql.strip())

            def commit(self) -> None:
                commits.append("commit")

            def rollback(self) -> None:
                raise AssertionError(_UNEXPECTED_ROLLBACK)

        yield _Conn()

    fake_schema = ["stmt_a", "stmt_b", "stmt_c"]
    fake_post_backfill_schema = ["stmt_after_backfill"]

    with (
        patch("news_dashboard.db.connect", fake_connect),
        patch("news_dashboard.db.POSTGRES_SCHEMA", fake_schema),
        patch("news_dashboard.db.POSTGRES_MULTIUSER_SCHEMA", []),
        patch("news_dashboard.db.POSTGRES_POST_BACKFILL_SCHEMA", fake_post_backfill_schema),
        patch("news_dashboard.db._ensure_vector_extension", lambda *_a, **_k: None),
        patch("news_dashboard.db._backfill_embedding_vectors", lambda *_a, **_k: 0),
    ):
        from news_dashboard.db import init_db

        init_db()

    assert len(connect_calls) == 2, "expected one connect() call per schema phase"
    assert statements_per_call == [fake_schema, fake_post_backfill_schema]
    assert commits == ["commit"] * (len(fake_schema) + len(fake_post_backfill_schema))


def test_init_db_postgres_caches_successful_schema_runs(tmp_path: Any) -> None:
    """Repeated hot-path init_db() calls should not replay every schema statement."""
    connect_calls: list[str] = []
    commits: list[str] = []

    @contextmanager
    def fake_connect(db_path: Any = None, database_url: Any = None) -> Any:
        connect_calls.append("open")

        class _Conn:
            def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
                return None

            def commit(self) -> None:
                commits.append("commit")

            def rollback(self) -> None:
                raise AssertionError(_UNEXPECTED_ROLLBACK)

        yield _Conn()

    fake_schema = ["CREATE TABLE cache_test_a", "CREATE TABLE cache_test_b"]

    with (
        patch("news_dashboard.db.connect", fake_connect),
        patch("news_dashboard.db.POSTGRES_SCHEMA", fake_schema),
        patch("news_dashboard.db.POSTGRES_MULTIUSER_SCHEMA", []),
        patch("news_dashboard.db.POSTGRES_POST_BACKFILL_SCHEMA", []),
        patch("news_dashboard.db._ensure_vector_extension", lambda *_a, **_k: None),
        patch("news_dashboard.db._backfill_embedding_vectors", lambda *_a, **_k: 0),
    ):
        from news_dashboard.db import init_db

        token = tmp_path / "cache-test.db"
        init_db(token)
        init_db(token)

    assert len(connect_calls) == 1
    assert commits == ["commit"] * len(fake_schema)


def test_run_schema_statements_rolls_back_failed_postgres_statement(pg_clean: str) -> None:
    """A failed statement rolls back without losing prior committed statements."""
    from news_dashboard.db import SchemaInitializationError, _run_schema_statements, connect

    statements = [
        "CREATE TABLE schema_recovery_before (id INTEGER)",
        "ALTER TABLE schema_recovery_missing ADD COLUMN value INTEGER",
        "CREATE TABLE schema_recovery_after (id INTEGER)",
    ]

    with pytest.raises(SchemaInitializationError, match="schema_recovery_missing"):
        _run_schema_statements(statements, None, pg_clean)

    with connect(database_url=pg_clean) as conn:
        rows = conn.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name IN ('schema_recovery_before', 'schema_recovery_after')
            ORDER BY table_name
            """
        ).fetchall()

    assert [row["table_name"] for row in rows] == ["schema_recovery_before"]

    _run_schema_statements(["CREATE TABLE schema_recovery_after (id INTEGER)"], None, pg_clean)

    with connect(database_url=pg_clean) as conn:
        row = conn.execute("SELECT to_regclass('schema_recovery_after')").fetchone()

    assert row is not None
    assert row["to_regclass"] == "schema_recovery_after"


def test_postgres_schema_adds_entities_column() -> None:
    """The articles.entities cache column ships as an idempotent statement."""
    from news_dashboard.db import POSTGRES_SCHEMA

    assert any(
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS entities TEXT" in stmt
        for stmt in POSTGRES_SCHEMA
    )
