from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import news_dashboard.db as db_mod
from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.ingest import sync_sources
from news_dashboard.main import app
from news_dashboard.recommendations import upsert_recommendation_score

pytestmark = pytest.mark.postgres


def _setup_db(tmp_path: Path, monkeypatch: Any, pg_url: str, name: str) -> Path:
    db_path = tmp_path / name
    monkeypatch.setenv("DATABASE_URL", pg_url)
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    init_db(db_path)
    return db_path


def _make_user(db_path: Path, username: str) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_source(
    db_path: Path,
    slug: str,
    *,
    category: str = "tech",
    priority: int = 50,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, %s, 'rss_feed', %s, TRUE)
            ON CONFLICT(slug) DO UPDATE SET
              name = excluded.name,
              url = excluded.url,
              category = excluded.category,
              priority = excluded.priority,
              enabled = TRUE
            """,
            (slug, slug.title(), f"https://example.com/{slug}.xml", category, priority),
        )


def _insert_article(
    db_path: Path,
    slug: str,
    suffix: str,
    *,
    category: str = "tech",
    importance: int = 50,
    tags: str = "",
    discovered_at: str = "2026-06-21T10:00:00+00:00",
) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, importance_score, tags, discovered_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'rss_feed', 'today', %s, %s, %s)
            RETURNING id
            """,
            (
                f"https://example.com/articles/{suffix}",
                f"https://example.com/articles/{suffix}",
                f"Article {suffix}",
                slug,
                slug.title(),
                category,
                importance,
                tags,
                discovered_at,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _client_for(user_id: int, username: str) -> TestClient:
    fake_user = {"id": user_id, "username": username, "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user
    return TestClient(app, raise_server_exceptions=True)


def _today_ids(client: TestClient) -> list[int]:
    response = client.get("/api/articles", params={"state": "today", "limit": 20})
    assert response.status_code == 200
    return [int(item["id"]) for item in response.json()["items"]]


def test_today_endpoint_orders_by_persisted_scores_and_keeps_missing_visible(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "today-recs.db")
    _insert_source(db_path, "quiet-source", category="misc", priority=1)
    user_id = _make_user(db_path, "alice")

    low = _insert_article(
        db_path,
        "quiet-source",
        "persisted-low",
        category="misc",
        importance=1,
        discovered_at="2026-06-20T10:00:00+00:00",
    )
    high = _insert_article(
        db_path,
        "quiet-source",
        "persisted-high",
        category="misc",
        importance=1,
        discovered_at="2026-06-19T10:00:00+00:00",
    )
    missing = _insert_article(
        db_path,
        "quiet-source",
        "missing-score",
        category="misc",
        importance=1,
        discovered_at="2020-01-01T00:00:00+00:00",
    )

    upsert_recommendation_score(user_id, low, 20.0, db_path=db_path)
    upsert_recommendation_score(user_id, high, 95.0, db_path=db_path)

    try:
        with _client_for(user_id, "alice") as client:
            ids = _today_ids(client)
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert ids[:3] == [high, low, missing]
    assert set(ids) >= {high, low, missing}


def test_today_recommendation_scores_are_isolated_per_user(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "per-user-recs.db")
    _insert_source(db_path, "shared-source", category="misc", priority=1)
    alice_id = _make_user(db_path, "alice")
    bob_id = _make_user(db_path, "bob")
    first = _insert_article(db_path, "shared-source", "first", category="misc", importance=1)
    second = _insert_article(db_path, "shared-source", "second", category="misc", importance=1)

    upsert_recommendation_score(alice_id, first, 90.0, db_path=db_path)
    upsert_recommendation_score(alice_id, second, 10.0, db_path=db_path)
    upsert_recommendation_score(bob_id, first, 10.0, db_path=db_path)
    upsert_recommendation_score(bob_id, second, 90.0, db_path=db_path)

    try:
        with _client_for(alice_id, "alice") as client:
            alice_ids = _today_ids(client)
        with _client_for(bob_id, "bob") as client:
            bob_ids = _today_ids(client)
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert alice_ids[:2] == [first, second]
    assert bob_ids[:2] == [second, first]


def test_today_endpoint_uses_cold_start_fallback_for_missing_scores(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "cold-start-recs.db")
    sync_sources(db_path)
    _insert_source(db_path, "hot-ai-source", category="ai", priority=95)
    _insert_source(db_path, "low-priority-source", category="misc", priority=1)
    user_id = _make_user(db_path, "alice")

    old_low_signal = _insert_article(
        db_path,
        "low-priority-source",
        "old-low-signal",
        category="misc",
        importance=1,
        tags="",
        discovered_at="2020-01-01T00:00:00+00:00",
    )
    recent_topic_match = _insert_article(
        db_path,
        "hot-ai-source",
        "recent-topic-match",
        category="ai",
        importance=80,
        tags="agents,llm",
        discovered_at="2026-06-21T12:00:00+00:00",
    )
    older_important = _insert_article(
        db_path,
        "hot-ai-source",
        "older-important",
        category="ai",
        importance=70,
        tags="",
        discovered_at="2026-06-10T12:00:00+00:00",
    )

    try:
        with _client_for(user_id, "alice") as client:
            ids = _today_ids(client)
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert ids[:3] == [recent_topic_match, older_important, old_low_signal]


def test_recalculate_mine_scores_callers_own_feed(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "recalc-mine.db")
    _insert_source(db_path, "hot-ai-source", category="ai", priority=95)
    user_id = _make_user(db_path, "alice")

    _insert_article(db_path, "hot-ai-source", "a", category="ai", importance=80)
    _insert_article(db_path, "hot-ai-source", "b", category="ai", importance=70)

    try:
        with _client_for(user_id, "alice") as client:
            response = client.post("/api/recommendations/recalculate-mine")
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    assert response.json()["scored"] == 2
