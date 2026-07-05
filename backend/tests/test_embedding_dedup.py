"""Tests for the post-ingest embedding-similarity dedup pass (embedding_dedup.py).

Covers:
- Merge above threshold: dissimilar titles, high cosine similarity -> canonical
  + archived duplicate with canonical_id set, also_from includes duplicate's source.
- No merge below threshold.
- No merge when either article already has a triaged (non-'today') per-user state.
- No merge across private-source visibility boundaries (different owners).
- Job no-ops (no error) without embedding credentials.

All embeddings are synthetic vectors written directly to the DB (via
embedding_vec::vector) — no OpenAI calls are made in these tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from news_dashboard.db import EMBEDDING_DIMENSIONS, connect
from news_dashboard.embedding_dedup import run_embedding_dedup
from news_dashboard.embeddings import vector_literal
from news_dashboard.ingest import _attach_also_from

# ── helpers ───────────────────────────────────────────────────────────────────


def _pack_vec(vec: list[float]) -> str:
    """Pad a short vector to the real embedding_vec(1536) width and format it."""
    return vector_literal(vec + [0.0] * (EMBEDDING_DIMENSIONS - len(vec)))


def _now_offset(hours: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _insert_user(pg_url: str, username: str) -> int:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, 'x') RETURNING id",
            (username,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_source(pg_url: str, slug: str, owner_user_id: int | None = None) -> None:
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, owner_user_id)
            VALUES (%s, %s, 'https://example.com', 'tech', 'rss_feed', %s)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug, owner_user_id),
        )


def _insert_article(
    pg_url: str,
    *,
    url: str,
    title: str,
    source_slug: str,
    embedding: list[float] | None,
    discovered_at: str,
) -> int:
    embedding_vec = _pack_vec(embedding) if embedding is not None else None
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name,
              category, kind, summary, embedding_vec, discovered_at
            )
            VALUES (
              %s, %s, %s, %s, %s, 'tech', 'rss_feed', %s, %s::vector, %s
            )
            RETURNING id
            """,
            (
                url,
                url,
                title,
                source_slug,
                source_slug,
                f"Summary for {title}",
                embedding_vec,
                discovered_at,
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _set_user_article_state(pg_url: str, user_id: int, article_id: int, state: str) -> None:
    with connect(database_url=pg_url) as conn:
        conn.execute(
            """
            INSERT INTO user_article_state(user_id, article_id, state)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, article_id) DO UPDATE SET state = excluded.state
            """,
            (user_id, article_id, state),
        )


def _get_article(pg_url: str, article_id: int) -> dict[str, Any]:
    with connect(database_url=pg_url) as conn:
        row = conn.execute(
            "SELECT * FROM articles WHERE id = %s",
            (article_id,),
        ).fetchone()
    assert row is not None
    return dict(row)


# A high-dimensional near-identical pair (cosine similarity ~1.0) and a
# clearly-dissimilar pair (orthogonal-ish, cosine similarity ~0.0).
_VEC_A = [1.0, 0.1, 0.0]
_VEC_A_NEAR = [0.99, 0.11, 0.01]  # cosine sim with _VEC_A is > 0.99
_VEC_B = [0.0, 0.0, 1.0]  # orthogonal to _VEC_A -> cosine sim ~0.0


@pytest.fixture(autouse=True)
def _embedding_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default all tests to "credentials configured" so the job actually runs.

    The dedicated inertness test explicitly unsets these.
    """
    monkeypatch.setenv("FREE_LLM_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


# ── merge above threshold ─────────────────────────────────────────────────────


def test_merges_dissimilar_titles_above_threshold(pg_clean: str) -> None:
    """Two articles with dissimilar titles but near-identical embeddings merge."""
    _insert_source(pg_clean, "vendor-blog")
    _insert_source(pg_clean, "hn-feed")

    older_id = _insert_article(
        pg_clean,
        url="https://vendor.example.com/post",
        title="Announcing Widget 3.0",
        source_slug="vendor-blog",
        embedding=_VEC_A,
        discovered_at=_now_offset(hours=2),
    )
    newer_id = _insert_article(
        pg_clean,
        url="https://news.ycombinator.com/item?id=123",
        title="Show HN: We just shipped something big",
        source_slug="hn-feed",
        embedding=_VEC_A_NEAR,
        discovered_at=_now_offset(hours=1),
    )

    summary = run_embedding_dedup(pg_clean)
    assert summary["merged"] == 1

    canonical = _get_article(pg_clean, older_id)
    dup = _get_article(pg_clean, newer_id)

    assert dup["canonical_id"] == older_id
    assert dup["state"] == "archived"
    assert dup["status"] == "archived"
    assert canonical["canonical_id"] is None
    assert canonical["state"] == "today"

    article: dict[str, Any] = {"id": older_id}
    with connect(database_url=pg_clean) as conn:
        _attach_also_from(conn, [article])
    assert "hn-feed" in article["also_from"]


# ── no merge below threshold ───────────────────────────────────────────────────


def test_does_not_merge_below_threshold(pg_clean: str) -> None:
    """Two articles with dissimilar embeddings are left alone."""
    _insert_source(pg_clean, "src-a")
    _insert_source(pg_clean, "src-b")

    id_a = _insert_article(
        pg_clean,
        url="https://a.example.com/story",
        title="Story A",
        source_slug="src-a",
        embedding=_VEC_A,
        discovered_at=_now_offset(hours=2),
    )
    id_b = _insert_article(
        pg_clean,
        url="https://b.example.com/story",
        title="Story B",
        source_slug="src-b",
        embedding=_VEC_B,
        discovered_at=_now_offset(hours=1),
    )

    summary = run_embedding_dedup(pg_clean)
    assert summary["merged"] == 0

    art_a = _get_article(pg_clean, id_a)
    art_b = _get_article(pg_clean, id_b)
    assert art_a["canonical_id"] is None
    assert art_b["canonical_id"] is None
    assert art_a["state"] == "today"
    assert art_b["state"] == "today"


# ── triaged-state protection ───────────────────────────────────────────────────


def test_does_not_merge_when_canonical_already_triaged(pg_clean: str) -> None:
    """If any user has triaged the would-be canonical, the pair is never merged."""
    uid = _insert_user(pg_clean, "triager")
    _insert_source(pg_clean, "vendor-blog")
    _insert_source(pg_clean, "hn-feed")

    older_id = _insert_article(
        pg_clean,
        url="https://vendor.example.com/post2",
        title="Announcing Widget 4.0",
        source_slug="vendor-blog",
        embedding=_VEC_A,
        discovered_at=_now_offset(hours=2),
    )
    newer_id = _insert_article(
        pg_clean,
        url="https://news.ycombinator.com/item?id=456",
        title="Show HN: Another big thing",
        source_slug="hn-feed",
        embedding=_VEC_A_NEAR,
        discovered_at=_now_offset(hours=1),
    )
    _set_user_article_state(pg_clean, uid, older_id, "done")

    summary = run_embedding_dedup(pg_clean)
    assert summary["merged"] == 0

    assert _get_article(pg_clean, older_id)["canonical_id"] is None
    assert _get_article(pg_clean, newer_id)["canonical_id"] is None


def test_does_not_merge_when_duplicate_already_triaged(pg_clean: str) -> None:
    """If any user has triaged the would-be duplicate, the pair is never merged."""
    uid = _insert_user(pg_clean, "triager2")
    _insert_source(pg_clean, "vendor-blog")
    _insert_source(pg_clean, "hn-feed")

    older_id = _insert_article(
        pg_clean,
        url="https://vendor.example.com/post3",
        title="Announcing Widget 5.0",
        source_slug="vendor-blog",
        embedding=_VEC_A,
        discovered_at=_now_offset(hours=2),
    )
    newer_id = _insert_article(
        pg_clean,
        url="https://news.ycombinator.com/item?id=789",
        title="Show HN: Yet another big thing",
        source_slug="hn-feed",
        embedding=_VEC_A_NEAR,
        discovered_at=_now_offset(hours=1),
    )
    _set_user_article_state(pg_clean, uid, newer_id, "skipped")

    summary = run_embedding_dedup(pg_clean)
    assert summary["merged"] == 0

    assert _get_article(pg_clean, older_id)["canonical_id"] is None
    assert _get_article(pg_clean, newer_id)["canonical_id"] is None


# ── private-source visibility isolation ────────────────────────────────────────


def test_does_not_merge_across_different_private_owners(pg_clean: str) -> None:
    """Private-source articles from two different users must never merge."""
    uid1 = _insert_user(pg_clean, "owner-one")
    uid2 = _insert_user(pg_clean, "owner-two")
    _insert_source(pg_clean, "owner-one-private", owner_user_id=uid1)
    _insert_source(pg_clean, "owner-two-private", owner_user_id=uid2)

    id1 = _insert_article(
        pg_clean,
        url="https://owner1.example.com/story",
        title="Owner One's Exclusive",
        source_slug="owner-one-private",
        embedding=_VEC_A,
        discovered_at=_now_offset(hours=2),
    )
    id2 = _insert_article(
        pg_clean,
        url="https://owner2.example.com/story",
        title="Owner Two's Scoop",
        source_slug="owner-two-private",
        embedding=_VEC_A_NEAR,
        discovered_at=_now_offset(hours=1),
    )

    summary = run_embedding_dedup(pg_clean)
    assert summary["merged"] == 0

    assert _get_article(pg_clean, id1)["canonical_id"] is None
    assert _get_article(pg_clean, id2)["canonical_id"] is None


def test_merges_private_source_against_global_canonical(pg_clean: str) -> None:
    """A private source may still merge against a global canonical article."""
    uid = _insert_user(pg_clean, "owner-three")
    _insert_source(pg_clean, "global-src")
    _insert_source(pg_clean, "owner-three-private", owner_user_id=uid)

    global_id = _insert_article(
        pg_clean,
        url="https://global.example.com/story",
        title="Global Coverage",
        source_slug="global-src",
        embedding=_VEC_A,
        discovered_at=_now_offset(hours=2),
    )
    private_id = _insert_article(
        pg_clean,
        url="https://private.example.com/story",
        title="My Private Take On This",
        source_slug="owner-three-private",
        embedding=_VEC_A_NEAR,
        discovered_at=_now_offset(hours=1),
    )

    summary = run_embedding_dedup(pg_clean)
    assert summary["merged"] == 1

    assert _get_article(pg_clean, private_id)["canonical_id"] == global_id
    assert _get_article(pg_clean, global_id)["canonical_id"] is None


# ── inertness without credentials ──────────────────────────────────────────────


def test_no_op_without_embedding_credentials(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """With no FREE_LLM_API_KEY/OPENAI_API_KEY, the job does nothing and logs nothing alarming."""
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    _insert_source(pg_clean, "vendor-blog")
    _insert_source(pg_clean, "hn-feed")
    older_id = _insert_article(
        pg_clean,
        url="https://vendor.example.com/post4",
        title="Announcing Widget 6.0",
        source_slug="vendor-blog",
        embedding=_VEC_A,
        discovered_at=_now_offset(hours=2),
    )
    newer_id = _insert_article(
        pg_clean,
        url="https://news.ycombinator.com/item?id=999",
        title="Show HN: Widget 6.0 discussion",
        source_slug="hn-feed",
        embedding=_VEC_A_NEAR,
        discovered_at=_now_offset(hours=1),
    )

    import logging

    with caplog.at_level(logging.INFO, logger="news_dashboard.embedding_dedup"):
        summary = run_embedding_dedup(pg_clean)

    assert summary == {"embedded": 0, "merged": 0}
    assert _get_article(pg_clean, older_id)["canonical_id"] is None
    assert _get_article(pg_clean, newer_id)["canonical_id"] is None
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)
