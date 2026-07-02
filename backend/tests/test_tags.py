"""Tests for user-defined tags/collections (#652)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import create_user, require_auth
from news_dashboard.db import connect
from news_dashboard.ingest import list_articles, search_articles, sync_sources
from news_dashboard.main import app
from news_dashboard.tags import (
    add_tag_to_article,
    create_tag,
    delete_tag,
    list_tags,
    list_tags_for_article,
    remove_tag_from_article,
    rename_tag,
)


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


def _authed_client(user_id: int) -> TestClient:
    client = TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": f"user-{user_id}",
        "email": None,
        "is_admin": False,
    }
    return client


# ── Tag CRUD ─────────────────────────────────────────────────────────────────


def test_create_and_list_tags(db: str) -> None:
    alice = _make_user(db, "alice")
    tag = create_tag(alice, "rust", "#ff0000", db_path=db)
    assert tag["name"] == "rust"
    assert tag["color"] == "#ff0000"

    tags = list_tags(alice, db_path=db)
    assert len(tags) == 1
    assert tags[0]["name"] == "rust"
    assert tags[0]["article_count"] == 0


def test_rename_tag(db: str) -> None:
    alice = _make_user(db, "alice")
    tag = create_tag(alice, "rust", db_path=db)
    renamed = rename_tag(tag["id"], alice, "rustlang", db_path=db)
    assert renamed is not None
    assert renamed["name"] == "rustlang"


def test_rename_tag_not_owned_returns_none(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    tag = create_tag(alice, "rust", db_path=db)
    assert rename_tag(tag["id"], bob, "hijacked", db_path=db) is None


def test_delete_tag_removes_associations_without_deleting_article(db: str) -> None:
    alice = _make_user(db, "alice")
    tag = create_tag(alice, "rust", db_path=db)
    article_id = _insert_article(db)
    assert add_tag_to_article(alice, article_id, tag["id"], db_path=db)

    assert delete_tag(tag["id"], alice, db_path=db)
    assert list_tags_for_article(alice, article_id, db_path=db) == []
    # Article itself should still exist.
    with connect(db) as conn:
        row = conn.execute("SELECT id FROM articles WHERE id = %s", (article_id,)).fetchone()
    assert row is not None


def test_delete_tag_not_owned_returns_false(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    tag = create_tag(alice, "rust", db_path=db)
    assert delete_tag(tag["id"], bob, db_path=db) is False


def test_duplicate_tag_name_raises(db: str) -> None:
    from psycopg.errors import UniqueViolation

    alice = _make_user(db, "alice")
    create_tag(alice, "rust", db_path=db)
    with pytest.raises(UniqueViolation):
        create_tag(alice, "rust", db_path=db)


# ── Applying tags to articles ────────────────────────────────────────────────


def test_add_and_remove_tag_on_article(db: str) -> None:
    alice = _make_user(db, "alice")
    tag = create_tag(alice, "rust", db_path=db)
    article_id = _insert_article(db)

    assert add_tag_to_article(alice, article_id, tag["id"], db_path=db)
    tags = list_tags_for_article(alice, article_id, db_path=db)
    assert [t["name"] for t in tags] == ["rust"]

    assert remove_tag_from_article(alice, article_id, tag["id"], db_path=db)
    assert list_tags_for_article(alice, article_id, db_path=db) == []


def test_add_tag_to_article_idempotent(db: str) -> None:
    alice = _make_user(db, "alice")
    tag = create_tag(alice, "rust", db_path=db)
    article_id = _insert_article(db)

    assert add_tag_to_article(alice, article_id, tag["id"], db_path=db)
    assert add_tag_to_article(alice, article_id, tag["id"], db_path=db)
    tags = list_tags_for_article(alice, article_id, db_path=db)
    assert len(tags) == 1


def test_add_tag_not_owned_by_user_fails(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    tag = create_tag(alice, "rust", db_path=db)
    article_id = _insert_article(db)

    assert add_tag_to_article(bob, article_id, tag["id"], db_path=db) is False


def test_tag_is_orthogonal_to_workflow_state(db: str) -> None:
    """An article can be `done` and tagged, independently of its workflow state."""
    from news_dashboard.ingest import transition_article_state

    alice = _make_user(db, "alice")
    tag = create_tag(alice, "rust", db_path=db)
    article_id = _insert_article(db)
    add_tag_to_article(alice, article_id, tag["id"], db_path=db)

    transition_article_state(article_id, "done", user_id=alice, db_path=db)

    tags = list_tags_for_article(alice, article_id, db_path=db)
    assert [t["name"] for t in tags] == ["rust"]
    articles = list_articles(state="done", user_id=alice, db_path=db)
    assert any(a["id"] == article_id for a in articles)


# ── Filter by tag ─────────────────────────────────────────────────────────────


def test_list_articles_filters_by_tag(db: str) -> None:
    alice = _make_user(db, "alice")
    tag = create_tag(alice, "rust", db_path=db)
    tagged_id = _insert_article(db, "tagged")
    untagged_id = _insert_article(db, "untagged")
    add_tag_to_article(alice, tagged_id, tag["id"], db_path=db)

    results = list_articles(tag_id=tag["id"], user_id=alice, db_path=db)
    ids = {a["id"] for a in results}
    assert tagged_id in ids
    assert untagged_id not in ids


def test_search_articles_filters_by_tag(db: str) -> None:
    alice = _make_user(db, "alice")
    tag = create_tag(alice, "rust", db_path=db)
    tagged_id = _insert_article(db, "tagged")
    untagged_id = _insert_article(db, "untagged")
    add_tag_to_article(alice, tagged_id, tag["id"], db_path=db)

    results = search_articles(q="", tag_id=tag["id"], user_id=alice, db_path=db)
    ids = {a["id"] for a in results}
    assert tagged_id in ids
    assert untagged_id not in ids


# ── Per-user isolation ────────────────────────────────────────────────────────


def test_tags_are_private_per_user(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    create_tag(alice, "rust", db_path=db)

    assert [t["name"] for t in list_tags(alice, db_path=db)] == ["rust"]
    assert list_tags(bob, db_path=db) == []


def test_article_tag_visibility_is_per_user(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    alice_tag = create_tag(alice, "rust", db_path=db)
    bob_tag = create_tag(bob, "rust", db_path=db)
    article_id = _insert_article(db)

    add_tag_to_article(alice, article_id, alice_tag["id"], db_path=db)

    assert [t["name"] for t in list_tags_for_article(alice, article_id, db_path=db)] == ["rust"]
    assert list_tags_for_article(bob, article_id, db_path=db) == []

    # Bob tagging the same article with his own tag doesn't leak to Alice's view.
    add_tag_to_article(bob, article_id, bob_tag["id"], db_path=db)
    assert len(list_tags_for_article(alice, article_id, db_path=db)) == 1
    assert len(list_tags_for_article(bob, article_id, db_path=db)) == 1


# ── API endpoints ─────────────────────────────────────────────────────────────


def test_tag_endpoints_full_flow(db: str) -> None:
    alice = _make_user(db, "alice")
    article_id = _insert_article(db)
    client = _authed_client(alice)

    create_resp = client.post("/api/tags", json={"name": "rust", "color": "#ff0000"})
    assert create_resp.status_code == 200
    tag_id = create_resp.json()["id"]

    list_resp = client.get("/api/tags")
    assert list_resp.status_code == 200
    assert list_resp.json()["items"][0]["name"] == "rust"

    rename_resp = client.patch(f"/api/tags/{tag_id}", json={"name": "rustlang"})
    assert rename_resp.status_code == 200
    assert rename_resp.json()["name"] == "rustlang"

    add_resp = client.post(f"/api/articles/{article_id}/tags", json={"tag_id": tag_id})
    assert add_resp.status_code == 200

    article_tags_resp = client.get(f"/api/articles/{article_id}/tags")
    assert article_tags_resp.status_code == 200
    assert article_tags_resp.json()["items"][0]["id"] == tag_id

    by_tag_resp = client.get(f"/api/tags/{tag_id}/articles")
    assert by_tag_resp.status_code == 200
    assert any(a["id"] == article_id for a in by_tag_resp.json()["items"])

    filtered_resp = client.get("/api/articles", params={"tag_id": tag_id})
    assert filtered_resp.status_code == 200
    assert any(a["id"] == article_id for a in filtered_resp.json()["items"])

    remove_resp = client.delete(f"/api/articles/{article_id}/tags/{tag_id}")
    assert remove_resp.status_code == 200

    delete_resp = client.delete(f"/api/tags/{tag_id}")
    assert delete_resp.status_code == 200

    delete_again_resp = client.delete(f"/api/tags/{tag_id}")
    assert delete_again_resp.status_code == 404


def test_create_tag_endpoint_rejects_blank_name(db: str) -> None:
    alice = _make_user(db, "alice")
    client = _authed_client(alice)
    response = client.post("/api/tags", json={"name": "   "})
    assert response.status_code == 400


def test_add_article_tag_endpoint_404s_for_missing_article(db: str) -> None:
    alice = _make_user(db, "alice")
    tag = create_tag(alice, "rust", db_path=db)
    client = _authed_client(alice)
    response = client.post("/api/articles/999999/tags", json={"tag_id": tag["id"]})
    assert response.status_code == 404


def test_add_article_tag_endpoint_404s_for_other_users_tag(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    tag = create_tag(alice, "rust", db_path=db)
    article_id = _insert_article(db)
    client = _authed_client(bob)
    response = client.post(f"/api/articles/{article_id}/tags", json={"tag_id": tag["id"]})
    assert response.status_code == 404
