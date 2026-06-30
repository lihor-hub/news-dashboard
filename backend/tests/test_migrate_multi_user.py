"""Tests for #131 — migrate-multi-user CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from news_dashboard.db import connect, init_db
from news_dashboard.ingest import sync_sources
from news_dashboard.migrate import _check_prerequisites, _row_count, app

runner = CliRunner()


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    sync_sources(db)
    return db


def _insert_article(db_path: Path | str, *, url_suffix: str = "1", state: str = "done") -> int:
    sync_sources(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug, source_name,
              category, kind, state, starred)
            VALUES (%s, %s, %s, %s, %s, 'tech', 'rss_feed', %s, FALSE)
            RETURNING id
            """,
            (
                f"https://example.com/art{url_suffix}",
                f"https://example.com/art{url_suffix}",
                f"Article {url_suffix}",
                "python-insider",
                "Python Insider",
                state,
            ),
        ).fetchone()
    return int(row[0] if isinstance(row, tuple) else row["id"])


# ── _row_count helper ─────────────────────────────────────────────────────────


def test_sqlite_to_postgres_requires_postgres_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    src = tmp_path / "old.sqlite"
    src.touch()
    result = runner.invoke(app, ["sqlite-to-postgres", str(src)])
    assert result.exit_code != 0
    assert "POSTGRES" in result.output or "DATABASE_URL" in result.output


def test_sqlite_to_postgres_rejects_missing_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    result = runner.invoke(app, ["sqlite-to-postgres", "/no/such/file.sqlite"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_sqlite_to_postgres_migrates_rows(
    tmp_path: Path, pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlite3

    # Build a legacy SQLite dump: sources lacks the newer health columns to
    # exercise the graceful-degradation path, articles carries all columns.
    src = tmp_path / "legacy.sqlite"
    sqlite = sqlite3.connect(src)
    # Sources lacks the newer health columns (graceful degradation) and stores
    # enabled as an integer 0/1 — the migrator must coerce it to a PG boolean.
    sqlite.execute(
        "CREATE TABLE sources(slug TEXT, name TEXT, url TEXT, category TEXT,"
        " kind TEXT, priority INTEGER, enabled INTEGER)"
    )
    sqlite.execute(
        "INSERT INTO sources VALUES('acme', 'Acme', 'https://acme.test', 'tech', 'rss_feed', 1, 1)"
    )
    sqlite.execute(
        "INSERT INTO sources VALUES('off', 'Off', 'https://off.test', 'tech', 'rss_feed', 1, 0)"
    )
    sqlite.execute(
        "CREATE TABLE articles(url TEXT, canonical_url TEXT, title TEXT, source_slug TEXT,"
        " source_name TEXT, category TEXT, kind TEXT, published_at TEXT, summary TEXT,"
        " reason TEXT, importance_score INTEGER, tags TEXT, status TEXT, discovered_at TEXT,"
        " read_at TEXT, saved_at TEXT, skipped_at TEXT, archived_at TEXT, updated_at TEXT)"
    )
    sqlite.execute(
        "INSERT INTO articles VALUES('https://acme.test/a', 'https://acme.test/a', 'Hello',"
        " 'acme', 'Acme', 'tech', 'rss_feed', NULL, 'sum', 'why', 50, '', 'new',"
        " '2026-06-01T00:00:00Z', NULL, NULL, NULL, NULL, '2026-06-01T00:00:00Z')"
    )
    sqlite.commit()
    sqlite.close()

    # Route the command's init_db()/connect() at an isolated schema in the test DB.
    schema_path = pg_clean
    monkeypatch.setenv("DATABASE_URL", pg_clean)

    # The migrator seeds sources before articles, so the article's FK to 'acme'
    # is satisfied within the same run — no pre-seeding needed.
    init_db(schema_path)

    result = runner.invoke(app, ["sqlite-to-postgres", str(src)])
    assert result.exit_code == 0, result.output
    assert "Migrated 2 source(s) and 1 article(s)" in result.output

    with connect(schema_path) as conn:
        articles = conn.execute("SELECT url, title FROM articles").fetchall()
        sources = conn.execute("SELECT slug, enabled FROM sources ORDER BY slug").fetchall()
    assert articles[0]["title"] == "Hello"
    # enabled integers are coerced to booleans
    enabled_by_slug = {s["slug"]: s["enabled"] for s in sources}
    assert enabled_by_slug["acme"] is True
    assert enabled_by_slug["off"] is False


def test_row_count_postgres_style() -> None:
    # Simulate a psycopg dict_row with 'count' key (lowercase)
    assert _row_count({"count": 3}) == 3


def test_row_count_none_returns_zero() -> None:
    assert _row_count(None) == 0


# ── _check_prerequisites ──────────────────────────────────────────────────────


def test_prerequisites_pass_when_schema_complete(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    with connect(db) as conn:
        missing = _check_prerequisites(conn)
    assert missing == []


def test_prerequisites_detect_missing_table(tmp_path: Path) -> None:
    db = tmp_path / "bare.db"
    init_db(db)
    with connect(db) as conn:
        conn.execute("DROP TABLE IF EXISTS user_article_state")
    with connect(db) as conn:
        missing = _check_prerequisites(conn)
    assert any("user_article_state" in m for m in missing)


# ── migrate-multi-user command ────────────────────────────────────────────────


def test_migration_creates_seed_user(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    db = pg_clean
    sync_sources(db)
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result = runner.invoke(app, ["migrate-multi-user"])
    assert result.exit_code == 0, result.output

    with connect(db) as conn:
        users = conn.execute("SELECT username FROM users").fetchall()
    assert len(users) == 1
    assert users[0]["username"] == "alice"


def test_migration_migrates_article_state(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    db = pg_clean
    aid = _insert_article(db, url_suffix="m1", state="done")
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result = runner.invoke(app, ["migrate-multi-user"])
    assert result.exit_code == 0, result.output

    with connect(db) as conn:
        uas = conn.execute(
            "SELECT state FROM user_article_state WHERE article_id = %s", (aid,)
        ).fetchone()
    assert uas is not None
    assert uas["state"] == "done"


def test_migration_seeds_source_subscriptions(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = pg_clean
    sync_sources(db)
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result = runner.invoke(app, ["migrate-multi-user"])
    assert result.exit_code == 0, result.output

    with connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM user_sources").fetchone()["count"]
    assert count > 0


def test_migration_is_idempotent(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    db = pg_clean
    _insert_article(db, url_suffix="i1", state="done")
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result1 = runner.invoke(app, ["migrate-multi-user"])
    assert result1.exit_code == 0, result1.output

    result2 = runner.invoke(app, ["migrate-multi-user"])
    assert result2.exit_code == 0, result2.output

    with connect(db) as conn:
        user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        uas_count = conn.execute("SELECT COUNT(*) AS count FROM user_article_state").fetchone()[
            "count"
        ]
    assert user_count == 1
    assert uas_count == 1


def test_migration_dry_run_does_not_write(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    db = pg_clean
    _insert_article(db, url_suffix="d1", state="done")
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result = runner.invoke(app, ["migrate-multi-user", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output

    with connect(db) as conn:
        user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        uas_count = conn.execute("SELECT COUNT(*) AS count FROM user_article_state").fetchone()[
            "count"
        ]
    assert user_count == 0
    assert uas_count == 0


def test_migration_aborts_on_missing_schema(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    db = pg_clean
    init_db(db)
    try:
        with connect(db) as conn:
            conn.execute("DROP TABLE IF EXISTS user_article_state")
        monkeypatch.setenv("DATABASE_URL", db)
        monkeypatch.setenv("SEED_USER", "alice")
        monkeypatch.setenv("SEED_PASSWORD", "password123")

        result = runner.invoke(app, ["migrate-multi-user"])
        assert result.exit_code != 0
        assert "prerequisite schema missing" in result.output.lower() or "ERROR" in result.output
    finally:
        from news_dashboard import db as db_mod

        db_mod._INITIALIZED_DATABASES.clear()
        init_db(db)


def test_migration_skips_user_creation_if_exists(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = pg_clean
    monkeypatch.setenv("DATABASE_URL", str(db))
    from news_dashboard.auth import create_user

    create_user("existing", "pass")
    monkeypatch.setenv("DATABASE_URL", str(db))
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result = runner.invoke(app, ["migrate-multi-user"])
    assert result.exit_code == 0, result.output
    assert "Users already exist" in result.output

    with connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    assert count == 1
