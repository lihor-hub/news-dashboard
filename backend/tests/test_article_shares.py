"""Tests for in-platform article sharing (shares.py)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

import news_dashboard.db as db_mod
from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.ingest import sync_sources
from news_dashboard.shares import (
    ShareError,
    list_received_shares,
    mark_share_read,
    share_article,
    shareable_users,
    unread_share_count,
)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Path]:
    """A test schema with sources synced and DB_PATH patched for share helpers."""
    path = tmp_path / "shares.db"
    sync_sources(path)
    orig = db_mod.DB_PATH
    db_mod.DB_PATH = path
    try:
        yield path
    finally:
        db_mod.DB_PATH = orig


def _make_user(username: str) -> int:
    return int(create_user(username, "password123")["id"])


def _insert_article(db_path: Path, suffix: str = "1") -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug,
              source_name, category, kind, state)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                f"https://example.com/art{suffix}",
                f"https://example.com/art{suffix}",
                f"Article {suffix}",
                "python-insider",
                "Python Insider",
                "python",
                "rss_feed",
                "today",
            ),
        ).fetchone()
    return int(row["id"])


def test_share_and_list(db: Path) -> None:
    alice = _make_user("alice")
    bob = _make_user("bob")
    article_id = _insert_article(db)

    share_article(article_id=article_id, from_user_id=alice, to_user_id=bob, note="  read this  ")

    received = list_received_shares(bob)
    assert len(received) == 1
    assert received[0]["from_username"] == "alice"
    assert received[0]["article_title"] == "Article 1"
    assert received[0]["note"] == "read this"
    assert received[0]["read_at"] is None
    assert unread_share_count(bob) == 1
    # Sender sees nothing in their own inbox.
    assert list_received_shares(alice) == []


def test_mark_read(db: Path) -> None:
    alice = _make_user("alice")
    bob = _make_user("bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)

    assert mark_share_read(int(share["id"]), bob) is True
    assert unread_share_count(bob) == 0
    # Idempotent: already-read share returns False.
    assert mark_share_read(int(share["id"]), bob) is False
    # Other users cannot mark someone else's share.
    assert mark_share_read(int(share["id"]), alice) is False


def test_shareable_users_excludes_self(db: Path) -> None:
    alice = _make_user("alice")
    _make_user("bob")
    usernames = {u["username"] for u in shareable_users(alice)}
    assert usernames == {"bob"}


def test_cannot_share_with_self(db: Path) -> None:
    alice = _make_user("alice")
    article_id = _insert_article(db)
    with pytest.raises(ShareError):
        share_article(article_id=article_id, from_user_id=alice, to_user_id=alice)


def test_share_unknown_article_raises(db: Path) -> None:
    alice = _make_user("alice")
    bob = _make_user("bob")
    with pytest.raises(ShareError):
        share_article(article_id=999999, from_user_id=alice, to_user_id=bob)
