"""Tests for #220 Today feed recommendation ranking."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from news_dashboard.db import POSTGRES_MULTIUSER_SCHEMA, connect
from news_dashboard.ingest import list_articles, upsert_article_recommendation

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg_env(pg_clean: str) -> Generator[str]:
    """Set DATABASE_URL so runtime code uses the PostgreSQL test database."""
    original = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_clean
    try:
        yield pg_clean
    finally:
        if original is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original


def _make_user(pg_url: str, username: str) -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "x"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _add_source(
    pg_url: str,
    *,
    slug: str,
    category: str = "tech",
    priority: int = 50,
    kind: str = "rss_feed",
) -> None:
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            ON CONFLICT(slug) DO UPDATE SET
              category = excluded.category,
              kind = excluded.kind,
              priority = excluded.priority
            """,
            (slug, slug, f"https://example.com/{slug}.xml", category, kind, priority),
        )


def _add_article(  # noqa: PLR0913
    pg_url: str,
    *,
    source_slug: str,
    suffix: str,
    title: str,
    category: str = "tech",
    importance_score: int = 50,
    tags: str = "",
    discovered_days_ago: int = 0,
) -> int:
    discovered_at = (datetime.now(timezone.utc) - timedelta(days=discovered_days_ago)).isoformat()
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name, category, kind,
              importance_score, tags, discovered_at, state
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'rss_feed', %s, %s, %s, 'today')
            RETURNING id
            """,
            (
                f"https://example.com/{suffix}",
                f"https://example.com/{suffix}",
                title,
                source_slug,
                source_slug,
                category,
                importance_score,
                tags,
                discovered_at,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _set_recommendation(
    pg_url: str,
    *,
    user_id: int,
    article_id: int,
    score: float,
    metadata: str = '{"reason": "test"}',
) -> None:
    import json

    os.environ["DATABASE_URL"] = pg_url
    upsert_article_recommendation(
        user_id=user_id,
        article_id=article_id,
        score=score,
        metadata=json.loads(metadata),
    )


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


def test_schema_defines_per_user_article_recommendations() -> None:
    schema = "\n".join(POSTGRES_MULTIUSER_SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS user_article_recommendations" in schema
    assert "PRIMARY KEY (user_id, article_id)" in schema
    assert "metadata     JSONB" in schema


def test_recommendation_metadata_can_be_persisted_per_user_article(pg_env: str) -> None:
    user_id = _make_user(pg_env, "persist-user")
    _add_source(pg_env, slug="persist-src")
    article_id = _add_article(pg_env, source_slug="persist-src", suffix="persist", title="Persist")

    row = upsert_article_recommendation(
        user_id=user_id,
        article_id=article_id,
        score=0.77,
        metadata={"reason": "cold-start"},
        score_source="cold_start",
    )

    assert row["user_id"] == user_id
    assert row["article_id"] == article_id
    assert row["score"] == 0.77
    assert row["score_source"] == "cold_start"
    assert row["metadata"] == {"reason": "cold-start"}


def test_api_today_orders_by_persisted_recommendation_scores(pg_env: str) -> None:
    user_id = _make_user(pg_env, "rank-user")
    _add_source(pg_env, slug="rank-src")
    low = _add_article(pg_env, source_slug="rank-src", suffix="low", title="Low")
    high = _add_article(pg_env, source_slug="rank-src", suffix="high", title="High")
    middle = _add_article(pg_env, source_slug="rank-src", suffix="middle", title="Middle")
    _set_recommendation(pg_env, user_id=user_id, article_id=low, score=0.2)
    _set_recommendation(pg_env, user_id=user_id, article_id=high, score=0.9)
    _set_recommendation(pg_env, user_id=user_id, article_id=middle, score=0.5)

    client = _api_client(user_id, "rank-user")
    try:
        response = client.get("/api/articles", params={"state": "today"})
    finally:
        _clear_auth_overrides()

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [high, middle, low]
    assert items[0]["recommendation_score"] == 0.9
    assert items[0]["recommendation_score_source"] == "persisted"
    assert items[0]["recommendation_metadata"] == {"reason": "test"}


def test_today_keeps_missing_score_articles_visible_with_fallback(pg_env: str) -> None:
    user_id = _make_user(pg_env, "visible-user")
    _add_source(pg_env, slug="visible-src", priority=50)
    scored = _add_article(pg_env, source_slug="visible-src", suffix="scored", title="Scored")
    missing = _add_article(
        pg_env,
        source_slug="visible-src",
        suffix="missing",
        title="Missing but visible",
        importance_score=85,
        tags="agents,llm",
    )
    _set_recommendation(pg_env, user_id=user_id, article_id=scored, score=0.4)

    articles = list_articles(state="today", user_id=user_id)

    assert {article["id"] for article in articles} == {scored, missing}
    fallback = next(article for article in articles if article["id"] == missing)
    assert fallback["recommendation_score_source"] == "cold_start"
    assert fallback["recommendation_score"] > 0


def test_today_recommendation_scores_are_per_user(pg_env: str) -> None:
    alice = _make_user(pg_env, "alice-rank")
    bob = _make_user(pg_env, "bob-rank")
    _add_source(pg_env, slug="isolation-src")
    first = _add_article(pg_env, source_slug="isolation-src", suffix="first", title="First")
    second = _add_article(pg_env, source_slug="isolation-src", suffix="second", title="Second")
    _set_recommendation(pg_env, user_id=alice, article_id=first, score=0.95)
    _set_recommendation(pg_env, user_id=alice, article_id=second, score=0.1)
    _set_recommendation(pg_env, user_id=bob, article_id=first, score=0.1)
    _set_recommendation(pg_env, user_id=bob, article_id=second, score=0.95)

    assert [article["id"] for article in list_articles(state="today", user_id=alice)] == [
        first,
        second,
    ]
    assert [article["id"] for article in list_articles(state="today", user_id=bob)] == [
        second,
        first,
    ]


def test_today_missing_score_fallback_uses_cold_start_signals(pg_env: str) -> None:
    user_id = _make_user(pg_env, "fallback-user")
    _add_source(pg_env, slug="cold-high", category="agents", priority=90)
    _add_source(pg_env, slug="cold-low", category="general", priority=20)
    low = _add_article(
        pg_env,
        source_slug="cold-low",
        suffix="old-low",
        title="Old low signal",
        category="general",
        importance_score=20,
        tags="",
        discovered_days_ago=10,
    )
    high = _add_article(
        pg_env,
        source_slug="cold-high",
        suffix="fresh-high",
        title="Fresh agent release",
        category="agents",
        importance_score=80,
        tags="agents,release",
        discovered_days_ago=0,
    )

    articles = list_articles(state="today", user_id=user_id)

    assert [article["id"] for article in articles] == [high, low]
    assert all(article["recommendation_score_source"] == "cold_start" for article in articles)
    assert articles[0]["recommendation_score"] > articles[1]["recommendation_score"]
