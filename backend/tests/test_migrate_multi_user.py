"""Tests for #131 — migrate-multi-user CLI command."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import news_dashboard.db as db_mod
from news_dashboard.db import connect, init_db
from news_dashboard.ingest import sync_sources
from news_dashboard.migrate import _check_prerequisites, _row_count, app

runner = CliRunner()


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    sync_sources(db)
    return db


def _insert_article(db_path: Path, *, url_suffix: str = "1", state: str = "done") -> int:
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


def test_migration_creates_seed_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _setup_db(tmp_path)
    monkeypatch.setattr(db_mod, "DB_PATH", db)
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result = runner.invoke(app, ["migrate-multi-user"])
    assert result.exit_code == 0, result.output

    with connect(db) as conn:
        users = conn.execute("SELECT username FROM users").fetchall()
    assert len(users) == 1
    assert users[0]["username"] == "alice"


def test_migration_migrates_article_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _setup_db(tmp_path)
    aid = _insert_article(db, url_suffix="m1", state="done")
    monkeypatch.setattr(db_mod, "DB_PATH", db)
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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _setup_db(tmp_path)
    monkeypatch.setattr(db_mod, "DB_PATH", db)
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result = runner.invoke(app, ["migrate-multi-user"])
    assert result.exit_code == 0, result.output

    with connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM user_sources").fetchone()["count"]
    assert count > 0


def test_migration_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _setup_db(tmp_path)
    _insert_article(db, url_suffix="i1", state="done")
    monkeypatch.setattr(db_mod, "DB_PATH", db)
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


def test_migration_dry_run_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _setup_db(tmp_path)
    _insert_article(db, url_suffix="d1", state="done")
    monkeypatch.setattr(db_mod, "DB_PATH", db)
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


def test_migration_aborts_on_missing_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "bare.db"
    init_db(db)
    with connect(db) as conn:
        conn.execute("DROP TABLE IF EXISTS user_article_state")
    monkeypatch.setattr(db_mod, "DB_PATH", db)
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result = runner.invoke(app, ["migrate-multi-user"])
    assert result.exit_code != 0
    assert "prerequisite schema missing" in result.output.lower() or "ERROR" in result.output


def test_migration_skips_user_creation_if_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _setup_db(tmp_path)
    monkeypatch.setattr(db_mod, "DB_PATH", db)
    from news_dashboard.auth import create_user

    create_user("existing", "pass")
    monkeypatch.setattr(db_mod, "DB_PATH", db)
    monkeypatch.setenv("SEED_USER", "alice")
    monkeypatch.setenv("SEED_PASSWORD", "password123")

    result = runner.invoke(app, ["migrate-multi-user"])
    assert result.exit_code == 0, result.output
    assert "Users already exist" in result.output

    with connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    assert count == 1
