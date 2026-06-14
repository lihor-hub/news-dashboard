"""Tests for #128 — per-user source subscriptions and custom private sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import news_dashboard.db as db_mod
from news_dashboard.auth import create_user
from news_dashboard.db import connect, row_to_dict
from news_dashboard.ingest import list_articles, sync_sources

# ── helpers ───────────────────────────────────────────────────────────────────


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    sync_sources(db)
    return db


def _make_user(db_path: Path, username: str = "alice") -> int:
    orig = db_mod.DB_PATH
    db_mod.DB_PATH = db_path
    try:
        user = create_user(username, "pw")
    finally:
        db_mod.DB_PATH = orig
    return int(user["id"])


def _insert_article(db_path: Path, *, source_slug: str, url_suffix: str = "1") -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug, source_name,
              category, kind, state)
            VALUES (?, ?, ?, ?, ?, 'tech', 'rss_feed', 'today')
            RETURNING id
            """,
            (
                f"https://example.com/{url_suffix}",
                f"https://example.com/{url_suffix}",
                f"Article {url_suffix}",
                source_slug,
                source_slug,
            ),
        ).fetchone()
    return int(row["id"] if isinstance(row, dict) else row[0])


def _global_slug(db_path: Path) -> str:
    """Return the slug of an arbitrary global source."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT slug FROM sources WHERE owner_user_id IS NULL LIMIT 1"
        ).fetchone()
        return str(row_to_dict(row)["slug"])


def _add_private_source(db_path: Path, *, slug: str, owner_user_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
            VALUES (?, ?, 'https://example.com/feed', 'tech', 'rss_feed', 0, 1, ?)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, owner_user_id),
        )


# ── subscription model ────────────────────────────────────────────────────────


def test_global_source_visible_to_all_users_by_default(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)

    # Use an existing global source slug from sync_sources
    slug = _global_slug(db)

    aid = _insert_article(db, source_slug=slug)
    articles = list_articles(state="today", db_path=db, user_id=uid)
    assert any(a["id"] == aid for a in articles)


def test_unsubscribed_source_articles_hidden(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)

    slug = _global_slug(db)

    aid = _insert_article(db, source_slug=slug)

    # Explicitly unsubscribe
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (?, ?, 0)",
            (uid, slug),
        )

    articles = list_articles(state="today", db_path=db, user_id=uid)
    assert not any(a["id"] == aid for a in articles)


def test_resubscription_shows_articles_again(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)

    slug = _global_slug(db)

    aid = _insert_article(db, source_slug=slug)

    # Unsubscribe then re-subscribe
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (?, ?, 0)",
            (uid, slug),
        )
        conn.execute(
            "UPDATE user_sources SET enabled = 1 WHERE user_id = ? AND source_slug = ?",
            (uid, slug),
        )

    articles = list_articles(state="today", db_path=db, user_id=uid)
    assert any(a["id"] == aid for a in articles)


def test_private_source_only_visible_to_owner(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid_a = _make_user(db, "alice")
    uid_b = _make_user(db, "bob")

    _add_private_source(db, slug="alices-feed", owner_user_id=uid_a)
    aid = _insert_article(db, source_slug="alices-feed", url_suffix="priv1")

    # Alice sees it
    alice_arts = list_articles(state="today", db_path=db, user_id=uid_a)
    assert any(a["id"] == aid for a in alice_arts)

    # Bob does not see it
    bob_arts = list_articles(state="today", db_path=db, user_id=uid_b)
    assert not any(a["id"] == aid for a in bob_arts)


def test_unsubscription_is_per_user(tmp_path: Path) -> None:
    """Unsubscribing from a source only affects the user who unsubscribed."""
    db = _setup_db(tmp_path)
    uid_a = _make_user(db, "alice")
    uid_b = _make_user(db, "bob")

    slug = _global_slug(db)

    aid = _insert_article(db, source_slug=slug)

    # Alice unsubscribes
    with connect(db) as conn:
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (?, ?, 0)",
            (uid_a, slug),
        )

    alice_arts = list_articles(state="today", db_path=db, user_id=uid_a)
    assert not any(a["id"] == aid for a in alice_arts)

    bob_arts = list_articles(state="today", db_path=db, user_id=uid_b)
    assert any(a["id"] == aid for a in bob_arts)


# ── API layer ─────────────────────────────────────────────────────────────────


def _api_client(db_path: Path, user_id: int, is_admin: bool = False) -> Any:
    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_admin, require_auth
    from news_dashboard.main import app

    fake = {"id": user_id, "username": "testuser", "email": None, "is_admin": is_admin}
    app.dependency_overrides[require_auth] = lambda: fake
    app.dependency_overrides[require_admin] = lambda: fake
    return TestClient(app, raise_server_exceptions=True)


def test_api_list_sources_returns_subscription_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "api.db")
    sync_sources(tmp_path / "api.db")
    uid = _make_user(tmp_path / "api.db")

    client = _api_client(tmp_path / "api.db", uid)
    try:
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) > 0
        # All global sources are subscribed by default
        assert all(i["subscribed"] for i in items)
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_api_create_private_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "api2.db")
    sync_sources(tmp_path / "api2.db")
    uid = _make_user(tmp_path / "api2.db")

    client = _api_client(tmp_path / "api2.db", uid)
    try:
        resp = client.post(
            "/api/sources",
            json={
                "url": "https://example.com/my-feed.xml",
                "name": "My Blog",
                "category": "tech",
                "slug": "my-blog",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "my-blog"
        assert data["owner_user_id"] == uid

        # Verify it appears in the source list for this user
        resp2 = client.get("/api/sources")
        slugs = [i["slug"] for i in resp2.json()["items"]]
        assert "my-blog" in slugs
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_api_private_source_not_visible_to_other_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "api3.db")
    sync_sources(tmp_path / "api3.db")
    uid_a = _make_user(tmp_path / "api3.db", "alice")
    uid_b = _make_user(tmp_path / "api3.db", "bob")

    # Alice creates a private source
    client_a = _api_client(tmp_path / "api3.db", uid_a)
    try:
        resp = client_a.post(
            "/api/sources",
            json={
                "url": "https://private.example.com/feed",
                "name": "Alice Blog",
                "slug": "alice-blog",
            },
        )
        assert resp.status_code == 200
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)

    # Bob doesn't see it
    client_b = _api_client(tmp_path / "api3.db", uid_b)
    try:
        resp2 = client_b.get("/api/sources")
        slugs = [i["slug"] for i in resp2.json()["items"]]
        assert "alice-blog" not in slugs
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_api_delete_own_private_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "api4.db")
    sync_sources(tmp_path / "api4.db")
    uid = _make_user(tmp_path / "api4.db")

    client = _api_client(tmp_path / "api4.db", uid)
    try:
        client.post(
            "/api/sources",
            json={
                "url": "https://delete.example.com/feed",
                "name": "To Delete",
                "slug": "to-delete",
            },
        )
        resp = client.delete("/api/sources/to-delete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_api_cannot_delete_others_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "api5.db")
    sync_sources(tmp_path / "api5.db")
    uid_a = _make_user(tmp_path / "api5.db", "alice")
    uid_b = _make_user(tmp_path / "api5.db", "bob")

    client_a = _api_client(tmp_path / "api5.db", uid_a)
    try:
        client_a.post(
            "/api/sources",
            json={
                "url": "https://alices.example.com/feed",
                "name": "Alice Source",
                "slug": "alice-src",
            },
        )
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)

    client_b = _api_client(tmp_path / "api5.db", uid_b)
    try:
        resp = client_b.delete("/api/sources/alice-src")
        assert resp.status_code == 403
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_api_toggle_subscription(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "api6.db")
    sync_sources(tmp_path / "api6.db")
    uid = _make_user(tmp_path / "api6.db")

    slug = _global_slug(tmp_path / "api6.db")
    client = _api_client(tmp_path / "api6.db", uid)
    try:
        # Unsubscribe
        resp = client.patch(f"/api/sources/{slug}/enabled", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["subscribed"] is False

        # Re-subscribe
        resp2 = client.patch(f"/api/sources/{slug}/enabled", json={"enabled": True})
        assert resp2.status_code == 200
        assert resp2.json()["subscribed"] is True
    finally:
        from news_dashboard.auth import require_admin, require_auth
        from news_dashboard.main import app

        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)
