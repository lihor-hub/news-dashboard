"""End-to-end regression pass over the user-visible recommendation contracts.

This module is the final guard from issue #227.  Where the per-feature suites
(``test_today_recommendations`` / ``test_recommendation_recalc``) prove one
mechanism at a time, these tests assert the *contracts* the PRD promises to the
user survive the whole ingest → score → serve pipeline:

* Today is ranked by recommendations while every eligible article stays visible.
* Low-signal, stale-score, missing-score, and missing-embedding articles remain
  visible and usable.
* The same article carries different score metadata for different users.
* Scoring failures degrade gracefully rather than breaking Today.
* The release stays scoped to Today ranking (no hiding / suppression / separate
  Recommended feed).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import news_dashboard.db as db_mod
from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.main import app
from news_dashboard.recommendations import upsert_recommendation_score

pytestmark = pytest.mark.postgres


# ── Fixtures / helpers ────────────────────────────────────────────────────────


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


def _insert_source(db_path: Path, slug: str, *, category: str = "tech", priority: int = 50) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, %s, 'rss_feed', %s, TRUE)
            ON CONFLICT(slug) DO NOTHING
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
    discovered_at: str = "2026-06-21T10:00:00+00:00",
    embedding: list[float] | None = None,
) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, importance_score, tags, discovered_at, embedding
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'rss_feed', 'today', %s, '', %s, %s)
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
                discovered_at,
                struct.pack(f"{len(embedding)}f", *embedding) if embedding else None,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _client_for(user_id: int, username: str) -> TestClient:
    fake_user = {"id": user_id, "username": username, "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user
    return TestClient(app, raise_server_exceptions=True)


def _today_items(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/articles", params={"state": "today", "limit": 50})
    assert response.status_code == 200
    return list(response.json()["items"])


# ── Ranking preserves every eligible article ──────────────────────────────────


def test_today_ranks_by_score_while_keeping_all_eligible_article_kinds_visible(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    """Today is ranked by persisted score, yet low-signal, stale, missing-score,
    and missing-embedding articles all remain in the feed and usable."""
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "contracts-ranking.db")
    _insert_source(db_path, "quiet-source", category="misc", priority=1)
    user_id = _make_user(db_path, "alice")

    high = _insert_article(db_path, "quiet-source", "high", category="misc", importance=1)
    low_signal = _insert_article(
        db_path, "quiet-source", "low-signal", category="misc", importance=1
    )
    stale = _insert_article(db_path, "quiet-source", "stale", category="misc", importance=1)
    missing_score = _insert_article(
        db_path, "quiet-source", "missing-score", category="misc", importance=1
    )
    # An article without an embedding must still rank and appear.
    missing_embedding = _insert_article(
        db_path, "quiet-source", "missing-embedding", category="misc", importance=1, embedding=None
    )

    upsert_recommendation_score(user_id, high, 95.0, db_path=db_path)
    upsert_recommendation_score(user_id, low_signal, 5.0, db_path=db_path)
    # Stale flag must not hide the article — it stays visible with its last score.
    upsert_recommendation_score(user_id, stale, 40.0, db_path=db_path)
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE user_article_recommendations SET stale = TRUE"
            " WHERE user_id = %s AND article_id = %s",
            (user_id, stale),
        )

    try:
        with _client_for(user_id, "alice") as client:
            items = _today_items(client)
    finally:
        app.dependency_overrides.pop(require_auth, None)

    ids = [int(item["id"]) for item in items]
    # Every eligible article is present regardless of score state.
    assert set(ids) == {high, low_signal, stale, missing_score, missing_embedding}
    # Scored articles rank by score; the missing-score articles fall back gracefully.
    assert ids.index(high) < ids.index(stale) < ids.index(low_signal)


def test_low_signal_and_unscored_articles_remain_usable(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    """A low-signal article keeps its link/title payload so it stays actionable."""
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "contracts-lowsignal.db")
    _insert_source(db_path, "quiet-source", category="misc", priority=1)
    user_id = _make_user(db_path, "alice")
    low = _insert_article(db_path, "quiet-source", "low", category="misc", importance=1)
    upsert_recommendation_score(user_id, low, 2.0, db_path=db_path)

    try:
        with _client_for(user_id, "alice") as client:
            items = _today_items(client)
    finally:
        app.dependency_overrides.pop(require_auth, None)

    item = next(it for it in items if int(it["id"]) == low)
    assert item["title"]
    assert item["url"]
    assert item["state"] == "today"


# ── Per-user isolation of score metadata ──────────────────────────────────────


def test_same_article_carries_different_score_metadata_per_user(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    """One shared article exposes different recommendation_score to each user,
    which is what drives the different compact labels in the UI."""
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "contracts-isolation.db")
    _insert_source(db_path, "shared", category="misc", priority=1)
    alice = _make_user(db_path, "alice")
    bob = _make_user(db_path, "bob")
    article = _insert_article(db_path, "shared", "shared", category="misc", importance=1)

    upsert_recommendation_score(alice, article, 90.0, db_path=db_path)
    upsert_recommendation_score(bob, article, 10.0, db_path=db_path)

    try:
        with _client_for(alice, "alice") as client:
            alice_item = next(it for it in _today_items(client) if int(it["id"]) == article)
        with _client_for(bob, "bob") as client:
            bob_item = next(it for it in _today_items(client) if int(it["id"]) == article)
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert alice_item["recommendation_score"] == pytest.approx(90.0)
    assert bob_item["recommendation_score"] == pytest.approx(10.0)
    # Same underlying article, different per-user metadata.
    assert alice_item["id"] == bob_item["id"]


# ── Graceful degradation ──────────────────────────────────────────────────────


def test_today_stays_intact_when_no_scores_have_been_computed(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    """If scoring never ran (ingestion/recalc failure), Today still serves every
    eligible article via the cold-start fallback rather than breaking."""
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "contracts-noscore.db")
    _insert_source(db_path, "src", category="ai", priority=80)
    user_id = _make_user(db_path, "alice")
    first = _insert_article(db_path, "src", "first", category="ai", importance=70)
    second = _insert_article(db_path, "src", "second", category="ai", importance=70)

    try:
        with _client_for(user_id, "alice") as client:
            items = _today_items(client)
    finally:
        app.dependency_overrides.pop(require_auth, None)

    ids = {int(item["id"]) for item in items}
    assert {first, second} <= ids
    # Unscored articles surface a null score rather than erroring.
    for item in items:
        if int(item["id"]) in {first, second}:
            assert item["recommendation_score"] is None


# ── Scope guard: ranking only, no hiding / separate feed ──────────────────────


def test_release_stays_scoped_to_ranking_without_hiding_or_separate_feed(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    """The recommendation release reorders Today; it must not suppress articles
    nor introduce a separate Recommended endpoint."""
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "contracts-scope.db")
    _insert_source(db_path, "src", category="misc", priority=1)
    user_id = _make_user(db_path, "alice")
    disliked = _insert_article(db_path, "src", "disliked", category="misc", importance=1)
    liked = _insert_article(db_path, "src", "liked", category="misc", importance=1)
    # A near-zero score must not hide the article — no suppression in this release.
    upsert_recommendation_score(user_id, disliked, 0.0, db_path=db_path)
    upsert_recommendation_score(user_id, liked, 99.0, db_path=db_path)

    try:
        with _client_for(user_id, "alice") as client:
            items = _today_items(client)
            # No dedicated Recommended feed ships in this release.
            recommended_feed = client.get("/api/recommendations")
    finally:
        app.dependency_overrides.pop(require_auth, None)

    ids = {int(item["id"]) for item in items}
    assert {disliked, liked} <= ids
    assert recommended_feed.status_code == 404
