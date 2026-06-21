from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import pytest

import news_dashboard.db as db_mod
import news_dashboard.embeddings as embeddings_mod
from news_dashboard.db import connect, init_db
from news_dashboard.embeddings import embedding_text, ensure_article_embedded
from news_dashboard.recommendations import (
    SEMANTIC_SCORE_SPAN,
    build_semantic_profile,
    recompute_user_recommendations,
    semantic_adjustment,
)

pytestmark = pytest.mark.postgres


# ── Pure semantic logic (no database) ─────────────────────────────────────────


def test_embedding_text_combines_fields_and_drops_blanks() -> None:
    assert embedding_text("Title", "Summary", "Reason", "tag1,tag2") == (
        "Title Summary Reason tag1,tag2"
    )
    # Missing fields are skipped rather than leaving stray whitespace.
    assert embedding_text("Title", "", None, "  ") == "Title"
    assert embedding_text(None, None, None, None) == ""


def test_build_semantic_profile_averages_vectors() -> None:
    profile = build_semantic_profile([[1.0, 0.0], [0.0, 1.0]])
    assert profile == [0.5, 0.5]


def test_build_semantic_profile_returns_none_without_vectors() -> None:
    assert build_semantic_profile([]) is None
    assert build_semantic_profile([[]]) is None


def test_semantic_adjustment_rewards_similarity() -> None:
    profile = [1.0, 0.0]
    aligned = semantic_adjustment([1.0, 0.0], profile)
    orthogonal = semantic_adjustment([0.0, 1.0], profile)
    assert aligned == pytest.approx(SEMANTIC_SCORE_SPAN)
    assert orthogonal == pytest.approx(0.0)
    assert aligned > orthogonal


def test_semantic_adjustment_degrades_when_vectors_missing() -> None:
    assert semantic_adjustment(None, [1.0, 0.0]) == 0.0
    assert semantic_adjustment([1.0, 0.0], None) == 0.0
    # Mismatched dimensions are treated as unavailable rather than crashing.
    assert semantic_adjustment([1.0, 0.0, 0.0], [1.0, 0.0]) == 0.0


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
                "2026-06-21T10:00:00+00:00",
                blob,
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


def test_semantic_lift_raises_similar_articles(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "semantic-lift.db")
    _insert_source(db_path, "src", category="tech", priority=50)
    user_id = _make_user(db_path, "alice")

    # Valued history points the taste vector toward [1, 0].
    history = _insert_article(db_path, "src", "history", embedding=[1.0, 0.0])
    _set_state(db_path, user_id, history, state="done", starred=True)

    # Two fresh candidates, identical except for their embeddings.
    similar = _insert_article(db_path, "src", "similar", embedding=[0.95, 0.05])
    different = _insert_article(db_path, "src", "different", embedding=[0.0, 1.0])

    recompute_user_recommendations(user_id, db_path=db_path)

    assert _persisted_score(db_path, user_id, similar) > _persisted_score(
        db_path, user_id, different
    )


def test_missing_candidate_embedding_falls_back_to_non_semantic(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "missing-embed.db")
    _insert_source(db_path, "src", category="tech", priority=50)
    user_id = _make_user(db_path, "alice")

    history = _insert_article(db_path, "src", "history", embedding=[1.0, 0.0])
    _set_state(db_path, user_id, history, state="done", starred=True)

    # Candidate has no embedding → semantic lift is skipped, score == cold start.
    candidate = _insert_article(db_path, "src", "no-embed", embedding=None)

    recompute_user_recommendations(user_id, db_path=db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT recommendation_score, signals"
            " FROM user_article_recommendations WHERE user_id = %s AND article_id = %s",
            (user_id, candidate),
        ).fetchone()
    assert row is not None
    # No embedding on the candidate → semantic lift contributes nothing; the
    # rest of the (behavioral + cold-start) score is still computed normally.
    assert row["signals"]["semantic_adjustment"] == pytest.approx(0.0)


def test_recompute_survives_unavailable_embedding_generation(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "embed-down.db")
    _insert_source(db_path, "src", category="tech", priority=50)
    user_id = _make_user(db_path, "alice")

    # The embedding service is down: any generation attempt raises.
    def _boom(_text: str) -> list[float]:
        message = "embedding service unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(embeddings_mod, "_embed", _boom)

    history = _insert_article(db_path, "src", "history", embedding=None)
    _set_state(db_path, user_id, history, state="done", starred=True)
    candidate = _insert_article(db_path, "src", "candidate", embedding=None)

    # Failed generation surfaces to callers (which wrap it in try/except)...
    with pytest.raises(RuntimeError):
        ensure_article_embedded(history, db_path)

    # ...and recompute still produces scores with no embeddings present.
    assert recompute_user_recommendations(user_id, db_path=db_path) >= 1
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT model_version FROM user_article_recommendations"
            " WHERE user_id = %s AND article_id = %s",
            (user_id, candidate),
        ).fetchone()
    assert row is not None
    # No embedded history → behavioral (non-semantic) model version.
    assert row["model_version"] == "behavioral-affinity-v1"


def test_semantic_scoring_is_isolated_per_user(
    tmp_path: Path, monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(tmp_path, monkeypatch, pg_clean, "semantic-isolated.db")
    _insert_source(db_path, "src", category="tech", priority=50)
    alice = _make_user(db_path, "alice")
    bob = _make_user(db_path, "bob")

    # Alice's taste points toward [1, 0]; Bob's toward [0, 1].
    a_hist = _insert_article(db_path, "src", "a-hist", embedding=[1.0, 0.0])
    b_hist = _insert_article(db_path, "src", "b-hist", embedding=[0.0, 1.0])
    _set_state(db_path, alice, a_hist, state="done", starred=True)
    _set_state(db_path, bob, b_hist, state="done", starred=True)

    cand_x = _insert_article(db_path, "src", "cand-x", embedding=[1.0, 0.0])
    cand_y = _insert_article(db_path, "src", "cand-y", embedding=[0.0, 1.0])

    recompute_user_recommendations(alice, db_path=db_path)
    recompute_user_recommendations(bob, db_path=db_path)

    # Each user ranks the candidate matching their own history higher.
    assert _persisted_score(db_path, alice, cand_x) > _persisted_score(db_path, alice, cand_y)
    assert _persisted_score(db_path, bob, cand_y) > _persisted_score(db_path, bob, cand_x)
