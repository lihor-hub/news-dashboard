"""Tests for #474 personal reading archive export."""

from __future__ import annotations

import pytest

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.export import assemble_user_export
from news_dashboard.ingest import set_article_starred, sync_sources, transition_article_state


def _insert_article(db_url: str, *, url_suffix: str = "1") -> int:
    with connect(database_url=db_url) as conn:
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
                "today",
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

    assert result["schema_version"] == 1
    articles = result["articles"]
    assert len(articles) == 1
    a = articles[0]
    assert a["id"] == aid
    assert a["state"] == "done"
    assert a["done_at"] is not None
    assert a["canonical_url"] == "https://example.com/artexp1"
    assert a["title"] == "Article exp1"


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
            assert data["schema_version"] == 1
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
