"""Tests for #87 workflow state model — transitions, starred flag, Later expiry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from news_dashboard.db import connect, init_db
from news_dashboard.ingest import (
    list_articles,
    send_article_later,
    set_article_starred,
    sync_sources,
    transition_article_state,
)


def _insert_article(db_path: Path, *, state: str = "today", starred: int = 0) -> int:
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, starred
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                f"https://example.com/{state}-{starred}",
                f"https://example.com/{state}-{starred}",
                f"Test {state}",
                "python-insider",
                "Python Insider",
                "python",
                "rss_feed",
                state,
                starred,
            ),
        ).fetchone()
    return int(row["id"] if isinstance(row, dict) else row[0])


# ─── Allowed transitions ────────────────────────────────────────────────────


def test_today_to_done(tmp_path: Path) -> None:
    sync_sources(tmp_path / "news.db")
    db = tmp_path / "news.db"
    aid = _insert_article(db, state="today")
    updated = transition_article_state(aid, "done", db_path=db)
    assert updated is not None
    assert updated["state"] == "done"
    assert updated["done_at"] is not None


def test_today_to_later(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="today")
    updated = send_article_later(aid, days=2, db_path=db)
    assert updated is not None
    assert updated["state"] == "later"
    assert updated["later_until"] is not None
    # later_until should be ~2 days from now
    until = datetime.fromisoformat(updated["later_until"])
    delta = until - datetime.now(timezone.utc)
    assert 1 < delta.total_seconds() / 3600 < 50


def test_today_to_skipped(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="today")
    updated = transition_article_state(aid, "skipped", db_path=db)
    assert updated is not None
    assert updated["state"] == "skipped"
    assert updated["skipped_at"] is not None


def test_today_to_archived(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="today")
    updated = transition_article_state(aid, "archived", db_path=db)
    assert updated is not None
    assert updated["state"] == "archived"
    assert updated["archived_at"] is not None


def test_later_to_today(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="later")
    updated = transition_article_state(aid, "today", db_path=db)
    assert updated is not None
    assert updated["state"] == "today"
    assert updated["restored_at"] is not None
    assert updated["later_until"] is None


def test_later_to_done(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="later")
    updated = transition_article_state(aid, "done", db_path=db)
    assert updated is not None
    assert updated["state"] == "done"


def test_later_to_archived(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="later")
    updated = transition_article_state(aid, "archived", db_path=db)
    assert updated is not None
    assert updated["state"] == "archived"


def test_done_to_archived(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="done")
    updated = transition_article_state(aid, "archived", db_path=db)
    assert updated is not None
    assert updated["state"] == "archived"


def test_skipped_to_today(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="skipped")
    updated = transition_article_state(aid, "today", db_path=db)
    assert updated is not None
    assert updated["state"] == "today"
    assert updated["restored_at"] is not None


def test_skipped_to_archived(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="skipped")
    updated = transition_article_state(aid, "archived", db_path=db)
    assert updated is not None
    assert updated["state"] == "archived"


def test_archived_to_today(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="archived")
    updated = transition_article_state(aid, "today", db_path=db)
    assert updated is not None
    assert updated["state"] == "today"
    assert updated["restored_at"] is not None


def test_archived_to_done(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="archived")
    updated = transition_article_state(aid, "done", db_path=db)
    assert updated is not None
    assert updated["state"] == "done"


# ─── Disallowed transitions ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        ("done", "today"),
        ("done", "skipped"),
        ("done", "later"),
        ("skipped", "done"),
        ("skipped", "later"),
        ("archived", "skipped"),
        ("archived", "later"),
    ],
)
def test_disallowed_transitions(tmp_path: Path, from_state: str, to_state: str) -> None:
    db = tmp_path / f"news-{from_state}-{to_state}.db"
    sync_sources(db)
    aid = _insert_article(db, state=from_state)
    with pytest.raises(ValueError, match="not allowed"):
        transition_article_state(aid, to_state, db_path=db)


# ─── Starred cannot be skipped ──────────────────────────────────────────────


def test_starred_cannot_be_skipped(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="today", starred=1)
    with pytest.raises(ValueError, match="starred articles cannot be skipped"):
        transition_article_state(aid, "skipped", db_path=db)


def test_unstarred_can_be_skipped(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="today", starred=0)
    updated = transition_article_state(aid, "skipped", db_path=db)
    assert updated is not None
    assert updated["state"] == "skipped"


# ─── Star / unstar ──────────────────────────────────────────────────────────


def test_star_article(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="today", starred=0)
    updated = set_article_starred(aid, True, db_path=db)
    assert updated is not None
    assert updated["starred"] in (1, True)
    assert updated["starred_at"] is not None


def test_unstar_article(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="today", starred=1)
    updated = set_article_starred(aid, False, db_path=db)
    assert updated is not None
    assert updated["starred"] in (0, False)


# ─── Later expiry ───────────────────────────────────────────────────────────


def test_expired_later_appears_in_today(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    # Insert an article with later_until in the past
    init_db(db)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, later_until
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'later', ?)
            """,
            (
                "https://example.com/expired-later",
                "https://example.com/expired-later",
                "Expired Later Article",
                "python-insider",
                "Python Insider",
                "python",
                "rss_feed",
                past,
            ),
        )

    today_articles = list_articles(state="today", db_path=db)
    titles = [a["title"] for a in today_articles]
    assert "Expired Later Article" in titles


def test_active_later_does_not_appear_in_today(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    init_db(db)
    future = (datetime.now(timezone.utc) + timedelta(hours=23)).isoformat()
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, later_until
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'later', ?)
            """,
            (
                "https://example.com/active-later",
                "https://example.com/active-later",
                "Active Later Article",
                "python-insider",
                "Python Insider",
                "python",
                "rss_feed",
                future,
            ),
        )

    today_articles = list_articles(state="today", db_path=db)
    titles = [a["title"] for a in today_articles]
    assert "Active Later Article" not in titles

    later_articles = list_articles(state="later", db_path=db)
    later_titles = [a["title"] for a in later_articles]
    assert "Active Later Article" in later_titles


# ─── Invalid state / input validation ───────────────────────────────────────


def test_invalid_state_rejected(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="today")
    with pytest.raises(ValueError, match="invalid state"):
        transition_article_state(aid, "reading", db_path=db)


def test_later_days_must_be_positive(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    aid = _insert_article(db, state="today")
    with pytest.raises(ValueError, match="days must be >= 1"):
        send_article_later(aid, days=0, db_path=db)


def test_missing_article_returns_none(tmp_path: Path) -> None:
    db = tmp_path / "news.db"
    sync_sources(db)
    assert transition_article_state(9999, "done", db_path=db) is None
    assert set_article_starred(9999, True, db_path=db) is None
    assert send_article_later(9999, db_path=db) is None


# ─── Migration mapping ──────────────────────────────────────────────────────


def test_migration_mapping(tmp_path: Path) -> None:
    """Verify that existing legacy status rows get migrated to the new state column."""
    db = tmp_path / "news.db"
    # Insert articles with old status values before running migrations
    import sqlite3

    raw = sqlite3.connect(str(db))
    raw.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          url TEXT NOT NULL UNIQUE,
          canonical_url TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL DEFAULT '',
          source_slug TEXT NOT NULL DEFAULT 'python-insider',
          source_name TEXT NOT NULL DEFAULT 'Python Insider',
          category TEXT NOT NULL DEFAULT 'python',
          kind TEXT NOT NULL DEFAULT 'rss_feed',
          published_at TEXT,
          discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          status TEXT NOT NULL DEFAULT 'new',
          importance_score INTEGER NOT NULL DEFAULT 50,
          summary TEXT NOT NULL DEFAULT '',
          reason TEXT NOT NULL DEFAULT '',
          tags TEXT NOT NULL DEFAULT '',
          read_at TEXT,
          saved_at TEXT,
          skipped_at TEXT,
          archived_at TEXT,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for status in ["new", "read", "saved", "skipped", "archived"]:
        raw.execute(
            "INSERT INTO articles(url, canonical_url, title, status) VALUES (?, ?, ?, ?)",
            (f"https://example.com/{status}", f"https://example.com/{status}", status, status),
        )
    raw.commit()
    raw.close()

    # Running init_db triggers migration
    init_db(db)

    with connect(db) as conn:
        rows = conn.execute("SELECT status, state, starred FROM articles ORDER BY id").fetchall()

    mapping = {
        row["status"] if isinstance(row, dict) else row[0]: (
            (row["state"] if isinstance(row, dict) else row[1]),
            (row["starred"] if isinstance(row, dict) else row[2]),
        )
        for row in rows
    }
    assert mapping["new"] == ("today", 0)
    assert mapping["read"] == ("done", 0)
    assert mapping["saved"][0] == "today"
    assert mapping["saved"][1] in (1, True)
    assert mapping["skipped"] == ("skipped", 0)
    assert mapping["archived"] == ("archived", 0)
