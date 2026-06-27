"""Tests for in-platform article sharing (shares.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.ingest import sync_sources
from news_dashboard.shares import (
    ShareError,
    add_annotation,
    add_message,
    generate_share_context,
    get_share,
    list_annotations,
    list_messages,
    list_received_shares,
    mark_share_read,
    share_article,
    shareable_users,
    unread_share_count,
)


@pytest.fixture
def db(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """A test database with sources synced for share helpers."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    return pg_clean


def _make_user(db_path: str, username: str) -> int:
    return int(create_user(username, "password123", db_path=db_path)["id"])


def _insert_article(db_path: str, suffix: str = "1") -> int:
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


def test_share_and_list(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)

    share_article(article_id=article_id, from_user_id=alice, to_user_id=bob, note="  read this  ")

    received = list_received_shares(bob)
    assert len(received) == 1
    assert received[0]["from_username"] == "alice"
    assert received[0]["article_title"] == "Article 1"
    assert received[0]["note"] == "read this"
    assert received[0]["read_at"] is None
    assert received[0]["annotations"] == []
    assert received[0]["messages"] == []
    assert unread_share_count(bob) == 1
    # Sender sees nothing in their own inbox.
    assert list_received_shares(alice) == []


def test_mark_read(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)

    assert mark_share_read(int(share["id"]), bob) is True
    assert unread_share_count(bob) == 0
    # Idempotent: already-read share returns False.
    assert mark_share_read(int(share["id"]), bob) is False
    # Other users cannot mark someone else's share.
    assert mark_share_read(int(share["id"]), alice) is False


def test_shareable_users_excludes_self(db: str) -> None:
    alice = _make_user(db, "alice")
    _make_user(db, "bob")
    usernames = {u["username"] for u in shareable_users(alice)}
    assert usernames == {"bob"}


def test_cannot_share_with_self(db: str) -> None:
    alice = _make_user(db, "alice")
    article_id = _insert_article(db)
    with pytest.raises(ShareError):
        share_article(article_id=article_id, from_user_id=alice, to_user_id=alice)


def test_share_unknown_article_raises(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    with pytest.raises(ShareError):
        share_article(article_id=999999, from_user_id=alice, to_user_id=bob)


# ── Annotation tests ──────────────────────────────────────────────────────────


def test_add_and_list_annotations(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    share_id = int(share["id"])

    ann = add_annotation(
        share_id, highlighted_text="important passage", offset_chars=42, note="key insight"
    )
    assert ann["highlighted_text"] == "important passage"
    assert ann["offset_chars"] == 42
    assert ann["note"] == "key insight"

    annotations = list_annotations(share_id)
    assert len(annotations) == 1
    assert annotations[0]["highlighted_text"] == "important passage"


def test_annotations_included_in_list_received_shares(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    add_annotation(int(share["id"]), highlighted_text="highlighted bit", note="why it matters")

    received = list_received_shares(bob)
    assert len(received[0]["annotations"]) == 1
    assert received[0]["annotations"][0]["highlighted_text"] == "highlighted bit"


# ── Message tests ─────────────────────────────────────────────────────────────


def test_add_and_list_messages(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    share_id = int(share["id"])

    msg1 = add_message(share_id, alice, "What do you think?")
    msg2 = add_message(share_id, bob, "Great article!")

    assert msg1["message"] == "What do you think?"
    assert msg2["message"] == "Great article!"

    messages = list_messages(share_id)
    assert len(messages) == 2
    assert messages[0]["username"] == "alice"
    assert messages[1]["username"] == "bob"


def test_messages_included_in_get_share(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    share_id = int(share["id"])
    add_message(share_id, alice, "Check this out")

    detail = get_share(share_id, bob)
    assert detail is not None
    assert len(detail["messages"]) == 1
    assert detail["messages"][0]["message"] == "Check this out"


def test_get_share_returns_none_for_unauthorized(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    charlie = _make_user(db, "charlie")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)

    assert get_share(int(share["id"]), charlie) is None


# ── AI context generation tests ───────────────────────────────────────────────


def test_generate_share_context_no_api_key(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BRIEFING_API_KEY", raising=False)

    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)

    result = generate_share_context(int(share["id"]))
    assert result is None


def test_generate_share_context_stores_summary(db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    share_id = int(share["id"])
    add_annotation(share_id, highlighted_text="the key section", note="this is relevant")

    mock_completion = MagicMock()
    summary = "Alice highlighted this because it matters. You will find it useful."
    mock_completion.choices[0].message.content = summary

    with (
        patch("news_dashboard.ai_client.get_openai_client") as mock_client_factory,
        patch("news_dashboard.ai_client.chat_create", return_value=mock_completion),
    ):
        mock_client_factory.return_value = MagicMock()
        result = generate_share_context(share_id)

    assert result == summary

    detail = get_share(share_id, bob)
    assert detail is not None
    assert detail["context_summary"] == result
