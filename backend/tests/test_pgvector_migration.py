"""pgvector migration (issue #924): extension setup, BLOB backfill, SQL top-k."""

from __future__ import annotations

import math
import struct
from pathlib import Path

import pytest

from news_dashboard.db import EMBEDDING_DIMENSIONS, _backfill_embedding_vectors, connect, init_db
from news_dashboard.embeddings import parse_vector, vector_literal

pytestmark = pytest.mark.postgres


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b)


def _padded(vec: list[float]) -> list[float]:
    return vec + [0.0] * (EMBEDDING_DIMENSIONS - len(vec))


def _seed_source(db_path: Path, slug: str = "src") -> None:
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, 'tech', 'rss_feed', 50, TRUE)
            ON CONFLICT(slug) DO NOTHING
            """,
            (slug, slug.title(), f"https://example.com/{slug}.xml"),
        )


def test_vector_extension_is_available(tmp_path: Path) -> None:
    """init_db's `CREATE EXTENSION IF NOT EXISTS vector` statement succeeded."""
    db_path = tmp_path / "ext.db"
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()
    assert row is not None


def test_embedding_vec_has_hnsw_cosine_index(tmp_path: Path) -> None:
    db_path = tmp_path / "idx.db"
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'articles' AND indexname = 'idx_articles_embedding_vec_hnsw'
            """
        ).fetchone()
    assert row is not None


def test_legacy_blob_column_is_dropped_after_migration(tmp_path: Path) -> None:
    """init_db drops the pre-pgvector BLOB column once backfilled."""
    db_path = tmp_path / "dropped.db"
    init_db(db_path)
    with connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'articles' AND column_name = 'embedding'
            """
        ).fetchone()
    assert row is None


def test_backfill_migrates_legacy_blob_embeddings_losslessly(tmp_path: Path) -> None:
    """Upgrading a pre-pgvector database backfills BLOB embeddings into
    embedding_vec with the same nearest-neighbor ordering as before, and the
    backfill is idempotent (a second pass has nothing left to do).
    """
    db_path = tmp_path / "backfill.db"
    init_db(db_path)
    _seed_source(db_path)

    # Reproduce a not-yet-migrated database: re-add the legacy BLOB column
    # init_db already dropped, and seed it directly (bypassing embedding_vec).
    with connect(db_path) as conn:
        conn.execute("ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding BYTEA")

    vectors = {1: [1.0, 0.0, 0.0], 2: [0.9, 0.1, 0.0], 3: [0.0, 1.0, 0.0]}
    with connect(db_path) as conn:
        for article_id, vec in vectors.items():
            blob = struct.pack(f"{EMBEDDING_DIMENSIONS}f", *_padded(vec))
            conn.execute(
                """
                INSERT INTO articles(
                  id, url, canonical_url, title, source_slug, source_name,
                  category, kind, importance_score, discovered_at, embedding
                ) VALUES (%s, %s, %s, %s, 'src', 'Src', 'tech', 'rss_feed', 50,
                  '2026-06-21T10:00:00+00:00', %s)
                """,
                (
                    article_id,
                    f"https://example.com/{article_id}",
                    f"https://example.com/{article_id}",
                    f"Article {article_id}",
                    blob,
                ),
            )

    backfilled = _backfill_embedding_vectors(db_path, None)
    assert backfilled == len(vectors)

    with connect(db_path) as conn:
        rows = conn.execute("SELECT id, embedding_vec FROM articles ORDER BY id").fetchall()
    got = {row["id"]: parse_vector(row["embedding_vec"]) for row in rows}

    for article_id, original in vectors.items():
        assert _cosine(got[article_id], _padded(original)) == pytest.approx(1.0, abs=1e-4)

    # Nearest-neighbor ordering is preserved: article 2 is closer to 1 than 3 is.
    assert _cosine(got[1], got[2]) > _cosine(got[1], got[3])

    # Nothing left to backfill on a second pass.
    assert _backfill_embedding_vectors(db_path, None) == 0


def test_sql_topk_orders_candidates_by_cosine_distance(tmp_path: Path) -> None:
    """The pgvector `<=>` operator ranks nearest-first directly in SQL —
    the retrieval path embeddings.ask() relies on for top-k, with no
    full-table Python cosine loop.
    """
    db_path = tmp_path / "topk.db"
    init_db(db_path)
    _seed_source(db_path)

    vectors = {1: [1.0, 0.0], 2: [0.9, 0.1], 3: [0.0, 1.0]}
    with connect(db_path) as conn:
        for article_id, vec in vectors.items():
            conn.execute(
                """
                INSERT INTO articles(
                  id, url, canonical_url, title, source_slug, source_name,
                  category, kind, importance_score, discovered_at, embedding_vec
                ) VALUES (%s, %s, %s, %s, 'src', 'Src', 'tech', 'rss_feed', 50,
                  '2026-06-21T10:00:00+00:00', %s::vector)
                """,
                (
                    article_id,
                    f"https://example.com/{article_id}",
                    f"https://example.com/{article_id}",
                    f"Article {article_id}",
                    vector_literal(_padded(vec)),
                ),
            )

        query_vec = vector_literal(_padded([1.0, 0.0]))
        rows = conn.execute(
            "SELECT id FROM articles ORDER BY embedding_vec <=> %s::vector LIMIT 2",
            (query_vec,),
        ).fetchall()

    assert [row["id"] for row in rows] == [1, 2]
