from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.main import app
from news_dashboard.reading_progress.service import get_streak, list_achievements

pytestmark = pytest.mark.postgres


def _setup_db(monkeypatch: Any, pg_url: str) -> str:
    monkeypatch.setenv("DATABASE_URL", pg_url)
    init_db(database_url=pg_url)
    return pg_url


def _make_user(database_url: str, username: str = "alice") -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_article(database_url: str, slug: str, state: str = "archived") -> int:
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, 'tech', 'rss_feed', 50, TRUE)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug.title(), f"https://example.com/{slug}.xml"),
        )
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, discovered_at
            )
            VALUES (%s, %s, %s, %s, %s, 'tech', 'rss_feed', %s, %s)
            RETURNING id
            """,
            (
                f"https://example.com/{slug}/article",
                f"https://example.com/{slug}/article",
                slug.title(),
                slug,
                slug.title(),
                state,
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


def test_streak_counts_consecutive_reading_days_and_resets_after_gap(
    monkeypatch: Any,
    pg_clean: str,
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    first_article = _insert_article(database_url, "one")
    second_article = _insert_article(database_url, "two")
    third_article = _insert_article(database_url, "three")

    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state, done_at)
            VALUES
              (%s, %s, 'done', '2026-06-28T12:00:00+00:00'),
              (%s, %s, 'done', '2026-06-29T12:00:00+00:00'),
              (%s, %s, 'done', '2026-07-01T12:00:00+00:00')
            """,
            (user_id, first_article, user_id, second_article, user_id, third_article),
        )

    streak = get_streak(
        user_id,
        now=datetime(2026, 7, 2, 9, tzinfo=timezone.utc),
        database_url=database_url,
    )
    assert streak["current_streak_days"] == 1
    assert streak["longest_streak_days"] == 2
    assert streak["last_active_date"] == "2026-07-01"

    stale = get_streak(
        user_id,
        now=datetime(2026, 7, 4, 9, tzinfo=timezone.utc),
        database_url=database_url,
    )
    assert stale["current_streak_days"] == 0


def test_achievements_unlock_once_and_endpoint_returns_progress(
    monkeypatch: Any,
    pg_clean: str,
) -> None:
    database_url = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(database_url)
    articles = [_insert_article(database_url, f"article-{idx}") for idx in range(7)]

    with connect(database_url=database_url) as conn:
        for idx, article_id in enumerate(articles, start=1):
            conn.execute(
                """
                INSERT INTO user_article_state(user_id, article_id, state, done_at)
                VALUES (%s, %s, 'done', %s)
                """,
                (user_id, article_id, f"2026-06-{20 + idx:02d}T12:00:00+00:00"),
            )
        conn.execute(
            """
            INSERT INTO user_quizzes(user_id, questions, score, submitted_at)
            VALUES (%s, '[]'::jsonb, 1, '2026-06-27T12:00:00+00:00')
            """,
            (user_id,),
        )

    first = list_achievements(
        user_id,
        now=datetime(2026, 6, 27, 18, tzinfo=timezone.utc),
        database_url=database_url,
    )
    second = list_achievements(
        user_id,
        now=datetime(2026, 6, 27, 18, tzinfo=timezone.utc),
        database_url=database_url,
    )

    unlocked = {item["key"]: item for item in first if item["unlocked"]}
    assert {"seven_day_streak", "first_quiz_passed", "inbox_zero"} <= set(unlocked)
    assert unlocked["seven_day_streak"]["progress"] == 7
    assert second == first
    with connect(database_url=database_url) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM user_achievements WHERE user_id = %s",
            (user_id,),
        ).fetchone()["count"]
    assert count == 3

    try:
        with _client_for(user_id) as client:
            streak_response = client.get("/api/users/me/streak")
            achievements_response = client.get("/api/users/me/achievements")
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert streak_response.status_code == 200
    assert achievements_response.status_code == 200
    assert achievements_response.json()["items"][0]["key"] == "seven_day_streak"
