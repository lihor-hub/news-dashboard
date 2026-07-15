"""Unit tests for connect() transient-connection retry behaviour.

These tests mock psycopg.connect so they run without Docker. The invariant:
connect() should wait out a not-yet-ready PostgreSQL (connection refused) by
retrying OperationalErrors with backoff, while non-connection errors and
exhausted retries still surface.
"""

from __future__ import annotations

import statistics
import time
from typing import Any, cast

import psycopg
import pytest
from psycopg_pool import PoolTimeout

_CONNECTION_REFUSED = "connection refused"
_SYNTAX_ERROR = "syntax error"


class _FakeConn:
    autocommit = False

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.statements: list[Any] = []

    def execute(self, *args: Any, **kwargs: Any) -> None:  # noqa: ARG002
        self.statements.append(args[0])

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class _FakePool:
    def __init__(self, conn: _FakeConn | None = None) -> None:
        self.conn = conn or _FakeConn()
        self.borrowed = 0
        self.returned: list[_FakeConn] = []
        self.closed_with: float | None = None

    def open(self, *, wait: bool, timeout: float) -> None:
        _ = wait, timeout

    def close(self, *, timeout: float) -> None:
        self.closed_with = timeout

    def getconn(self, *, timeout: float) -> _FakeConn:  # noqa: ARG002
        self.borrowed += 1
        return self.conn

    def putconn(self, conn: _FakeConn) -> None:
        self.returned.append(conn)


def test_connect_retries_transient_operational_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A connection refused is retried until PostgreSQL becomes reachable."""
    from news_dashboard import db

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("DB_CONNECT_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setenv("DB_CONNECT_MAX_ATTEMPTS", "5")

    attempts = {"n": 0}

    def fake_connect(dsn: str, row_factory: Any = None) -> _FakeConn:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise psycopg.OperationalError(_CONNECTION_REFUSED)
        return _FakeConn()

    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("news_dashboard.db.psycopg.connect", fake_connect)
    monkeypatch.setattr("news_dashboard.db.time.sleep", fake_sleep)

    with db.connect(database_url="postgresql://u:p@localhost:5432/db") as conn:
        assert isinstance(conn, _FakeConn)

    assert attempts["n"] == 3
    assert sleeps == [0.0, 0.0]


def test_connect_gives_up_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once attempts are exhausted the original OperationalError is re-raised."""
    from news_dashboard import db

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("DB_CONNECT_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setenv("DB_CONNECT_MAX_ATTEMPTS", "3")

    attempts = {"n": 0}

    def fake_connect(dsn: str, row_factory: Any = None) -> _FakeConn:
        attempts["n"] += 1
        raise psycopg.OperationalError(_CONNECTION_REFUSED)

    def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("news_dashboard.db.psycopg.connect", fake_connect)
    monkeypatch.setattr("news_dashboard.db.time.sleep", fake_sleep)

    with (
        pytest.raises(psycopg.OperationalError, match=_CONNECTION_REFUSED),
        db.connect(database_url="postgresql://u:p@localhost:5432/db"),
    ):
        pass

    assert attempts["n"] == 3


def test_connect_does_not_retry_non_connection_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Programming/other errors must surface immediately without retrying."""
    from news_dashboard import db

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("DB_CONNECT_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setenv("DB_CONNECT_MAX_ATTEMPTS", "5")

    attempts = {"n": 0}

    def fake_connect(dsn: str, row_factory: Any = None) -> _FakeConn:
        attempts["n"] += 1
        raise psycopg.ProgrammingError(_SYNTAX_ERROR)

    def fake_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr("news_dashboard.db.psycopg.connect", fake_connect)
    monkeypatch.setattr("news_dashboard.db.time.sleep", fake_sleep)

    with (
        pytest.raises(psycopg.ProgrammingError, match=_SYNTAX_ERROR),
        db.connect(database_url="postgresql://u:p@localhost:5432/db"),
    ):
        pass

    assert attempts["n"] == 1


def test_default_runtime_connect_reuses_pool_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default runtime connections borrow from the process-local pool."""
    from news_dashboard import db

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setattr(db, "_POOL", _FakePool())
    monkeypatch.setattr(db, "_POOL_DSN", "postgresql://u:p@localhost:5432/db")

    with db.connect() as first:
        first_backend = id(first)
    with db.connect() as second:
        second_backend = id(second)

    pool = cast("_FakePool", db._POOL)
    assert pool.borrowed == 2
    assert len(pool.returned) == 2
    assert first_backend == second_backend
    assert pool.conn.commits == 2
    assert pool.conn.closed is False
    reset_statement = str(pool.conn.statements[-1])
    assert "RESET ALL" in reset_statement
    assert "UNLISTEN *" in reset_statement


def test_default_runtime_connect_rolls_back_and_resets_pool_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exceptions roll back and pooled connections are reset before return."""
    from news_dashboard import db

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    fake_pool = _FakePool()
    monkeypatch.setattr(db, "_POOL", fake_pool)
    monkeypatch.setattr(db, "_POOL_DSN", "postgresql://u:p@localhost:5432/db")

    def raise_boom() -> None:
        message = "boom"
        raise ValueError(message)

    with pytest.raises(ValueError, match="boom"), db.connect():
        raise_boom()

    assert fake_pool.conn.commits == 0
    assert fake_pool.conn.rollbacks >= 1
    assert fake_pool.returned == [fake_pool.conn]
    assert fake_pool.conn.autocommit is False
    reset_statement = str(fake_pool.conn.statements[-1])
    assert "RESET ALL" in reset_statement
    assert "SELECT pg_advisory_unlock_all()" in reset_statement


def test_default_runtime_connect_logs_pool_acquire_timeout(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An exhausted pool times out with a clear log message."""
    from news_dashboard import db

    class TimeoutPool(_FakePool):
        def getconn(self, *, timeout: float) -> _FakeConn:  # noqa: ARG002
            message = "pool exhausted"
            raise PoolTimeout(message)

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("DB_POOL_TIMEOUT_SECONDS", "0.5")
    monkeypatch.setattr(db, "_POOL", TimeoutPool())
    monkeypatch.setattr(db, "_POOL_DSN", "postgresql://u:p@localhost:5432/db")

    with pytest.raises(PoolTimeout, match="pool exhausted"), db.connect():
        pass

    assert "Timed out acquiring PostgreSQL connection from runtime pool" in caplog.text


def test_close_connection_pool_uses_bounded_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shutdown closes the pool without waiting indefinitely."""
    from news_dashboard import db

    fake_pool = _FakePool()
    monkeypatch.setenv("DB_POOL_CLOSE_TIMEOUT_SECONDS", "0.25")
    monkeypatch.setattr(db, "_POOL", fake_pool)
    monkeypatch.setattr(db, "_POOL_DSN", "postgresql://u:p@localhost:5432/db")

    db.close_connection_pool()

    assert fake_pool.closed_with == 0.25
    assert db._POOL is None
    assert db._POOL_DSN is None


def test_pool_settings_validate_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pool capacity settings must be bounded and coherent."""
    from news_dashboard import db

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("DB_POOL_MIN_SIZE", "4")
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "2")

    with pytest.raises(
        db.DatabasePoolConfigError,
        match="DB_POOL_MIN_SIZE must be less than or equal to DB_POOL_MAX_SIZE",
    ):
        db.open_connection_pool()


def test_open_connection_pool_uses_existing_startup_retry_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pool startup waits out transient PostgreSQL readiness like direct connect."""
    from news_dashboard import db

    opened_with: dict[str, float] = {}
    created_with: dict[str, Any] = {}

    class StartupPool(_FakePool):
        def __init__(self, *_args: Any, **kwargs: Any) -> None:
            super().__init__()
            created_with.update(kwargs)

        def open(self, *, wait: bool, timeout: float) -> None:
            opened_with["timeout"] = timeout
            opened_with["wait"] = float(wait)

    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("DB_CONNECT_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("DB_CONNECT_RETRY_DELAY_SECONDS", "1.5")
    monkeypatch.setattr(db, "ConnectionPool", StartupPool)
    monkeypatch.setattr(db, "_POOL", None)
    monkeypatch.setattr(db, "_POOL_DSN", None)

    db.open_connection_pool()
    db.close_connection_pool()

    assert opened_with == {"timeout": 6.0, "wait": 1.0}
    assert created_with["kwargs"]["prepare_threshold"] is None


def test_postgres_runtime_pool_reuses_backend_and_resets_session_state(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Borrowed runtime connections reuse a backend without leaking session state."""
    from news_dashboard import db

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("DB_POOL_MIN_SIZE", "1")
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "1")
    db.close_connection_pool()
    db.open_connection_pool()
    try:
        with db.connect() as conn:
            first_pid = conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
            original_search_path = conn.execute(
                "SELECT current_setting('search_path') AS path"
            ).fetchone()["path"]
            conn.execute("SET search_path TO pg_catalog")

        with db.connect() as conn:
            second_pid = conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
            search_path = conn.execute("SELECT current_setting('search_path') AS path").fetchone()[
                "path"
            ]
    finally:
        db.close_connection_pool()

    assert second_pid == first_pid
    assert search_path == original_search_path
    assert search_path != "pg_catalog"


@pytest.mark.perf_serial
def test_postgres_runtime_pool_reduces_repeated_select_overhead(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local repeated SELECT 1 overhead is materially lower through the pool."""
    from news_dashboard import db

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("DB_POOL_MIN_SIZE", "1")
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "1")
    db.close_connection_pool()

    direct_times: list[float] = []
    pooled_times: list[float] = []
    for _ in range(40):
        started = time.perf_counter()
        with psycopg.connect(pg_clean) as conn:
            conn.execute("SELECT 1").fetchone()
        direct_times.append(time.perf_counter() - started)

    db.open_connection_pool()
    try:
        for _ in range(40):
            started = time.perf_counter()
            with db.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            pooled_times.append(time.perf_counter() - started)
    finally:
        db.close_connection_pool()

    assert statistics.median(direct_times) / statistics.median(pooled_times) >= 5
