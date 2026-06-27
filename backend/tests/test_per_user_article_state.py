"""Tests for #127 per-user article state via user_article_state table."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.ingest import (
    list_articles,
    search_articles,
    send_article_later,
    set_article_starred,
    sync_sources,
    transition_article_state,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _setup_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    sync_sources(db)
    return db


def _insert_article(db_path: Path | str, *, url_suffix: str = "1", state: str = "today") -> int:
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
                "python-insider",
                "Python Insider",
                "python",
                "rss_feed",
                state,
            ),
        ).fetchone()
    return int(row["id"] if isinstance(row, dict) else row[0])


def _make_user(db_path: Path | str, username: str = "alice") -> int:
    user = create_user(username, "password123", db_path=db_path)
    return int(user["id"])


# ── implicit today (no UAS row yet) ──────────────────────────────────────────


def test_no_uas_row_is_implicitly_today(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    _insert_article(db)
    articles = list_articles(state="today", db_path=db, user_id=uid)
    assert len(articles) == 1
    assert articles[0]["state"] == "today"
    assert articles[0]["starred"] is False


def test_no_uas_row_not_returned_for_done_filter(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    _insert_article(db)
    articles = list_articles(state="done", db_path=db, user_id=uid)
    assert len(articles) == 0


# ── per-user state isolation ──────────────────────────────────────────────────


def test_state_is_per_user(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid_a = _make_user(db, "alice")
    uid_b = _make_user(db, "bob")
    aid = _insert_article(db)

    transition_article_state(aid, "done", db_path=db, user_id=uid_a)

    # alice sees it as done
    a_arts = list_articles(state="done", db_path=db, user_id=uid_a)
    assert any(a["id"] == aid for a in a_arts)

    # bob still sees it as today
    b_arts = list_articles(state="today", db_path=db, user_id=uid_b)
    assert any(a["id"] == aid for a in b_arts)

    # bob doesn't see it in done
    b_done = list_articles(state="done", db_path=db, user_id=uid_b)
    assert not any(a["id"] == aid for a in b_done)


def test_star_is_per_user(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid_a = _make_user(db, "alice")
    uid_b = _make_user(db, "bob")
    aid = _insert_article(db)

    set_article_starred(aid, True, db_path=db, user_id=uid_a)

    a_starred = list_articles(starred=True, db_path=db, user_id=uid_a)
    assert any(a["id"] == aid for a in a_starred)

    b_starred = list_articles(starred=True, db_path=db, user_id=uid_b)
    assert not any(a["id"] == aid for a in b_starred)


# ── transition_article_state with user_id ─────────────────────────────────────


def test_today_to_done_with_user(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    result = transition_article_state(aid, "done", db_path=db, user_id=uid)
    assert result is not None
    assert result["state"] == "done"
    assert result["done_at"] is not None


def test_today_to_skipped_with_user(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    result = transition_article_state(aid, "skipped", db_path=db, user_id=uid)
    assert result is not None
    assert result["state"] == "skipped"
    assert result["skipped_at"] is not None


def test_skipped_to_today_restores(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    transition_article_state(aid, "skipped", db_path=db, user_id=uid)
    result = transition_article_state(aid, "today", db_path=db, user_id=uid)
    assert result is not None
    assert result["state"] == "today"
    assert result["restored_at"] is not None


def test_invalid_transition_raises(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    transition_article_state(aid, "done", db_path=db, user_id=uid)
    with pytest.raises(ValueError, match="not allowed"):
        transition_article_state(aid, "skipped", db_path=db, user_id=uid)


def test_starred_cannot_be_skipped(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    set_article_starred(aid, True, db_path=db, user_id=uid)
    with pytest.raises(ValueError, match="starred"):
        transition_article_state(aid, "skipped", db_path=db, user_id=uid)


# ── set_article_starred with user_id ─────────────────────────────────────────


def test_star_then_unstar(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    result = set_article_starred(aid, True, db_path=db, user_id=uid)
    assert result is not None
    assert result["starred"] is True
    assert result["starred_at"] is not None

    result = set_article_starred(aid, False, db_path=db, user_id=uid)
    assert result is not None
    assert result["starred"] is False


# ── send_article_later with user_id ──────────────────────────────────────────


def test_snooze_with_user(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    result = send_article_later(aid, days=3, db_path=db, user_id=uid)
    assert result is not None
    assert result["state"] == "later"
    assert result["later_until"] is not None
    later_until = result["later_until"]
    until = datetime.fromisoformat(later_until) if isinstance(later_until, str) else later_until
    delta = until - datetime.now(timezone.utc)
    assert 2 < delta.total_seconds() / 3600 < 75  # ~3 days


def test_snooze_cannot_snooze_done(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    transition_article_state(aid, "done", db_path=db, user_id=uid)
    with pytest.raises(ValueError, match="cannot snooze"):
        send_article_later(aid, days=1, db_path=db, user_id=uid)


def test_snooze_returns_to_today_after_expiry(tmp_path: Path) -> None:
    """An article snoozed with later_until in the past appears in the today filter."""
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    # Put the article in "later" state for this user
    send_article_later(aid, days=1, db_path=db, user_id=uid)

    # Manually backdate later_until to simulate expiry
    expired_ts = "2020-01-01T00:00:00+00:00"
    with connect(db) as conn:
        conn.execute(
            "UPDATE user_article_state SET later_until = %s WHERE article_id = %s AND user_id = %s",
            (expired_ts, aid, uid),
        )

    today_arts = list_articles(state="today", db_path=db, user_id=uid)
    assert any(a["id"] == aid for a in today_arts)


def test_snooze_leaves_later_view_after_expiry(tmp_path: Path) -> None:
    """An expired snooze returns to today and no longer shows in the later view."""
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db)

    send_article_later(aid, days=1, db_path=db, user_id=uid)

    # Still pending: visible in later, not yet in today.
    assert any(a["id"] == aid for a in list_articles(state="later", db_path=db, user_id=uid))
    assert not any(a["id"] == aid for a in list_articles(state="today", db_path=db, user_id=uid))

    # Backdate later_until to simulate the snooze expiring.
    expired_ts = "2020-01-01T00:00:00+00:00"
    with connect(db) as conn:
        conn.execute(
            "UPDATE user_article_state SET later_until = %s WHERE article_id = %s AND user_id = %s",
            (expired_ts, aid, uid),
        )

    # Returned: in today, gone from later.
    assert any(a["id"] == aid for a in list_articles(state="today", db_path=db, user_id=uid))
    assert not any(a["id"] == aid for a in list_articles(state="later", db_path=db, user_id=uid))


# ── search_articles with user_id ──────────────────────────────────────────────


def test_search_with_user_id(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db, url_suffix="search1")

    # Mark as done for this user
    transition_article_state(aid, "done", db_path=db, user_id=uid)

    done_results = search_articles(states=["done"], db_path=db, user_id=uid)
    assert any(a["id"] == aid for a in done_results)
    assert all(a["state"] == "done" for a in done_results if a["id"] == aid)


def test_search_excludes_archived_by_default(tmp_path: Path) -> None:
    db = _setup_db(tmp_path)
    uid = _make_user(db)
    aid = _insert_article(db, url_suffix="arch1")

    transition_article_state(aid, "archived", db_path=db, user_id=uid)

    results = search_articles(db_path=db, user_id=uid)
    assert not any(a["id"] == aid for a in results)


# ── API layer integration ──────────────────────────────────────────────────────


def test_api_articles_uses_user_state(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/articles returns per-user state for the authenticated user."""
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    # Create a real user in our test DB
    uid = _make_user(pg_clean, "testuser")
    aid = _insert_article(pg_clean, url_suffix="api1")

    fake_user = {"id": uid, "username": "testuser", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/api/articles", params={"state": "today"})
            assert resp.status_code == 200
            ids = [a["id"] for a in resp.json()["items"]]
            assert aid in ids
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_api_state_transition_writes_uas(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """PATCH /api/articles/{id}/state writes to user_article_state."""
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    uid = _make_user(pg_clean, "testuser2")
    aid = _insert_article(pg_clean, url_suffix="api2")

    fake_user = {"id": uid, "username": "testuser2", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.patch(f"/api/articles/{aid}/state", json={"state": "done"})
            assert resp.status_code == 200
            assert resp.json()["state"] == "done"

        # Confirm UAS row was written, article table state unchanged
        with connect(pg_clean) as conn:
            uas = conn.execute(
                "SELECT * FROM user_article_state WHERE article_id = %s AND user_id = %s",
                (aid, uid),
            ).fetchone()
            assert uas is not None
            from news_dashboard.db import row_to_dict

            uas_d = row_to_dict(uas)
            assert uas_d["state"] == "done"

            art = conn.execute("SELECT state FROM articles WHERE id = %s", (aid,)).fetchone()
            art_d = row_to_dict(art)
            assert art_d["state"] == "today"  # article table untouched
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_legacy_status_endpoint_updates_only_current_user_state(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PATCH /api/articles/{id}/status maps legacy read to caller-scoped state."""
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    uid_a = _make_user(pg_clean, "legacy_status_alice")
    uid_b = _make_user(pg_clean, "legacy_status_bob")
    aid = _insert_article(pg_clean, url_suffix="legacy-status")

    fake_user = {
        "id": uid_a,
        "username": "legacy_status_alice",
        "email": None,
        "is_admin": False,
    }
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.patch(f"/api/articles/{aid}/status", json={"status": "read"})
            assert resp.status_code == 200
            assert resp.json()["state"] == "done"

        alice_done = list_articles(state="done", db_path=pg_clean, user_id=uid_a)
        bob_today = list_articles(state="today", db_path=pg_clean, user_id=uid_b)
        bob_done = list_articles(state="done", db_path=pg_clean, user_id=uid_b)

        assert any(article["id"] == aid for article in alice_done)
        assert any(article["id"] == aid for article in bob_today)
        assert not any(article["id"] == aid for article in bob_done)

        with connect(pg_clean) as conn:
            art = conn.execute("SELECT state FROM articles WHERE id = %s", (aid,)).fetchone()
            assert art is not None
            assert art["state"] == "today"
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_legacy_saved_status_stars_only_current_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PATCH /api/articles/{id}/status maps legacy saved to caller-scoped star."""
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    uid_a = _make_user(pg_clean, "legacy_saved_alice")
    uid_b = _make_user(pg_clean, "legacy_saved_bob")
    aid = _insert_article(pg_clean, url_suffix="legacy-saved")

    fake_user = {
        "id": uid_a,
        "username": "legacy_saved_alice",
        "email": None,
        "is_admin": False,
    }
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.patch(f"/api/articles/{aid}/status", json={"status": "saved"})
            assert resp.status_code == 200
            assert resp.json()["state"] == "today"
            assert resp.json()["starred"] is True

        alice_starred = list_articles(starred=True, db_path=pg_clean, user_id=uid_a)
        bob_starred = list_articles(starred=True, db_path=pg_clean, user_id=uid_b)

        assert any(article["id"] == aid for article in alice_starred)
        assert not any(article["id"] == aid for article in bob_starred)

        with connect(pg_clean) as conn:
            art = conn.execute(
                "SELECT state, saved_at FROM articles WHERE id = %s", (aid,)
            ).fetchone()
            assert art is not None
            assert art["state"] == "today"
            assert art["saved_at"] is None
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_api_articles_includes_recommendation_score(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/articles?state=today includes recommendation_score when ranked."""
    db = pg_clean
    monkeypatch.setenv("DATABASE_URL", str(db))
    sync_sources(db)

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app
    from news_dashboard.recommendations import upsert_recommendation_score

    uid = _make_user(db, "rec_score_user")
    aid = _insert_article(db, url_suffix="rec-score1")

    upsert_recommendation_score(uid, aid, 87.5, db_path=db)

    fake_user = {"id": uid, "username": "rec_score_user", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/api/articles", params={"state": "today"})
            assert resp.status_code == 200
            items = resp.json()["items"]
            article = next((a for a in items if a["id"] == aid), None)
            assert article is not None
            assert article["recommendation_score"] == pytest.approx(87.5)
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_api_articles_recommendation_score_falls_back_to_cold_start_when_unranked(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/articles?state=today exposes the cold-start score for unranked articles.

    The feed already *ranks* unranked articles by their cold-start score, so it
    surfaces that same score (not ``null``) and labels the model cold-start —
    otherwise high-churn sources whose fresh items outpace the recompute sweep
    would show no recommendation insight at all.
    """
    db = pg_clean
    monkeypatch.setenv("DATABASE_URL", str(db))
    sync_sources(db)

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    uid = _make_user(db, "rec_null_user")
    aid = _insert_article(db, url_suffix="rec-null1")

    fake_user = {"id": uid, "username": "rec_null_user", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/api/articles", params={"state": "today"})
            assert resp.status_code == 200
            items = resp.json()["items"]
            article = next((a for a in items if a["id"] == aid), None)
            assert article is not None
            assert article["recommendation_score"] is not None
            assert article["recommendation_score"] > 0
            assert article["recommendation_model"] == "cold-start-v1"
    finally:
        app.dependency_overrides.pop(require_auth, None)
