from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import create_user, require_auth
from news_dashboard.db import connect
from news_dashboard.ingest import sync_sources
from news_dashboard.main import app
from news_dashboard.personal_highlights import add_highlight, delete_highlight, list_highlights


@pytest.fixture
def db(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> str:
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
                f"https://example.com/highlight-{suffix}",
                f"https://example.com/highlight-{suffix}",
                f"Highlight Article {suffix}",
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
            VALUES ('private-highlights', 'Private Highlights',
                    'https://private.example.com/feed.xml', 'private', 'rss_feed', %s)
            """,
            (owner_user_id,),
        )
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug,
              source_name, category, kind, state)
            VALUES ('https://private.example.com/highlights',
                    'https://private.example.com/highlights',
                    'Private Highlight Article', 'private-highlights', 'Private Highlights',
                    'private', 'rss_feed', 'today')
            RETURNING id
            """
        ).fetchone()
    return int(row["id"])


def test_user_can_create_list_and_delete_private_highlights(db: str) -> None:
    user_id = _make_user(db, "alice")
    article_id = _insert_article(db)

    created = add_highlight(
        article_id,
        user_id,
        highlighted_text=" selected passage ",
        offset_chars=14,
        note=" remember this ",
    )

    assert created is not None
    assert created["highlighted_text"] == "selected passage"
    assert created["offset_chars"] == 14
    assert created["note"] == "remember this"
    assert list_highlights(article_id, user_id) == [created]
    assert delete_highlight(article_id, user_id, int(created["id"])) is True
    assert list_highlights(article_id, user_id) == []


def test_highlights_are_isolated_by_user(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)

    created = add_highlight(article_id, alice, highlighted_text="Alice only")

    assert created is not None
    assert list_highlights(article_id, bob) == []
    assert delete_highlight(article_id, bob, int(created["id"])) is False
    assert list_highlights(article_id, alice) == [created]


def test_cross_user_private_article_access_is_rejected(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_private_article(db, owner_user_id=alice)

    assert add_highlight(article_id, bob, highlighted_text="Nope") is None
    assert list_highlights(article_id, bob) is None


def test_highlight_api_is_auth_scoped(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    article_id = _insert_article(db)
    client = TestClient(app, raise_server_exceptions=True)

    app.dependency_overrides[require_auth] = lambda: {
        "id": alice,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    create_response = client.post(
        f"/api/articles/{article_id}/highlights",
        json={"highlighted_text": "API passage", "offset_chars": 7, "note": "API note"},
    )
    assert create_response.status_code == 200
    highlight_id = create_response.json()["id"]

    app.dependency_overrides[require_auth] = lambda: {
        "id": bob,
        "username": "bob",
        "email": None,
        "is_admin": False,
    }
    bob_list_response = client.get(f"/api/articles/{article_id}/highlights")
    bob_delete_response = client.delete(f"/api/articles/{article_id}/highlights/{highlight_id}")

    app.dependency_overrides[require_auth] = lambda: {
        "id": alice,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    alice_list_response = client.get(f"/api/articles/{article_id}/highlights")

    assert bob_list_response.status_code == 200
    assert bob_list_response.json()["items"] == []
    assert bob_delete_response.status_code == 200
    assert bob_delete_response.json() == {"ok": False}
    assert alice_list_response.status_code == 200
    assert alice_list_response.json()["items"][0]["id"] == highlight_id
