"""Tests for the user-scoped /api/summary endpoint and get_user_summary().

Covers:
- get_user_summary() returns counts for the authenticated user only
- State isolation between users (alice vs bob)
- Starred count is per-user
- Category breakdown respects user scope
- Disabled sources are excluded from counts
- Articles from private sources owned by user ARE included
- Articles from private sources NOT owned by user are excluded
- /api/summary API endpoint requires authentication
- /api/summary returns data for the currently-authenticated user
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import news_dashboard.db as db_mod
from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.ingest import (
    get_user_summary,
    set_article_starred,
    sync_sources,
    transition_article_state,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    sync_sources(db)
    return db


def _make_user(db_path: Path, username: str = "alice") -> int:
    orig = db_mod.DB_PATH
    db_mod.DB_PATH = db_path
    try:
        user = create_user(username, "password123")
    finally:
        db_mod.DB_PATH = orig
    return int(user["id"])


def _insert_article(
    db_path: Path,
    *,
    url_suffix: str = "1",
    category: str = "AI/LLM",
    source_slug: str = "python-insider",
) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                f"https://example.com/art{url_suffix}",
                f"https://example.com/art{url_suffix}",
                f"Article {url_suffix}",
                source_slug,
                "Python Insider",
                category,
                "rss_feed",
                "today",
            ),
        ).fetchone()
    return int(row["id"] if isinstance(row, dict) else row[0])


def _insert_private_source(db_path: Path, *, slug: str, owner_user_id: int) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, owner_user_id, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, f"https://{slug}.example.com", "AI/LLM", "rss_feed", owner_user_id, True),
        )


# ── get_user_summary unit tests ───────────────────────────────────────────────


def test_empty_db_returns_zero_counts(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    result = get_user_summary(user_id=uid, db_path=db)
    assert result["byStatus"]["new"] == 0
    assert result["byStatus"]["saved"] == 0
    assert result["byStatus"]["read"] == 0
    assert result["byStatus"]["skipped"] == 0
    assert result["byStatus"]["archived"] == 0
    assert result["byCategory"] == {}


def test_new_article_counted_as_new(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    _insert_article(db)
    result = get_user_summary(user_id=uid, db_path=db)
    assert result["byStatus"]["new"] == 1


def test_done_article_counted_as_read(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)
    transition_article_state(aid, "done", db_path=db, user_id=uid)
    result = get_user_summary(user_id=uid, db_path=db)
    assert result["byStatus"]["read"] == 1
    assert result["byStatus"]["new"] == 0


def test_skipped_article_counted_as_skipped(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)
    transition_article_state(aid, "skipped", db_path=db, user_id=uid)
    result = get_user_summary(user_id=uid, db_path=db)
    assert result["byStatus"]["skipped"] == 1
    assert result["byStatus"]["new"] == 0


def test_starred_article_counted_as_saved(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)
    set_article_starred(aid, True, db_path=db, user_id=uid)
    result = get_user_summary(user_id=uid, db_path=db)
    assert result["byStatus"]["saved"] == 1


def test_unstarred_article_not_counted_as_saved(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)
    set_article_starred(aid, True, db_path=db, user_id=uid)
    set_article_starred(aid, False, db_path=db, user_id=uid)
    result = get_user_summary(user_id=uid, db_path=db)
    assert result["byStatus"]["saved"] == 0


def test_category_breakdown_correct(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    _insert_article(db, url_suffix="1", category="AI/LLM")
    _insert_article(db, url_suffix="2", category="AI/LLM")
    _insert_article(db, url_suffix="3", category="Python")
    result = get_user_summary(user_id=uid, db_path=db)
    assert result["byCategory"]["AI/LLM"] == 2
    assert result["byCategory"]["Python"] == 1


def test_user_isolation_state(tmp_path: Path) -> None:
    """Alice's done state must not pollute Bob's summary."""
    db = _setup_db(tmp_path)
    uid_a = _make_user(db, "alice")
    uid_b = _make_user(db, "bob")
    aid = _insert_article(db)

    transition_article_state(aid, "done", db_path=db, user_id=uid_a)

    result_a = get_user_summary(user_id=uid_a, db_path=db)
    result_b = get_user_summary(user_id=uid_b, db_path=db)

    assert result_a["byStatus"]["read"] == 1
    assert result_a["byStatus"]["new"] == 0
    assert result_b["byStatus"]["new"] == 1
    assert result_b["byStatus"]["read"] == 0


def test_user_isolation_starred(tmp_path: Path) -> None:
    """Alice starring an article must not affect Bob's saved count."""
    db = _setup_db(tmp_path)
    uid_a = _make_user(db, "alice")
    uid_b = _make_user(db, "bob")
    aid = _insert_article(db)

    set_article_starred(aid, True, db_path=db, user_id=uid_a)

    result_a = get_user_summary(user_id=uid_a, db_path=db)
    result_b = get_user_summary(user_id=uid_b, db_path=db)

    assert result_a["byStatus"]["saved"] == 1
    assert result_b["byStatus"]["saved"] == 0


def test_user_disabled_source_excludes_articles(tmp_path: Path) -> None:
    """When a user disables a public source, those articles should not count."""
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    _insert_article(db, url_suffix="1", source_slug="python-insider")

    # Disable the source for this user
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO user_sources(user_id, source_slug, enabled)
            VALUES (%s, %s, %s)
            ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = excluded.enabled
            """,
            (uid, "python-insider", False),
        )

    result = get_user_summary(user_id=uid, db_path=db)
    assert result["byStatus"]["new"] == 0


def test_private_source_owner_sees_articles(tmp_path: Path) -> None:
    """Owner of a private source sees its articles in their summary."""
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    _insert_private_source(db, slug="my-private", owner_user_id=uid)
    _insert_article(db, url_suffix="p1", source_slug="my-private")

    result = get_user_summary(user_id=uid, db_path=db)
    assert result["byStatus"]["new"] == 1


def test_private_source_non_owner_excluded(tmp_path: Path) -> None:
    """Non-owner must NOT see articles from another user's private source."""
    db = _setup_db(tmp_path)
    uid_owner = _make_user(db, "owner")
    uid_other = _make_user(db, "other")
    _insert_private_source(db, slug="private-src", owner_user_id=uid_owner)
    _insert_article(db, url_suffix="x1", source_slug="private-src")

    result = get_user_summary(user_id=uid_other, db_path=db)
    assert result["byStatus"]["new"] == 0


def test_multiple_states_counted_independently(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid1 = _insert_article(db, url_suffix="1")
    aid2 = _insert_article(db, url_suffix="2")
    aid3 = _insert_article(db, url_suffix="3")

    transition_article_state(aid2, "done", db_path=db, user_id=uid)
    transition_article_state(aid3, "skipped", db_path=db, user_id=uid)
    set_article_starred(aid1, True, db_path=db, user_id=uid)

    result = get_user_summary(user_id=uid, db_path=db)
    # aid1 is still today (starred but not transitioned)
    assert result["byStatus"]["new"] == 1
    assert result["byStatus"]["read"] == 1
    assert result["byStatus"]["skipped"] == 1
    assert result["byStatus"]["saved"] == 1


# ── /api/summary API endpoint tests ──────────────────────────────────────────


def test_api_summary_requires_auth(tmp_path: Path) -> None:
    """Without the auth override, /api/summary returns 401."""
    orig = db_mod.DB_PATH
    db_mod.DB_PATH = _setup_db(tmp_path)
    try:
        from news_dashboard.auth import require_auth
        from news_dashboard.main import app

        # Clear the autouse override
        app.dependency_overrides.pop(require_auth, None)
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.get("/api/summary")
            assert resp.status_code == 401
        finally:
            # Restore for other tests (conftest autouse will re-inject after this test)
            pass
    finally:
        db_mod.DB_PATH = orig


def test_api_summary_returns_by_status_and_category(tmp_path: Path) -> None:
    """Authenticated call returns the expected shape with byStatus and byCategory."""
    db = _setup_db(tmp_path)
    orig = db_mod.DB_PATH
    db_mod.DB_PATH = db
    try:
        uid = _make_user(db, "apitestuser")
        _insert_article(db, url_suffix="a1")

        from news_dashboard.auth import require_auth
        from news_dashboard.main import app

        fake_user = {"id": uid, "username": "apitestuser", "is_admin": False}
        app.dependency_overrides[require_auth] = lambda: fake_user
        client = TestClient(app)
        try:
            resp = client.get("/api/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert "byStatus" in data
            assert "byCategory" in data
            assert data["byStatus"]["new"] == 1
        finally:
            app.dependency_overrides.pop(require_auth, None)
    finally:
        db_mod.DB_PATH = orig


def test_api_summary_isolates_users(tmp_path: Path) -> None:
    """Two users hitting /api/summary each see only their own counts."""
    db = _setup_db(tmp_path)
    orig = db_mod.DB_PATH
    db_mod.DB_PATH = db
    try:
        uid_a = _make_user(db, "user_a")
        uid_b = _make_user(db, "user_b")
        aid = _insert_article(db)

        # User A marks article as done
        transition_article_state(aid, "done", db_path=db, user_id=uid_a)

        from news_dashboard.auth import require_auth
        from news_dashboard.main import app

        # Check as user A
        app.dependency_overrides[require_auth] = lambda: {
            "id": uid_a,
            "username": "user_a",
            "is_admin": False,
        }
        client = TestClient(app)
        resp_a = client.get("/api/summary")
        data_a = resp_a.json()

        # Check as user B
        app.dependency_overrides[require_auth] = lambda: {
            "id": uid_b,
            "username": "user_b",
            "is_admin": False,
        }
        resp_b = client.get("/api/summary")
        data_b = resp_b.json()

        app.dependency_overrides.pop(require_auth, None)

        assert data_a["byStatus"]["read"] == 1
        assert data_a["byStatus"]["new"] == 0
        assert data_b["byStatus"]["new"] == 1
        assert data_b["byStatus"]["read"] == 0
    finally:
        db_mod.DB_PATH = orig
