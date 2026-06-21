from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import news_dashboard.db as db_mod
from news_dashboard.db import connect, init_db
from news_dashboard.recommendations import (
    AFFINITY_SCORE_SPAN,
    ArticleSignal,
    build_affinity_profile,
    parse_tags,
    recompute_user_recommendations,
    score_article,
)

pytestmark = pytest.mark.postgres


# ── Pure scoring logic (no database) ──────────────────────────────────────────


def test_parse_tags_normalizes_and_drops_empties() -> None:
    assert parse_tags(" Agents, LLM ,, python ") == ("agents", "llm", "python")
    assert parse_tags(None) == ()
    assert parse_tags("") == ()


def test_starred_is_strongest_positive_signal() -> None:
    starred = ArticleSignal(state="today", starred=True, source_slug="s")
    done = ArticleSignal(state="done", starred=False, source_slug="s")
    later = ArticleSignal(state="later", starred=False, source_slug="s")
    assert starred.weight > done.weight > 0.0
    assert later.weight == 0.0


def test_positive_signals_raise_and_negative_signals_lower_scores() -> None:
    liked = build_affinity_profile(
        [
            ArticleSignal(state="done", starred=True, source_slug="good", category="ai"),
            ArticleSignal(state="done", starred=False, source_slug="good", category="ai"),
        ]
    )
    disliked = build_affinity_profile(
        [
            ArticleSignal(state="skipped", starred=False, source_slug="bad", category="crypto"),
            ArticleSignal(state="archived", starred=False, source_slug="bad", category="crypto"),
        ]
    )
    base = 50.0
    assert score_article(base, source_slug="good", category="ai", tags=(), profile=liked) > base
    assert (
        score_article(base, source_slug="bad", category="crypto", tags=(), profile=disliked) < base
    )


def test_later_is_neutral_not_negative() -> None:
    profile = build_affinity_profile(
        [
            ArticleSignal(state="later", starred=False, source_slug="src", category="ai"),
            ArticleSignal(state="later", starred=False, source_slug="src", category="ai"),
        ]
    )
    base = 50.0
    assert score_article(base, source_slug="src", category="ai", tags=(), profile=profile) == base


def test_source_category_and_topic_affinities_each_influence_score() -> None:
    profile = build_affinity_profile(
        [
            ArticleSignal(
                state="done",
                starred=True,
                source_slug="src",
                category="ai",
                tags=("agents",),
            )
        ]
        * 3
    )
    assert profile.adjustment("src", None, ()) > 0  # source alone
    assert profile.adjustment("other", "ai", ()) > 0  # category alone
    assert profile.adjustment("other", None, ("agents",)) > 0  # topic alone


def test_strong_article_from_disliked_source_can_still_rise() -> None:
    """A bounded penalty means a high-base article isn't gated out by source."""
    disliked = build_affinity_profile(
        [ArticleSignal(state="skipped", starred=False, source_slug="noisy")] * 50
    )
    strong_from_noisy = score_article(
        95.0, source_slug="noisy", category=None, tags=(), profile=disliked
    )
    weak_from_neutral = score_article(
        40.0, source_slug="neutral", category=None, tags=(), profile=disliked
    )
    assert strong_from_noisy >= 95.0 - AFFINITY_SCORE_SPAN
    assert strong_from_noisy > weak_from_neutral


def test_scores_are_clamped_to_unit_range() -> None:
    liked = build_affinity_profile(
        [ArticleSignal(state="done", starred=True, source_slug="src")] * 10
    )
    assert score_article(99.0, source_slug="src", category=None, tags=(), profile=liked) <= 100.0
    disliked = build_affinity_profile(
        [ArticleSignal(state="skipped", starred=False, source_slug="src")] * 10
    )
    assert score_article(1.0, source_slug="src", category=None, tags=(), profile=disliked) >= 0.0


# ── Database-backed recompute ─────────────────────────────────────────────────


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
    tags: str = "",
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
                "2026-06-21T10:00:00+00:00",
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _set_state(
    db_path: Path, user_id: int, article_id: int, *, state: str, starred: bool = False
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


def _persisted_score(db_path: Path, user_id: int, article_id: int) -> float:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT recommendation_score FROM user_article_recommendations"
            " WHERE user_id = %s AND article_id = %s",
            (user_id, article_id),
        ).fetchone()
    assert row is not None
    return float(row["recommendation_score"])


def test_recompute_persists_affinity_adjusted_scores(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "recompute.db")
    _insert_source(db_path, "loved", category="ai", priority=50)
    _insert_source(db_path, "hated", category="crypto", priority=50)
    user_id = _make_user(db_path, "alice")

    # History: star/done on the loved source, skip/archive on the hated one.
    for i in range(3):
        liked = _insert_article(db_path, "loved", f"liked-{i}", category="ai")
        _set_state(db_path, user_id, liked, state="done", starred=True)
        disliked = _insert_article(db_path, "hated", f"disliked-{i}", category="crypto")
        _set_state(db_path, user_id, disliked, state="skipped")

    # Two fresh candidates with identical base, differing only by source/category.
    good = _insert_article(db_path, "loved", "candidate-good", category="ai")
    bad = _insert_article(db_path, "hated", "candidate-bad", category="crypto")

    count = recompute_user_recommendations(user_id, db_path=db_path)
    assert count >= 2
    assert _persisted_score(db_path, user_id, good) > _persisted_score(db_path, user_id, bad)


def test_recompute_is_isolated_per_user(tmp_path: Path, monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "isolated.db")
    _insert_source(db_path, "src-a", category="ai")
    _insert_source(db_path, "src-b", category="crypto")
    alice = _make_user(db_path, "alice")
    bob = _make_user(db_path, "bob")

    for i in range(3):
        a = _insert_article(db_path, "src-a", f"a-{i}", category="ai")
        b = _insert_article(db_path, "src-b", f"b-{i}", category="crypto")
        # Alice likes A, dislikes B; Bob does the opposite.
        _set_state(db_path, alice, a, state="done", starred=True)
        _set_state(db_path, alice, b, state="skipped")
        _set_state(db_path, bob, b, state="done", starred=True)
        _set_state(db_path, bob, a, state="skipped")

    cand_a = _insert_article(db_path, "src-a", "cand-a", category="ai")
    cand_b = _insert_article(db_path, "src-b", "cand-b", category="crypto")

    recompute_user_recommendations(alice, db_path=db_path)
    recompute_user_recommendations(bob, db_path=db_path)

    assert _persisted_score(db_path, alice, cand_a) > _persisted_score(db_path, alice, cand_b)
    assert _persisted_score(db_path, bob, cand_b) > _persisted_score(db_path, bob, cand_a)


def test_recompute_with_no_history_keeps_base_scores(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "no-history.db")
    _insert_source(db_path, "src", category="ai")
    user_id = _make_user(db_path, "alice")
    article = _insert_article(db_path, "src", "only", category="ai")

    assert recompute_user_recommendations(user_id, db_path=db_path) == 1
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT recommendation_score, cold_start_score"
            " FROM user_article_recommendations WHERE user_id = %s AND article_id = %s",
            (user_id, article),
        ).fetchone()
    assert row is not None
    # No interactions → affinity profile is empty → score equals the cold-start base.
    assert float(row["recommendation_score"]) == pytest.approx(float(row["cold_start_score"]))
