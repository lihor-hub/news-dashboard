"""Tests for #128 — per-user source subscriptions and custom private sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import create_user
from news_dashboard.db import connect, row_to_dict
from news_dashboard.ingest import list_articles, sync_sources

# ── helpers ───────────────────────────────────────────────────────────────────


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    sync_sources(db)
    return db


def _make_user(db_path: Path | str, username: str = "alice") -> int:
    user = create_user(username, "pw", db_path=db_path)
    return int(user["id"])


def _insert_article(db_path: Path | str, *, source_slug: str, url_suffix: str = "1") -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug, source_name,
              category, kind, state)
            VALUES (%s, %s, %s, %s, %s, 'tech', 'rss_feed', 'today')
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


def _global_slug(db_path: Path | str) -> str:
    """Return the slug of an arbitrary global source."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT slug FROM sources WHERE owner_user_id IS NULL LIMIT 1"
        ).fetchone()
        return str(row_to_dict(row)["slug"])


def _add_private_source(db_path: Path | str, *, slug: str, owner_user_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
            VALUES (%s, %s, 'https://example.com/feed', 'tech', 'rss_feed', 0, TRUE, %s)
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
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (%s, %s, FALSE)",
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
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (%s, %s, FALSE)",
            (uid, slug),
        )
        conn.execute(
            "UPDATE user_sources SET enabled = TRUE WHERE user_id = %s AND source_slug = %s",
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
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (%s, %s, FALSE)",
            (uid_a, slug),
        )

    alice_arts = list_articles(state="today", db_path=db, user_id=uid_a)
    assert not any(a["id"] == aid for a in alice_arts)

    bob_arts = list_articles(state="today", db_path=db, user_id=uid_b)
    assert any(a["id"] == aid for a in bob_arts)


# ── API layer ─────────────────────────────────────────────────────────────────


def _api_client(db_path: Path | str, user_id: int, is_admin: bool = False) -> Any:
    from collections.abc import Generator
    from contextlib import contextmanager

    from news_dashboard.auth import require_admin, require_auth
    from news_dashboard.main import app

    fake = {"id": user_id, "username": "testuser", "email": None, "is_admin": is_admin}

    @contextmanager
    def _ctx() -> Generator[TestClient]:
        app.dependency_overrides[require_auth] = lambda: fake
        app.dependency_overrides[require_admin] = lambda: fake
        try:
            with TestClient(app, raise_server_exceptions=True) as c:
                yield c
        finally:
            app.dependency_overrides.pop(require_auth, None)
            app.dependency_overrides.pop(require_admin, None)

    return _ctx()


def test_api_list_sources_returns_subscription_status(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) > 0
        # All global sources are subscribed by default
        assert all(i["subscribed"] for i in items)


def test_api_create_private_source(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
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


def test_api_private_source_not_visible_to_other_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid_a = _make_user(pg_clean, "alice")
    uid_b = _make_user(pg_clean, "bob")

    # Alice creates a private source
    with _api_client(pg_clean, uid_a) as client_a:
        resp = client_a.post(
            "/api/sources",
            json={
                "url": "https://private.example.com/feed",
                "name": "Alice Blog",
                "slug": "alice-blog",
            },
        )
        assert resp.status_code == 200

    # Bob doesn't see it
    with _api_client(pg_clean, uid_b) as client_b:
        resp2 = client_b.get("/api/sources")
        slugs = [i["slug"] for i in resp2.json()["items"]]
        assert "alice-blog" not in slugs


def test_api_delete_own_private_source(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
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


def test_api_cannot_delete_others_source(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid_a = _make_user(pg_clean, "alice")
    uid_b = _make_user(pg_clean, "bob")

    with _api_client(pg_clean, uid_a) as client_a:
        client_a.post(
            "/api/sources",
            json={
                "url": "https://alices.example.com/feed",
                "name": "Alice Source",
                "slug": "alice-src",
            },
        )

    with _api_client(pg_clean, uid_b) as client_b:
        resp = client_b.delete("/api/sources/alice-src")
        assert resp.status_code == 403


def test_api_toggle_subscription(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    slug = _global_slug(pg_clean)
    with _api_client(pg_clean, uid) as client:
        # Unsubscribe
        resp = client.patch(f"/api/sources/{slug}/enabled", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["subscribed"] is False

        # Re-subscribe
        resp2 = client.patch(f"/api/sources/{slug}/enabled", json={"enabled": True})
        assert resp2.status_code == 200
        assert resp2.json()["subscribed"] is True


# ── Validation ────────────────────────────────────────────────────────────────


def test_api_create_source_rejects_invalid_url_scheme(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
        for bad_url in ("ftp://example.com/feed", "file:///etc/passwd", "javascript:alert(1)"):
            resp = client.post("/api/sources", json={"url": bad_url, "name": "Bad"})
            assert resp.status_code == 400, f"expected 400 for {bad_url!r}"
            assert "http" in resp.json()["detail"].lower()


def test_api_create_source_rejects_missing_host(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
        resp = client.post("/api/sources", json={"url": "https://", "name": "Bad Host"})
        assert resp.status_code == 400


def test_api_create_source_rejects_empty_name(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
        resp = client.post("/api/sources", json={"url": "https://example.com/feed", "name": "   "})
        assert resp.status_code == 400


def test_api_create_source_rejects_bad_slug(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
        resp = client.post(
            "/api/sources",
            json={"url": "https://example.com/feed", "name": "My Blog", "slug": "BAD_SLUG!"},
        )
        assert resp.status_code == 400


def test_api_create_source_duplicate_slug_returns_409(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
        payload = {"url": "https://example.com/feed", "name": "My Blog", "slug": "my-blog"}
        resp1 = client.post("/api/sources", json=payload)
        assert resp1.status_code == 200
        resp2 = client.post("/api/sources", json=payload)
        assert resp2.status_code == 409
        assert "already exists" in resp2.json()["detail"]


def test_api_create_source_auto_generates_slug(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)
    uid = _make_user(pg_clean)

    with _api_client(pg_clean, uid) as client:
        resp = client.post(
            "/api/sources",
            json={"url": "https://example.com/feed", "name": "Hello World Blog"},
        )
        assert resp.status_code == 200
        slug = resp.json()["slug"]
        assert slug
        assert slug == slug.lower()
        assert " " not in slug
