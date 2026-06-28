from __future__ import annotations

import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from news_dashboard.db import connect, init_db
from news_dashboard.recommendations import (
    FRESHNESS_SCORE_SPAN,
    NOVELTY_SCORE_SPAN,
    freshness_adjustment,
    novelty_adjustment,
    recompute_user_recommendations,
)

pytestmark = pytest.mark.postgres


# ── Pure freshness/novelty logic (no database) ────────────────────────────────


def test_freshness_lifts_recent_high_quality_articles() -> None:
    fresh = freshness_adjustment(0.0, 100)
    stale = freshness_adjustment(1000.0, 100)
    assert fresh == pytest.approx(FRESHNESS_SCORE_SPAN)
    assert stale == pytest.approx(0.0)
    assert fresh > stale


def test_freshness_scales_with_quality() -> None:
    high = freshness_adjustment(0.0, 100)
    low = freshness_adjustment(0.0, 0)
    assert high > low
    assert low == pytest.approx(0.0)


def test_freshness_degrades_when_age_unknown() -> None:
    assert freshness_adjustment(None, 100) == 0.0


def test_novelty_rewards_dissimilar_articles() -> None:
    profile = [1.0, 0.0]
    similar = novelty_adjustment([1.0, 0.0], profile, 100)
    surprising = novelty_adjustment([-1.0, 0.0], profile, 100)
    assert surprising == pytest.approx(NOVELTY_SCORE_SPAN)
    assert similar == pytest.approx(0.0)
    assert surprising > similar


def test_novelty_requires_plausibility_via_quality() -> None:
    profile = [1.0, 0.0]
    # A surprising but low-quality article gets no novelty lift; quality gates it.
    assert novelty_adjustment([0.0, 1.0], profile, 0) == pytest.approx(0.0)
    assert novelty_adjustment([0.0, 1.0], profile, 100) > 0.0


def test_novelty_degrades_when_vectors_missing() -> None:
    assert novelty_adjustment(None, [1.0, 0.0], 100) == 0.0
    assert novelty_adjustment([1.0, 0.0], None, 100) == 0.0
    assert novelty_adjustment([1.0, 0.0, 0.0], [1.0, 0.0], 100) == 0.0


# ── Database-backed recompute ─────────────────────────────────────────────────


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


def _insert_source(db_path: str, slug: str, *, category: str = "tech", priority: int = 50) -> None:
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
    db_path: str,
    slug: str,
    suffix: str,
    *,
    category: str = "tech",
    importance: int = 50,
    discovered_at: str = "2026-06-21T10:00:00+00:00",
    embedding: list[float] | None = None,
) -> int:
    blob = struct.pack(f"{len(embedding)}f", *embedding) if embedding is not None else None
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, importance_score, discovered_at, embedding
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
                discovered_at,
                blob,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _hours_ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _set_state(
    db_path: str, user_id: int, article_id: int, *, state: str, starred: bool = False
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state, starred)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(user_id, article_id) DO UPDATE SET
              state = excluded.state, starred = excluded.starred
            """,
            (user_id, article_id, state, starred),
        )


def _signals(db_path: str, user_id: int, article_id: int) -> dict[str, Any]:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT recommendation_score, signals FROM user_article_recommendations"
            " WHERE user_id = %s AND article_id = %s",
            (user_id, article_id),
        ).fetchone()
    assert row is not None
    data = dict(row["signals"])
    data["recommendation_score"] = float(row["recommendation_score"])
    return data


def test_freshness_lifts_recent_article_over_older_twin(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    _insert_source(db_path, "src")
    user_id = _make_user(db_path, "alice")

    # Two articles identical except for age; the recent one should score higher.
    recent = _insert_article(db_path, "src", "recent", importance=90, discovered_at=_hours_ago(2))
    old = _insert_article(db_path, "src", "old", importance=90, discovered_at=_hours_ago(1000))

    recompute_user_recommendations(user_id, db_path=db_path)

    recent_signals = _signals(db_path, user_id, recent)
    old_signals = _signals(db_path, user_id, old)
    assert recent_signals["freshness_adjustment"] > old_signals["freshness_adjustment"]
    assert recent_signals["recommendation_score"] > old_signals["recommendation_score"]


def test_novelty_contributes_positively_and_relevance_does_not_dominate(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    _insert_source(db_path, "src")
    user_id = _make_user(db_path, "alice")

    # Valued history points the taste vector toward [1, 0].
    history = _insert_article(db_path, "src", "history", embedding=[1.0, 0.0])
    _set_state(db_path, user_id, history, state="done", starred=True)

    # A surprising, high-quality, fresh candidate dissimilar to the user's taste.
    surprising = _insert_article(
        db_path,
        "src",
        "surprising",
        importance=95,
        discovered_at=_hours_ago(2),
        embedding=[0.0, 1.0],
    )

    recompute_user_recommendations(user_id, db_path=db_path)
    signals = _signals(db_path, user_id, surprising)

    # Novelty fires for the dissimilar-but-plausible article, giving it a lift
    # that pure semantic relevance (which would score this 0) never would.
    assert signals["novelty_adjustment"] > 0.0
    assert signals["semantic_adjustment"] == pytest.approx(0.0)


def test_low_signal_articles_remain_visible(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    _insert_source(db_path, "src")
    user_id = _make_user(db_path, "alice")

    # A low-importance, stale, no-embedding article still gets scored and stored.
    low = _insert_article(
        db_path, "src", "low", importance=1, discovered_at="2026-01-01T00:00:00+00:00"
    )

    assert recompute_user_recommendations(user_id, db_path=db_path) >= 1
    signals = _signals(db_path, user_id, low)
    assert signals["recommendation_score"] >= 0.0
