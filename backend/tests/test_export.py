"""Tests for #474 personal reading archive export and #778 subscriptions/preferences."""

from __future__ import annotations

import json

import pytest
from psycopg.types.json import Jsonb

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.export import assemble_user_export
from news_dashboard.ingest.service import (
    set_article_starred,
    sync_sources,
    transition_article_state,
)


def _insert_article(db_url: str, *, url_suffix: str = "1", body: str | None = None) -> int:
    with connect(database_url=db_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, body
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                "today",
                body,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_briefing(db_url: str, user_id: int, article_id: int) -> int:
    with connect(database_url=db_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(scope, status, title, summary, user_id)
            VALUES ('since_last_briefing', 'complete', 'Test Brief', 'Summary', %s)
            RETURNING id
            """,
            (user_id,),
        ).fetchone()
        assert row is not None
        brid = int(row["id"])
        conn.execute(
            "INSERT INTO briefing_articles(briefing_id, article_id) VALUES (%s, %s)",
            (brid, article_id),
        )
    return brid


def _make_user(db_url: str, username: str = "alice") -> int:
    user = create_user(username, "password123", db_path=db_url)
    return int(user["id"])


# ── assemble_user_export ──────────────────────────────────────────────────────


def test_export_includes_user_article_state(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "exporter_alice")
    aid = _insert_article(pg_clean, url_suffix="exp1")

    transition_article_state(aid, "done", db_path=pg_clean, user_id=uid)

    result = assemble_user_export(uid, database_url=pg_clean)

    assert result["schema_version"] == 2
    articles = result["articles"]
    assert len(articles) == 1
    a = articles[0]
    assert a["id"] == aid
    assert a["state"] == "done"
    assert a["done_at"] is not None
    assert a["canonical_url"] == "https://example.com/artexp1"
    assert a["title"] == "Article exp1"


def test_export_excludes_cached_article_body_text(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "exporter_no_body")
    cached_body = "Full cached article body that should not leave the database."
    aid = _insert_article(pg_clean, url_suffix="no_body", body=cached_body)

    transition_article_state(aid, "done", db_path=pg_clean, user_id=uid)

    result = assemble_user_export(uid, database_url=pg_clean)

    assert result["includes_article_bodies"] is False
    article = result["articles"][0]
    assert article["id"] == aid
    assert article["state"] == "done"
    assert "body" not in article
    assert cached_body not in json.dumps(result)


def test_export_includes_starred_articles(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "exporter_bob")
    aid = _insert_article(pg_clean, url_suffix="exp2")

    set_article_starred(aid, True, db_path=pg_clean, user_id=uid)

    result = assemble_user_export(uid, database_url=pg_clean)

    articles = result["articles"]
    assert len(articles) == 1
    assert articles[0]["starred"] is True
    assert articles[0]["starred_at"] is not None


def test_export_scoped_to_user(pg_clean: str) -> None:
    """Alice's export must not include Bob's article state."""
    sync_sources(pg_clean)
    uid_alice = _make_user(pg_clean, "scope_alice")
    uid_bob = _make_user(pg_clean, "scope_bob")

    aid_alice = _insert_article(pg_clean, url_suffix="scoped_a")
    aid_bob = _insert_article(pg_clean, url_suffix="scoped_b")

    transition_article_state(aid_alice, "done", db_path=pg_clean, user_id=uid_alice)
    transition_article_state(aid_bob, "skipped", db_path=pg_clean, user_id=uid_bob)

    alice_export = assemble_user_export(uid_alice, database_url=pg_clean)
    bob_export = assemble_user_export(uid_bob, database_url=pg_clean)

    alice_ids = {a["id"] for a in alice_export["articles"]}
    bob_ids = {a["id"] for a in bob_export["articles"]}

    assert aid_alice in alice_ids
    assert aid_bob not in alice_ids

    assert aid_bob in bob_ids
    assert aid_alice not in bob_ids


def test_export_includes_briefings(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "brief_user")
    aid = _insert_article(pg_clean, url_suffix="bexp1")
    _insert_briefing(pg_clean, uid, aid)

    result = assemble_user_export(uid, database_url=pg_clean)

    briefings = result["briefings"]
    assert len(briefings) == 1
    b = briefings[0]
    assert b["title"] == "Test Brief"
    cited = b["cited_articles"]
    assert len(cited) == 1
    assert cited[0]["article_id"] == aid


def test_export_briefings_scoped_to_user(pg_clean: str) -> None:
    """Alice's briefings must not appear in Bob's export."""
    sync_sources(pg_clean)
    uid_alice = _make_user(pg_clean, "br_scope_alice")
    uid_bob = _make_user(pg_clean, "br_scope_bob")

    aid = _insert_article(pg_clean, url_suffix="bscoped")
    brid = _insert_briefing(pg_clean, uid_alice, aid)

    alice_export = assemble_user_export(uid_alice, database_url=pg_clean)
    bob_export = assemble_user_export(uid_bob, database_url=pg_clean)

    assert any(b["id"] == brid for b in alice_export["briefings"])
    assert not any(b["id"] == brid for b in bob_export["briefings"])


def test_export_empty_for_new_user(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "empty_user")

    result = assemble_user_export(uid, database_url=pg_clean)

    assert result["articles"] == []
    assert result["briefings"] == []
    assert result["preferences"]["recommendations"] == {
        "category_weights": {},
        "novelty_weight": 1.0,
    }
    assert result["preferences"]["onboarding"] == {
        "interests": [],
        "completed_at": None,
        "updated_at": None,
    }
    assert result["preferences"]["notifications"]["push_enabled"] is False


def test_export_deterministic_ordering(pg_clean: str) -> None:
    """Articles are sorted by id ASC, so repeated calls produce identical order."""
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "order_user")
    aids = [_insert_article(pg_clean, url_suffix=f"ord{i}") for i in range(3)]
    for aid in aids:
        set_article_starred(aid, True, db_path=pg_clean, user_id=uid)

    r1 = assemble_user_export(uid, database_url=pg_clean)
    r2 = assemble_user_export(uid, database_url=pg_clean)

    assert [a["id"] for a in r1["articles"]] == [a["id"] for a in r2["articles"]]
    assert [a["id"] for a in r1["articles"]] == sorted(aids)


# ── API endpoint ──────────────────────────────────────────────────────────────


def test_export_endpoint_returns_200(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    uid = _make_user(pg_clean, "endpoint_user")
    aid = _insert_article(pg_clean, url_suffix="ep1")
    transition_article_state(aid, "done", db_path=pg_clean, user_id=uid)

    fake_user = {"id": uid, "username": "endpoint_user", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/api/users/me/export")
            assert resp.status_code == 200
            data = resp.json()
            assert data["schema_version"] == 2
            article_ids = [a["id"] for a in data["articles"]]
            assert aid in article_ids
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_export_endpoint_scoped_to_auth_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Endpoint returns only the authenticated user's data, not another user's."""
    monkeypatch.setenv("DATABASE_URL", str(pg_clean))
    sync_sources(pg_clean)

    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    uid_a = _make_user(pg_clean, "ep_alice")
    uid_b = _make_user(pg_clean, "ep_bob")

    aid_alice = _insert_article(pg_clean, url_suffix="ep_a")
    aid_bob = _insert_article(pg_clean, url_suffix="ep_b")

    transition_article_state(aid_alice, "done", db_path=pg_clean, user_id=uid_a)
    transition_article_state(aid_bob, "skipped", db_path=pg_clean, user_id=uid_b)

    fake_user = {"id": uid_a, "username": "ep_alice", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user

    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            resp = client.get("/api/users/me/export")
            assert resp.status_code == 200
            article_ids = [a["id"] for a in resp.json()["articles"]]
            assert aid_alice in article_ids
            assert aid_bob not in article_ids
    finally:
        app.dependency_overrides.pop(require_auth, None)


# ── #778: metadata, source subscriptions, preferences ─────────────────────────


def test_export_metadata_and_body_flag(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "meta_user")

    result = assemble_user_export(uid, database_url=pg_clean)

    assert result["schema_version"] == 2
    assert result["generated_at"]
    assert result["includes_article_bodies"] is False


def test_export_source_subscriptions_reflect_disabled_global_source(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "sub_user")

    with connect(database_url=pg_clean) as conn:
        slug_row = conn.execute(
            "SELECT slug FROM sources WHERE owner_user_id IS NULL ORDER BY slug LIMIT 1"
        ).fetchone()
        assert slug_row is not None
        slug = slug_row["slug"]
        conn.execute(
            """
            INSERT INTO user_sources(user_id, source_slug, enabled)
            VALUES (%s, %s, FALSE)
            ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = FALSE
            """,
            (uid, slug),
        )

    result = assemble_user_export(uid, database_url=pg_clean)

    by_slug = {s["slug"]: s for s in result["source_subscriptions"]}
    assert by_slug[slug]["subscribed"] is False
    assert by_slug[slug]["private"] is False


def test_export_includes_own_private_source_not_other_users(pg_clean: str) -> None:
    sync_sources(pg_clean)
    uid_alice = _make_user(pg_clean, "priv_alice")
    uid_bob = _make_user(pg_clean, "priv_bob")

    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
            VALUES (%s, %s, %s, %s, %s, 0, TRUE, %s)
            """,
            (
                "alice-private-feed",
                "Alice's Feed",
                "https://example.com/feed",
                "custom",
                "rss_feed",
                uid_alice,
            ),
        )

    alice_export = assemble_user_export(uid_alice, database_url=pg_clean)
    bob_export = assemble_user_export(uid_bob, database_url=pg_clean)

    alice_slugs = {s["slug"] for s in alice_export["source_subscriptions"]}
    bob_slugs = {s["slug"] for s in bob_export["source_subscriptions"]}

    assert "alice-private-feed" in alice_slugs
    assert "alice-private-feed" not in bob_slugs
    alice_private = next(
        s for s in alice_export["source_subscriptions"] if s["slug"] == "alice-private-feed"
    )
    assert alice_private["private"] is True
    assert alice_private["subscribed"] is True


def test_export_preferences_include_recommendations_onboarding_notifications(
    pg_clean: str,
) -> None:
    sync_sources(pg_clean)
    uid = _make_user(pg_clean, "pref_user")

    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO user_settings(user_id, category_weights, novelty_weight)
            VALUES (%s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE SET
              category_weights = excluded.category_weights,
              novelty_weight = excluded.novelty_weight
            """,
            (uid, Jsonb({"python": 2.0}), 0.5),
        )
        conn.execute(
            """
            INSERT INTO user_interest_profiles(user_id, interests, completed_at, updated_at)
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT(user_id) DO UPDATE SET
              interests = excluded.interests, completed_at = NOW(), updated_at = NOW()
            """,
            (uid, Jsonb(["python", "security"])),
        )
        conn.execute(
            """
            UPDATE users
            SET briefing_time = '07:30', briefing_timezone = 'America/New_York',
                briefing_push_enabled = TRUE, recap_enabled = FALSE, recap_day = 'fri'
            WHERE id = %s
            """,
            (uid,),
        )

    result = assemble_user_export(uid, database_url=pg_clean)
    prefs = result["preferences"]

    assert prefs["recommendations"] == {"category_weights": {"python": 2.0}, "novelty_weight": 0.5}
    assert prefs["onboarding"]["interests"] == ["python", "security"]
    assert prefs["onboarding"]["completed_at"] is not None
    assert prefs["notifications"]["briefing_time"] == "07:30"
    assert prefs["notifications"]["briefing_timezone"] == "America/New_York"
    assert prefs["notifications"]["push_enabled"] is True
    assert prefs["notifications"]["recap_enabled"] is False
    assert prefs["notifications"]["recap_day"] == "fri"


def test_export_preferences_scoped_to_user(pg_clean: str) -> None:
    """Alice's preferences must not leak into Bob's export."""
    sync_sources(pg_clean)
    uid_alice = _make_user(pg_clean, "pref_scope_alice")
    uid_bob = _make_user(pg_clean, "pref_scope_bob")

    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO user_settings(user_id, category_weights, novelty_weight)
            VALUES (%s, %s, %s)
            """,
            (uid_alice, Jsonb({"security": 3.0}), 1.5),
        )

    alice_export = assemble_user_export(uid_alice, database_url=pg_clean)
    bob_export = assemble_user_export(uid_bob, database_url=pg_clean)

    assert alice_export["preferences"]["recommendations"]["category_weights"] == {"security": 3.0}
    assert bob_export["preferences"]["recommendations"]["category_weights"] == {}
