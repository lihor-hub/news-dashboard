"""PostgreSQL-specific type-compatibility tests.

These tests run against a real PostgreSQL instance (via testcontainers) and
guard against the class of bug where SQLite happily accepts integer 0/1 for
boolean columns but PostgreSQL raises DatatypeMismatch.

Covered scenarios
-----------------
- COALESCE(uas.starred, false)     — list_articles starred filter
- COALESCE(us_src.enabled, true)   — source subscription filter in list_articles
- COALESCE(us.enabled, true)       — sources listing CASE expression in main.py
- Writing user_sources.enabled as a Python bool (not 0/1) via PATCH API
- State isolation between users on PostgreSQL
- Private source visibility on PostgreSQL
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

import pytest

pytestmark = pytest.mark.postgres


# ── fixture: set DATABASE_URL for the duration of each test ──────────────────


@pytest.fixture
def pg_env(pg_clean: str) -> Generator[str]:
    """Set DATABASE_URL in the environment and restore it after the test."""
    orig = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_clean
    try:
        yield pg_clean
    finally:
        if orig is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = orig


# ── DB helpers ────────────────────────────────────────────────────────────────


def _make_user(pg_url: str, username: str) -> int:
    import psycopg

    with psycopg.connect(pg_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "x"),
        ).fetchone()
        conn.commit()
    assert row is not None
    return int(row[0])


def _add_global_source(pg_url: str, slug: str) -> None:
    import psycopg

    with psycopg.connect(pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, 'https://example.com/feed', 'tech', 'rss_feed', 50, TRUE)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug),
        )
        conn.commit()


def _add_private_source(pg_url: str, slug: str, *, owner_user_id: int) -> None:
    import psycopg

    with psycopg.connect(pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
            VALUES (%s, %s, 'https://example.com/feed', 'tech', 'rss_feed', 50, TRUE, %s)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, owner_user_id),
        )
        conn.commit()


def _add_article(pg_url: str, *, source_slug: str, url_suffix: str = "1") -> int:
    import psycopg

    with psycopg.connect(pg_url) as conn:
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
        conn.commit()
    assert row is not None
    return int(row[0])


def _api_client(uid: int, username: str = "user") -> Any:
    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_admin, require_auth
    from news_dashboard.main import app

    fake = {"id": uid, "username": username, "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake
    app.dependency_overrides[require_admin] = lambda: fake
    return TestClient(app, raise_server_exceptions=True)


def _clear_auth_overrides() -> None:
    from news_dashboard.auth import require_admin, require_auth
    from news_dashboard.main import app

    app.dependency_overrides.pop(require_auth, None)
    app.dependency_overrides.pop(require_admin, None)


# ── starred BOOLEAN column ────────────────────────────────────────────────────


def test_pg_list_articles_starred_filter(pg_env: str) -> None:
    """COALESCE(uas.starred, false) must not raise DatatypeMismatch on PostgreSQL."""
    from news_dashboard.ingest import list_articles, set_article_starred

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-star")
    uid = _make_user(pg_url, "star-user")
    aid = _add_article(pg_url, source_slug="pg-src-star", url_suffix="star1")

    # No UAS row yet — starred filter should return empty without crashing.
    results = list_articles(starred=True, user_id=uid)
    assert not any(a["id"] == aid for a in results)

    # Star the article and verify it appears.
    set_article_starred(aid, True, user_id=uid)
    results = list_articles(starred=True, user_id=uid)
    assert any(a["id"] == aid for a in results)
    assert all(a["starred"] is True for a in results if a["id"] == aid)


def test_pg_list_articles_unstarred_filter(pg_env: str) -> None:
    """Starred=False filter must correctly exclude starred articles on PostgreSQL."""
    from news_dashboard.ingest import list_articles, set_article_starred

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-unstar")
    uid = _make_user(pg_url, "unstar-user")
    aid_a = _add_article(pg_url, source_slug="pg-src-unstar", url_suffix="unstar1")
    aid_b = _add_article(pg_url, source_slug="pg-src-unstar", url_suffix="unstar2")

    set_article_starred(aid_a, True, user_id=uid)

    starred = list_articles(starred=True, user_id=uid)
    unstarred = list_articles(starred=False, user_id=uid)

    assert any(a["id"] == aid_a for a in starred)
    assert not any(a["id"] == aid_a for a in unstarred)
    assert not any(a["id"] == aid_b for a in starred)
    assert any(a["id"] == aid_b for a in unstarred)


def test_pg_list_articles_exposes_recommendation_metadata(pg_env: str) -> None:
    """list_articles must surface recommendation_score/model for compact Today labels."""
    from news_dashboard.ingest import list_articles
    from news_dashboard.recommendations import upsert_recommendation_score

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-rec")
    uid = _make_user(pg_url, "rec-user")
    aid_scored = _add_article(pg_url, source_slug="pg-src-rec", url_suffix="rec-scored")
    aid_unscored = _add_article(pg_url, source_slug="pg-src-rec", url_suffix="rec-unscored")

    upsert_recommendation_score(
        uid,
        aid_scored,
        82.5,
        model_version="semantic-hybrid-v1",
        signals={
            "affinity_adjustment": 8.0,
            "semantic_adjustment": 12.0,
            "freshness_adjustment": 3.0,
            "novelty_adjustment": 0.0,
            "source_slug": "pg-src-rec",
        },
    )

    results = list_articles(state="today", user_id=uid)
    by_id = {a["id"]: a for a in results}

    scored = by_id[aid_scored]
    assert scored["recommendation_score"] == pytest.approx(82.5)
    assert scored["recommendation_model"] == "semantic-hybrid-v1"
    # The per-factor signal breakdown powers on-demand explanations (#225).
    assert scored["recommendation_signals"]["semantic_adjustment"] == pytest.approx(12.0)
    assert scored["recommendation_signals"]["affinity_adjustment"] == pytest.approx(8.0)

    # Articles without recommendation metadata degrade gracefully to None.
    unscored = by_id[aid_unscored]
    assert unscored["recommendation_score"] is None
    assert unscored["recommendation_model"] is None
    assert unscored["recommendation_signals"] is None


def test_pg_list_articles_today_without_uas(pg_env: str) -> None:
    """list_articles state=today must work when no UAS row exists (NULL coalesces to false)."""
    from news_dashboard.ingest import list_articles

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-today")
    uid = _make_user(pg_url, "today-user")
    aid = _add_article(pg_url, source_slug="pg-src-today", url_suffix="today1")

    results = list_articles(state="today", user_id=uid)
    assert any(a["id"] == aid for a in results)
    match = next(a for a in results if a["id"] == aid)
    assert match["starred"] is False
    assert match["state"] == "today"


def test_pg_star_then_unstar(pg_env: str) -> None:
    """set_article_starred round-trip on PostgreSQL boolean column."""
    from news_dashboard.ingest import list_articles, set_article_starred

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-roundtrip")
    uid = _make_user(pg_url, "roundtrip-user")
    aid = _add_article(pg_url, source_slug="pg-src-roundtrip", url_suffix="rt1")

    result = set_article_starred(aid, True, user_id=uid)
    assert result is not None
    assert result["starred"] is True

    result = set_article_starred(aid, False, user_id=uid)
    assert result is not None
    assert result["starred"] is False

    # Confirm list also shows correct value.
    today = list_articles(state="today", user_id=uid)
    match = next((a for a in today if a["id"] == aid), None)
    assert match is not None
    assert match["starred"] is False


# ── user_sources.enabled BOOLEAN column ──────────────────────────────────────


def test_pg_list_articles_respects_source_subscription(pg_env: str) -> None:
    """COALESCE(us_src.enabled, true) must not raise DatatypeMismatch on PostgreSQL."""
    import psycopg

    from news_dashboard.ingest import list_articles

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-sub")
    uid = _make_user(pg_url, "sub-user")
    aid = _add_article(pg_url, source_slug="pg-src-sub", url_suffix="sub1")

    # Default: no user_sources row → source is visible.
    results = list_articles(state="today", user_id=uid)
    assert any(a["id"] == aid for a in results)

    # Unsubscribe using a Python bool (not 0/1).
    with psycopg.connect(pg_url) as conn:
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (%s, %s, %s)",
            (uid, "pg-src-sub", False),
        )
        conn.commit()

    results = list_articles(state="today", user_id=uid)
    assert not any(a["id"] == aid for a in results)


def test_pg_list_articles_resubscription(pg_env: str) -> None:
    """Flipping user_sources.enabled back to true restores article visibility."""
    import psycopg

    from news_dashboard.ingest import list_articles

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-resub")
    uid = _make_user(pg_url, "resub-user")
    aid = _add_article(pg_url, source_slug="pg-src-resub", url_suffix="resub1")

    with psycopg.connect(pg_url) as conn:
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (%s, %s, %s)",
            (uid, "pg-src-resub", False),
        )
        conn.commit()

    assert not any(a["id"] == aid for a in list_articles(state="today", user_id=uid))

    with psycopg.connect(pg_url) as conn:
        conn.execute(
            "UPDATE user_sources SET enabled = %s WHERE user_id = %s AND source_slug = %s",
            (True, uid, "pg-src-resub"),
        )
        conn.commit()

    results = list_articles(state="today", user_id=uid)
    assert any(a["id"] == aid for a in results)


# ── GET /api/sources CASE WHEN COALESCE expression ───────────────────────────


def test_pg_sources_listing_subscribed_by_default(pg_env: str) -> None:
    """GET /api/sources COALESCE(us.enabled, true) must not raise DatatypeMismatch."""
    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-list")
    uid = _make_user(pg_url, "list-user")

    client = _api_client(uid, "list-user")
    try:
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        items = resp.json()["items"]
        match = next((i for i in items if i["slug"] == "pg-src-list"), None)
        assert match is not None
        assert match["subscribed"] is True
    finally:
        _clear_auth_overrides()


def test_pg_sources_listing_after_unsubscribe(pg_env: str) -> None:
    """After unsubscribing, GET /api/sources must show subscribed=false."""
    import psycopg

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-unsub-list")
    uid = _make_user(pg_url, "unsub-list-user")

    with psycopg.connect(pg_url) as conn:
        conn.execute(
            "INSERT INTO user_sources(user_id, source_slug, enabled) VALUES (%s, %s, %s)",
            (uid, "pg-src-unsub-list", False),
        )
        conn.commit()

    client = _api_client(uid, "unsub-list-user")
    try:
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        match = next((i for i in resp.json()["items"] if i["slug"] == "pg-src-unsub-list"), None)
        assert match is not None
        assert match["subscribed"] is False
    finally:
        _clear_auth_overrides()


# ── PATCH /api/sources/{slug}/enabled writes boolean ─────────────────────────


def test_pg_api_toggle_subscription_writes_boolean(pg_env: str) -> None:
    """PATCH /api/sources/{slug}/enabled must write a Python bool to user_sources.enabled."""
    import psycopg

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-toggle")
    uid = _make_user(pg_url, "toggle-user")

    client = _api_client(uid, "toggle-user")
    try:
        resp = client.patch("/api/sources/pg-src-toggle/enabled", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["subscribed"] is False

        resp2 = client.patch("/api/sources/pg-src-toggle/enabled", json={"enabled": True})
        assert resp2.status_code == 200
        assert resp2.json()["subscribed"] is True
    finally:
        _clear_auth_overrides()

    # Confirm the DB column holds a proper boolean, not an integer.
    with psycopg.connect(pg_url) as conn:
        row = conn.execute(
            "SELECT enabled FROM user_sources WHERE user_id = %s AND source_slug = %s",
            (uid, "pg-src-toggle"),
        ).fetchone()
    assert row is not None
    assert row[0] is True


# ── per-user state isolation ──────────────────────────────────────────────────


def test_pg_state_isolation_between_users(pg_env: str) -> None:
    """State transitions on PostgreSQL must be isolated per user."""
    from news_dashboard.ingest import list_articles, transition_article_state

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-iso")
    uid_a = _make_user(pg_url, "iso-alice")
    uid_b = _make_user(pg_url, "iso-bob")
    aid = _add_article(pg_url, source_slug="pg-src-iso", url_suffix="iso1")

    transition_article_state(aid, "done", user_id=uid_a)

    assert any(a["id"] == aid for a in list_articles(state="done", user_id=uid_a))
    assert any(a["id"] == aid for a in list_articles(state="today", user_id=uid_b))
    assert not any(a["id"] == aid for a in list_articles(state="done", user_id=uid_b))


def test_pg_star_isolation_between_users(pg_env: str) -> None:
    """Starring an article for one user must not affect another user's view."""
    from news_dashboard.ingest import list_articles, set_article_starred

    pg_url = pg_env
    _add_global_source(pg_url, "pg-src-star-iso")
    uid_a = _make_user(pg_url, "stariso-alice")
    uid_b = _make_user(pg_url, "stariso-bob")
    aid = _add_article(pg_url, source_slug="pg-src-star-iso", url_suffix="stariso1")

    set_article_starred(aid, True, user_id=uid_a)

    assert any(a["id"] == aid for a in list_articles(starred=True, user_id=uid_a))
    assert not any(a["id"] == aid for a in list_articles(starred=True, user_id=uid_b))


# ── private source visibility ─────────────────────────────────────────────────


def test_pg_private_source_visibility(pg_env: str) -> None:
    """Private source articles must only be visible to the owner on PostgreSQL."""
    from news_dashboard.ingest import list_articles

    pg_url = pg_env
    uid_a = _make_user(pg_url, "priv-alice")
    uid_b = _make_user(pg_url, "priv-bob")
    _add_private_source(pg_url, "pg-priv-src", owner_user_id=uid_a)
    aid = _add_article(pg_url, source_slug="pg-priv-src", url_suffix="priv1")

    assert any(a["id"] == aid for a in list_articles(state="today", user_id=uid_a))
    assert not any(a["id"] == aid for a in list_articles(state="today", user_id=uid_b))


# ── schema correctness ────────────────────────────────────────────────────────


def test_pg_user_article_state_starred_is_boolean(pg_clean: str) -> None:
    """user_article_state.starred must be a boolean column in PostgreSQL."""
    import psycopg

    with psycopg.connect(pg_clean) as conn:
        row = conn.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'user_article_state' AND column_name = 'starred'
            """,
        ).fetchone()
    assert row is not None
    assert row[0] == "boolean"


def test_pg_user_sources_enabled_is_boolean(pg_clean: str) -> None:
    """user_sources.enabled must be a boolean column in PostgreSQL."""
    import psycopg

    with psycopg.connect(pg_clean) as conn:
        row = conn.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'user_sources' AND column_name = 'enabled'
            """,
        ).fetchone()
    assert row is not None
    assert row[0] == "boolean"


def test_pg_articles_starred_is_boolean(pg_clean: str) -> None:
    """articles.starred must be a boolean column in PostgreSQL."""
    import psycopg

    with psycopg.connect(pg_clean) as conn:
        row = conn.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'articles' AND column_name = 'starred'
            """,
        ).fetchone()
    assert row is not None
    assert row[0] == "boolean"


def test_pg_init_db_converts_legacy_integer_booleans(pg_url: str, tmp_path: Any) -> None:
    """init_db must repair legacy integer 0/1 boolean columns before runtime SQL uses TRUE."""
    import psycopg
    from psycopg import sql

    from news_dashboard.db import _schema_name, init_db

    schema = _schema_name(tmp_path / "legacy-integer-booleans")
    with psycopg.connect(pg_url) as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        conn.execute(
            """
            CREATE TABLE sources (
              slug TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              url TEXT NOT NULL,
              category TEXT NOT NULL,
              kind TEXT NOT NULL,
              priority INTEGER NOT NULL DEFAULT 50,
              enabled INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE articles (
              id BIGSERIAL PRIMARY KEY,
              url TEXT NOT NULL UNIQUE,
              canonical_url TEXT NOT NULL,
              title TEXT NOT NULL,
              source_slug TEXT NOT NULL REFERENCES sources(slug),
              source_name TEXT NOT NULL,
              category TEXT NOT NULL,
              kind TEXT NOT NULL,
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
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              starred INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE users (
              id SERIAL PRIMARY KEY,
              username TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE user_sources (
              user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
              source_slug TEXT NOT NULL REFERENCES sources(slug) ON DELETE CASCADE,
              enabled INTEGER NOT NULL DEFAULT 1,
              PRIMARY KEY (user_id, source_slug)
            )
            """
        )
        conn.commit()

    init_db(tmp_path / "legacy-integer-booleans", database_url=pg_url)

    with psycopg.connect(pg_url) as conn:
        conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        rows = conn.execute(
            """
            SELECT table_name, column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND (table_name, column_name) IN (
                ('sources', 'enabled'),
                ('articles', 'starred'),
                ('user_sources', 'enabled')
              )
            ORDER BY table_name, column_name
            """
        ).fetchall()
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        conn.commit()

    assert {(row[0], row[1], row[2]) for row in rows} == {
        ("articles", "starred", "boolean"),
        ("sources", "enabled", "boolean"),
        ("user_sources", "enabled", "boolean"),
    }
    assert all("true" in str(row[3]).lower() or "false" in str(row[3]).lower() for row in rows)
