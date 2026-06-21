from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import news_dashboard.db as db_mod
import news_dashboard.recommendation_jobs as jobs
from news_dashboard.db import connect, init_db
from news_dashboard.ingest import list_articles, transition_article_state
from news_dashboard.recommendation_jobs import (
    find_recalculation_candidates,
    recalculate_stale_recommendations,
    recommendation_health,
)

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


def _insert_article(db_path: Path, slug: str, suffix: str, *, category: str = "tech") -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, state, importance_score, tags, discovered_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'rss_feed', 'today', 50, '', %s)
            RETURNING id
            """,
            (
                f"https://example.com/articles/{suffix}",
                f"https://example.com/articles/{suffix}",
                f"Article {suffix}",
                slug,
                slug.title(),
                category,
                "2026-06-21T10:00:00+00:00",
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _set_state(db_path: Path, user_id: int, article_id: int, *, state: str) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state)
            VALUES (%s, %s, %s)
            ON CONFLICT(user_id, article_id) DO UPDATE SET state = excluded.state
            """,
            (user_id, article_id, state),
        )


def _insert_rec(
    db_path: Path,
    user_id: int,
    article_id: int,
    *,
    score: float = 10.0,
    model_version: str = "behavioral-affinity-v1",
    stale: bool = False,
) -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_article_recommendations(
              user_id, article_id, recommendation_score, model_version, stale
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, article_id, score, model_version, stale),
        )


def _rec_row(db_path: Path, user_id: int, article_id: int) -> dict[str, Any] | None:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT recommendation_score, model_version, stale"
            " FROM user_article_recommendations WHERE user_id = %s AND article_id = %s",
            (user_id, article_id),
        ).fetchone()
    return dict(row) if row is not None else None


# ── Stale / missing / superseded repair ───────────────────────────────────────


def test_stale_score_is_recalculated_and_cleared(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "stale.db")
    _insert_source(db_path, "src", category="ai")
    user_id = _make_user(db_path, "alice")
    article = _insert_article(db_path, "src", "a", category="ai")
    _insert_rec(db_path, user_id, article, score=1.0, stale=True)

    assert user_id in find_recalculation_candidates(db_path=db_path)
    summary = recalculate_stale_recommendations(db_path=db_path)
    assert summary.users_recalculated == 1

    row = _rec_row(db_path, user_id, article)
    assert row is not None
    assert row["stale"] is False
    # Cold-start base for a priority-50 source is well above the stub 1.0 score.
    assert row["recommendation_score"] != pytest.approx(1.0)


def test_missing_score_is_created(tmp_path: Path, monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "missing.db")
    _insert_source(db_path, "src", category="ai")
    user_id = _make_user(db_path, "alice")
    article = _insert_article(db_path, "src", "a", category="ai")

    assert _rec_row(db_path, user_id, article) is None
    assert user_id in find_recalculation_candidates(db_path=db_path)

    summary = recalculate_stale_recommendations(db_path=db_path)
    assert summary.scores_written >= 1
    assert _rec_row(db_path, user_id, article) is not None


def test_superseded_model_version_is_repaired(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "superseded.db")
    _insert_source(db_path, "src", category="ai")
    user_id = _make_user(db_path, "alice")
    article = _insert_article(db_path, "src", "a", category="ai")
    # An old formula/embedding scheme persisted this row; it is not stale-flagged
    # but its model_version is no longer current, so it must be repaired.
    _insert_rec(db_path, user_id, article, model_version="cold-start-v1", stale=False)

    assert user_id in find_recalculation_candidates(db_path=db_path)
    recalculate_stale_recommendations(db_path=db_path)

    row = _rec_row(db_path, user_id, article)
    assert row is not None
    assert row["model_version"] != "cold-start-v1"


# ── Failure fallback ──────────────────────────────────────────────────────────


def test_per_user_failure_does_not_abort_sweep(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "failure.db")
    _insert_source(db_path, "src", category="ai")
    alice = _make_user(db_path, "alice")
    bob = _make_user(db_path, "bob")
    art_a = _insert_article(db_path, "src", "a", category="ai")
    art_b = _insert_article(db_path, "src", "b", category="ai")
    _set_state(db_path, alice, art_a, state="today")
    _set_state(db_path, bob, art_b, state="today")

    from news_dashboard.recommendations import recompute_user_recommendations as real

    def flaky(user_id: int, **kwargs: Any) -> int:
        if user_id == alice:
            message = "transient scoring failure"
            raise RuntimeError(message)
        return real(user_id, **kwargs)

    monkeypatch.setattr(jobs, "recompute_user_recommendations", flaky)

    summary = recalculate_stale_recommendations(db_path=db_path)
    assert summary.users_failed == 1
    assert summary.users_recalculated == 1
    # Bob's score was still written despite Alice failing.
    assert _rec_row(db_path, bob, art_b) is not None


# ── Today read does not recompute synchronously ───────────────────────────────


def test_today_read_does_not_compute_scores(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "today-read.db")
    _insert_source(db_path, "src", category="ai")
    user_id = _make_user(db_path, "alice")
    article = _insert_article(db_path, "src", "a", category="ai")

    items = list_articles(state="today", user_id=user_id, db_path=db_path)
    assert any(item["id"] == article for item in items)

    # Reading Today must not synchronously materialize or recompute scores.
    assert _rec_row(db_path, user_id, article) is None


# ── Preference change marks scores stale ──────────────────────────────────────


def test_preference_change_marks_scores_stale(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "pref.db")
    _insert_source(db_path, "src", category="ai")
    user_id = _make_user(db_path, "alice")
    art_one = _insert_article(db_path, "src", "one", category="ai")
    art_two = _insert_article(db_path, "src", "two", category="ai")
    _insert_rec(db_path, user_id, art_one, stale=False)

    # Acting on a *different* article still reshapes the profile behind art_one.
    transition_article_state(art_two, "done", user_id=user_id, db_path=db_path)

    row = _rec_row(db_path, user_id, art_one)
    assert row is not None
    assert row["stale"] is True


# ── Observability ─────────────────────────────────────────────────────────────


def test_recommendation_health_reports_stale_and_missing(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "health.db")
    _insert_source(db_path, "src", category="ai")
    user_id = _make_user(db_path, "alice")
    scored = _insert_article(db_path, "src", "scored", category="ai")
    _insert_article(db_path, "src", "unscored", category="ai")
    _insert_rec(db_path, user_id, scored, stale=True)

    health = recommendation_health(db_path=db_path)
    assert health["total_scores"] == 1
    assert health["stale_scores"] == 1
    assert health["missing_scores"] >= 1
    assert health["by_model_version"]
