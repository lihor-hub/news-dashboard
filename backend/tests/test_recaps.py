from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.main import app
from news_dashboard.recaps.service import assemble_weekly_recap, list_recaps, save_weekly_recap

pytestmark = pytest.mark.postgres


def _setup_db(monkeypatch: Any, pg_url: str) -> str:
    monkeypatch.setenv("DATABASE_URL", pg_url)
    init_db(database_url=pg_url)
    return pg_url


def _make_user(db_path: str, username: str) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_article(db_path: str, slug: str, category: str) -> int:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, %s, 'rss_feed', 50, TRUE)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug.title(), f"https://example.com/{slug}.xml", category),
        )
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, discovered_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'rss_feed', 'today', %s)
            RETURNING id
            """,
            (
                f"https://example.com/{slug}/article",
                f"https://example.com/{slug}/article",
                f"{category.title()} Article",
                slug,
                slug.title(),
                category,
                "2026-06-21T10:00:00+00:00",
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _client_for(user_id: int) -> TestClient:
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    return TestClient(app, raise_server_exceptions=True)


def test_assemble_weekly_recap_aggregates_trailing_week(monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path, "alice")
    article_id = _insert_article(db_path, "science-weekly", "science")
    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=30)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state, done_at)"
            " VALUES (%s, %s, 'done', %s)",
            (user_id, article_id, now),
        )
        conn.execute(
            "INSERT INTO user_events(user_id, event_type, article_id, duration_ms, created_at)"
            " VALUES (%s, 'heartbeat', NULL, 120000, %s)",
            (user_id, now),
        )
        # A second article, done outside the 7-day window: must not be counted.
        other_article_id = _insert_article(db_path, "old-news", "science")
        conn.execute(
            "INSERT INTO user_article_state(user_id, article_id, state, done_at)"
            " VALUES (%s, %s, 'done', %s)",
            (user_id, other_article_id, stale),
        )

    recap = assemble_weekly_recap(user_id, now=now, database_url=db_path)

    assert recap["articles_read"] == 1
    assert recap["categories"][0]["category"] == "science"
    assert recap["categories"][0]["count"] == 1
    assert recap["minutes_read"] == 2.0
    assert recap["current_streak_days"] == 1


def test_save_and_list_recaps_upserts_by_week(monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path, "alice")
    recap = {
        "week_start": "2026-06-22",
        "week_end": "2026-06-29",
        "generated_at": "2026-06-29T00:00:00+00:00",
        "articles_read": 3,
        "categories": [],
        "sources": [],
        "minutes_read": 10.0,
        "current_streak_days": 2,
    }

    saved = save_weekly_recap(user_id, recap, "Great week!", database_url=db_path)
    assert saved["narrative"] == "Great week!"
    assert saved["data"]["articles_read"] == 3

    updated = dict(recap, articles_read=5)
    save_weekly_recap(user_id, updated, "Even better!", database_url=db_path)

    recaps = list_recaps(user_id, database_url=db_path)
    assert len(recaps) == 1
    assert recaps[0]["data"]["articles_read"] == 5
    assert recaps[0]["narrative"] == "Even better!"


def test_recaps_endpoint_returns_saved_history(monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path, "alice")
    recap = {
        "week_start": "2026-06-22",
        "week_end": "2026-06-29",
        "generated_at": "2026-06-29T00:00:00+00:00",
        "articles_read": 4,
        "categories": [],
        "sources": [],
        "minutes_read": 15.0,
        "current_streak_days": 3,
    }
    save_weekly_recap(user_id, recap, "Nice reading week", database_url=db_path)

    try:
        with _client_for(user_id) as client:
            list_response = client.get("/api/recaps")
            latest_response = client.get("/api/recaps/latest")
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["data"]["articles_read"] == 4

    assert latest_response.status_code == 200
    assert latest_response.json()["narrative"] == "Nice reading week"


def test_recaps_latest_endpoint_404_when_none(monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path, "alice")

    try:
        with _client_for(user_id) as client:
            response = client.get("/api/recaps/latest")
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 404
