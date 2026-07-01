"""Tests for in-platform article sharing (shares.py)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import create_user, require_auth
from news_dashboard.body_fetch import get_article
from news_dashboard.db import connect
from news_dashboard.ingest import sync_sources
from news_dashboard.main import app
from news_dashboard.shares import (
    ShareError,
    add_annotation,
    add_message,
    fetch_shared_article_body,
    generate_share_context,
    get_share,
    get_shared_article,
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


def _insert_private_article(db_path: str, *, owner_user_id: int) -> int:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, owner_user_id)
            VALUES ('private-share', 'Private Share', 'https://private.example.com/feed.xml',
                    'private', 'rss_feed', %s)
            """,
            (owner_user_id,),
        )
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug,
              source_name, category, kind, state)
            VALUES ('https://private.example.com/share', 'https://private.example.com/share',
                    'Private Share Article', 'private-share', 'Private Share',
                    'private', 'rss_feed', 'today')
            RETURNING id
            """
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


def test_cannot_share_other_users_private_source_article(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_private_article(db, owner_user_id=alice)

    with pytest.raises(ShareError, match="not found"):
        share_article(article_id=article_id, from_user_id=bob, to_user_id=alice)

    with connect(db) as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM article_shares").fetchone()
    assert row["count"] == 0
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    assert share["article_id"] == article_id


def test_shared_article_grants_share_scoped_private_source_access(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    charlie = _make_user(db, "charlie")
    article_id = _insert_private_article(db, owner_user_id=alice)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    share_id = int(share["id"])

    assert get_article(article_id, user_id=bob) is None

    recipient_article = get_shared_article(share_id, bob)
    assert recipient_article is not None
    assert recipient_article["id"] == article_id
    assert recipient_article["title"] == "Private Share Article"

    sender_article = get_shared_article(share_id, alice)
    assert sender_article is not None
    assert sender_article["id"] == article_id

    assert get_shared_article(share_id, charlie) is None


def test_shared_article_api_grants_sender_and_recipient_access(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_private_article(db, owner_user_id=alice)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    share_id = int(share["id"])

    client = TestClient(app, raise_server_exceptions=True)
    for user_id in (alice, bob):
        app.dependency_overrides[require_auth] = lambda user_id=user_id: {
            "id": user_id,
            "username": f"user-{user_id}",
            "email": None,
            "is_admin": False,
        }
        response = client.get(f"/api/shares/{share_id}/article")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == article_id
        assert payload["title"] == "Private Share Article"


def test_shared_article_api_does_not_weaken_normal_article_visibility(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    charlie = _make_user(db, "charlie")
    article_id = _insert_private_article(db, owner_user_id=alice)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    share_id = int(share["id"])
    client = TestClient(app, raise_server_exceptions=True)

    app.dependency_overrides[require_auth] = lambda: {
        "id": bob,
        "username": "bob",
        "email": None,
        "is_admin": False,
    }
    normal_response = client.get(f"/api/articles/{article_id}")
    shared_response = client.get(f"/api/shares/{share_id}/article")

    app.dependency_overrides[require_auth] = lambda: {
        "id": charlie,
        "username": "charlie",
        "email": None,
        "is_admin": False,
    }
    unauthorized_shared_response = client.get(f"/api/shares/{share_id}/article")

    assert normal_response.status_code == 404
    assert shared_response.status_code == 200
    assert unauthorized_shared_response.status_code == 404


def test_shared_article_body_fetch_is_anchored_to_visible_share(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    charlie = _make_user(db, "charlie")
    article_id = _insert_private_article(db, owner_user_id=alice)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    share_id = int(share["id"])

    with connect(db) as conn:
        conn.execute(
            """
            UPDATE articles
            SET body = 'Cached private body', body_status = 'ok'
            WHERE id = %s
            """,
            (article_id,),
        )

    article = fetch_shared_article_body(share_id, bob)
    assert article is not None
    assert article["id"] == article_id
    assert article["body"] == "Cached private body"

    assert fetch_shared_article_body(share_id, charlie) is None


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
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)

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


# ── Payload bounds (#602) ─────────────────────────────────────────────────────


def _authed_client(user_id: int) -> TestClient:
    client = TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": f"user-{user_id}",
        "email": None,
        "is_admin": False,
    }
    return client


def test_share_endpoint_rejects_oversized_note(db: str) -> None:
    from news_dashboard.main import MAX_SHARE_NOTE_LENGTH

    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    client = _authed_client(alice)

    response = client.post(
        f"/api/articles/{article_id}/share",
        json={"to_user_id": bob, "note": "x" * (MAX_SHARE_NOTE_LENGTH + 1)},
    )
    assert response.status_code == 422


def test_annotation_endpoint_rejects_blank_highlighted_text(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    client = _authed_client(bob)

    response = client.post(
        f"/api/shares/{share['id']}/annotations",
        json={"highlighted_text": "   "},
    )
    assert response.status_code == 422


def test_annotation_endpoint_rejects_oversized_highlighted_text(db: str) -> None:
    from news_dashboard.main import MAX_ANNOTATION_HIGHLIGHT_LENGTH

    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    client = _authed_client(bob)

    response = client.post(
        f"/api/shares/{share['id']}/annotations",
        json={"highlighted_text": "x" * (MAX_ANNOTATION_HIGHLIGHT_LENGTH + 1)},
    )
    assert response.status_code == 422


def test_message_endpoint_rejects_blank_message(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    client = _authed_client(bob)

    response = client.post(f"/api/shares/{share['id']}/messages", json={"message": "   "})
    assert response.status_code == 422


def test_message_endpoint_rejects_oversized_message(db: str) -> None:
    from news_dashboard.main import MAX_SHARE_MESSAGE_LENGTH

    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    client = _authed_client(bob)

    response = client.post(
        f"/api/shares/{share['id']}/messages",
        json={"message": "x" * (MAX_SHARE_MESSAGE_LENGTH + 1)},
    )
    assert response.status_code == 422


def test_message_endpoint_accepts_message_at_length_boundary(db: str) -> None:
    from news_dashboard.main import MAX_SHARE_MESSAGE_LENGTH

    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    share = share_article(article_id=article_id, from_user_id=alice, to_user_id=bob)
    client = _authed_client(bob)

    response = client.post(
        f"/api/shares/{share['id']}/messages",
        json={"message": "x" * MAX_SHARE_MESSAGE_LENGTH},
    )
    assert response.status_code == 200
