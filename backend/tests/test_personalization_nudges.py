"""Tests for personalization nudges (source-level and topic-level suggestions)."""

from __future__ import annotations

from typing import Any

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.personalization_nudges import apply_nudge, dismiss_nudge, generate_nudges
from news_dashboard.recommendations import get_recommendation_preferences

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_user(database_url: str, username: str = "alice") -> int:
    user = create_user(username, "pw", db_path=database_url)
    return int(user["id"])


def _add_source(conn: Any, slug: str, name: str, category: str = "tech") -> None:
    conn.execute(
        """
        INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
        VALUES (%s, %s, %s, %s, 'rss_feed', 10, TRUE)
        """,
        (slug, name, f"https://example.com/{slug}.xml", category),
    )


def _add_article(
    conn: Any,
    *,
    user_id: int,
    slug: str,
    index: int,
    category: str = "tech",
    state: str = "today",
    days_old: int = 1,
) -> None:
    row = conn.execute(
        """
        INSERT INTO articles(
          url, canonical_url, title, source_slug, source_name, category, kind, discovered_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'rss_feed', NOW() - (%s * INTERVAL '1 day'))
        RETURNING id
        """,
        (
            f"https://example.com/{slug}/{index}",
            f"https://example.com/{slug}/{index}",
            f"{slug} article {index}",
            slug,
            slug,
            category,
            days_old,
        ),
    ).fetchone()
    article_id = int(row["id"])
    if state == "today":
        return
    conn.execute(
        """
        INSERT INTO user_article_state(
          user_id, article_id, state, starred, done_at, skipped_at, archived_at
        )
        VALUES (
          %s, %s, %s, %s,
          CASE WHEN %s = 'done' THEN NOW() ELSE NULL END,
          CASE WHEN %s = 'skipped' THEN NOW() ELSE NULL END,
          CASE WHEN %s = 'archived' THEN NOW() ELSE NULL END
        )
        """,
        (user_id, article_id, state, state == "starred", state, state, state),
    )


def _api_client(user_id: int) -> Any:
    from fastapi.testclient import TestClient

    from news_dashboard.auth import require_admin, require_auth
    from news_dashboard.main import app

    fake = {"id": user_id, "username": "testuser", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake
    app.dependency_overrides[require_admin] = lambda: fake
    return TestClient(app, raise_server_exceptions=True)


# ── source-level nudge tests ───────────────────────────────────────────────────


def test_generate_nudge_high_skip_rate_source(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "noise-feed", "Noise Feed")
        for i in range(28):
            _add_article(conn, user_id=uid, slug="noise-feed", index=i, state="skipped")
        for i in range(28, 30):
            _add_article(conn, user_id=uid, slug="noise-feed", index=i, state="done")

    nudges = generate_nudges(uid, database_url=pg_clean)

    assert len(nudges) == 1
    nudge = nudges[0]
    assert nudge["id"] == "source:noise-feed"
    assert nudge["kind"] == "source"
    assert nudge["action"] == "disable_source"
    assert nudge["target"] == "noise-feed"
    assert nudge["skip_rate"] > 0.75


def test_generate_nudge_low_skip_rate_source_not_returned(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "good-feed", "Good Feed")
        for i in range(20):
            _add_article(conn, user_id=uid, slug="good-feed", index=i, state="done")
        for i in range(20, 30):
            _add_article(conn, user_id=uid, slug="good-feed", index=i, state="skipped")

    nudges = generate_nudges(uid, database_url=pg_clean)
    source_nudges = [n for n in nudges if n["kind"] == "source"]
    assert source_nudges == []


def test_generate_nudge_below_min_articles_not_returned(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "tiny-feed", "Tiny Feed")
        for i in range(5):
            _add_article(conn, user_id=uid, slug="tiny-feed", index=i, state="skipped")

    nudges = generate_nudges(uid, database_url=pg_clean)
    assert nudges == []


# ── topic-level nudge tests ────────────────────────────────────────────────────


def test_generate_nudge_high_skip_rate_topic(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "politics-feed", "Politics Feed", category="politics")
        for i in range(20):
            _add_article(
                conn,
                user_id=uid,
                slug="politics-feed",
                index=i,
                category="politics",
                state="skipped",
            )
        for i in range(20, 25):
            _add_article(
                conn, user_id=uid, slug="politics-feed", index=i, category="politics", state="done"
            )

    nudges = generate_nudges(uid, database_url=pg_clean, max_results=10)
    topic_nudges = [n for n in nudges if n["kind"] == "topic"]
    assert len(topic_nudges) >= 1
    assert topic_nudges[0]["target"] == "politics"
    assert topic_nudges[0]["action"] == "reduce_topic_weight"


# ── apply nudge tests ─────────────────────────────────────────────────────────


def test_apply_source_nudge_disables_source(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "noisy", "Noisy")

    result = apply_nudge(uid, "source:noisy", database_url=pg_clean)
    assert result["applied"] is True
    assert result["kind"] == "source"

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT enabled FROM user_sources WHERE user_id = %s AND source_slug = 'noisy'",
            (uid,),
        ).fetchone()
    assert row is not None
    assert row["enabled"] is False


def test_apply_source_nudge_records_permanent_dismissal(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "noisy2", "Noisy2")
    apply_nudge(uid, "source:noisy2", database_url=pg_clean)

    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT cooldown_until FROM user_nudge_dismissals"
            " WHERE user_id = %s AND nudge_kind = 'source' AND nudge_target = 'noisy2'",
            (uid,),
        ).fetchone()
    assert row is not None
    assert row["cooldown_until"] is not None


def test_apply_topic_nudge_reduces_category_weight(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)

    result = apply_nudge(uid, "topic:politics", database_url=pg_clean)
    assert result["applied"] is True
    assert result["kind"] == "topic"
    assert result["new_weight"] == 0.75

    prefs = get_recommendation_preferences(uid, database_url=pg_clean)
    assert prefs.category_weights.get("politics", 1.0) == 0.75


def test_apply_topic_nudge_does_not_go_below_zero(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)

    for _ in range(5):
        apply_nudge(uid, "topic:politics", database_url=pg_clean)

    prefs = get_recommendation_preferences(uid, database_url=pg_clean)
    assert prefs.category_weights.get("politics", 1.0) >= 0.0


def test_apply_nudge_invalid_id(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    result = apply_nudge(uid, "badinput", database_url=pg_clean)
    assert result["applied"] is False


# ── dismiss nudge tests ────────────────────────────────────────────────────────


def test_dismiss_nudge_suppresses_future_nudge(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "noisy3", "Noisy3")
        for i in range(30):
            _add_article(conn, user_id=uid, slug="noisy3", index=i, state="skipped")

    before = generate_nudges(uid, database_url=pg_clean)
    assert any(n["target"] == "noisy3" for n in before)

    dismiss_nudge(uid, "source:noisy3", cooldown_days=7, database_url=pg_clean)

    after = generate_nudges(uid, database_url=pg_clean)
    assert not any(n["target"] == "noisy3" for n in after)


def test_dismiss_nudge_invalid_id(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    result = dismiss_nudge(uid, "badinput", database_url=pg_clean)
    assert result["dismissed"] is False


# ── API endpoint tests ────────────────────────────────────────────────────────


def test_api_get_nudges(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    client = _api_client(uid)

    resp = client.get("/api/personalization/nudges")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_api_apply_nudge_source(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        _add_source(conn, "api-noisy", "Api Noisy")
    client = _api_client(uid)

    resp = client.post("/api/personalization/nudges/apply", json={"nudge_id": "source:api-noisy"})
    assert resp.status_code == 200
    assert resp.json()["applied"] is True


def test_api_dismiss_nudge(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    client = _api_client(uid)

    resp = client.post(
        "/api/personalization/nudges/dismiss",
        json={"nudge_id": "source:somekey", "cooldown_days": 14},
    )
    assert resp.status_code == 200
    assert resp.json()["dismissed"] is True


def test_existing_sources_cleanup_suggestions_still_work(pg_clean: str, monkeypatch: Any) -> None:
    """Regression: existing cleanup-suggestions endpoint must still function."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    uid = _make_user(pg_clean)
    client = _api_client(uid)

    resp = client.get("/api/sources/cleanup-suggestions")
    assert resp.status_code == 200
    assert "items" in resp.json()
