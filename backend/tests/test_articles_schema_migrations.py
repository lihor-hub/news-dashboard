"""PostgreSQL regression tests for the physical ``articles`` schema."""

from __future__ import annotations

import struct

import pytest
from psycopg import sql

from news_dashboard.db import _INITIALIZED_DATABASES, EMBEDDING_DIMENSIONS, connect, init_db
from news_dashboard.embeddings import parse_vector

pytestmark = pytest.mark.postgres

_EXPECTED_ARTICLE_INDEXES = {
    "articles_pkey",
    "articles_url_key",
    "idx_articles_category",
    "idx_articles_category_discovered_id",
    "idx_articles_discovered",
    "idx_articles_embedding_vec_hnsw",
    "idx_articles_search",
    "idx_articles_source",
    "idx_articles_starred",
    "idx_articles_state",
    "idx_articles_state_discovered_id",
    "idx_articles_status",
    "idx_articles_visible_discovered_id",
}
_EXPECTED_ARTICLE_CONSTRAINTS = {
    ("articles_canonical_id_fkey", "f"),
    ("articles_pkey", "p"),
    ("articles_source_slug_fkey", "f"),
    ("articles_status_check", "c"),
    ("articles_url_key", "u"),
}


def _reset_schema(database_url: str) -> None:
    """Remove tables from the isolated ``pg_clean`` schema for a clean replay."""
    with connect(database_url=database_url) as conn:
        tables = conn.execute(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = current_schema()
            """
        ).fetchall()
        for table in tables:
            conn.execute(
                sql.SQL("DROP TABLE {} CASCADE").format(sql.Identifier(table["tablename"]))
            )
    _INITIALIZED_DATABASES.clear()


def _article_attribute_counts(database_url: str) -> tuple[int, int]:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE NOT attribute.attisdropped) AS live,
              COUNT(*) FILTER (WHERE attribute.attisdropped) AS dropped
            FROM pg_attribute AS attribute
            JOIN pg_class AS relation ON relation.oid = attribute.attrelid
            JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = current_schema()
              AND relation.relname = 'articles'
              AND attribute.attnum > 0
            """
        ).fetchone()

    assert row is not None
    return int(row["live"]), int(row["dropped"])


def test_clean_schema_has_no_dropped_article_attributes(pg_clean: str) -> None:
    """A clean full-chain replay must not spend attributes on legacy columns."""
    _reset_schema(pg_clean)

    init_db(database_url=pg_clean)

    assert _article_attribute_counts(pg_clean) == (37, 0)
    with connect(database_url=pg_clean) as conn:
        legacy_columns = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'articles'
              AND column_name IN ('embedding', 'fts_vector')
            """
        ).fetchall()

    assert legacy_columns == []


def test_pre_fix_schema_upgrade_is_lossless_and_stops_attribute_churn(pg_clean: str) -> None:
    """Upgrade the pre-fix shape, then prove a restart cannot add tombstones."""
    _reset_schema(pg_clean)
    init_db(database_url=pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            ALTER TABLE articles ADD COLUMN embedding BYTEA;
            ALTER TABLE articles ADD COLUMN fts_vector tsvector
              GENERATED ALWAYS AS (
                to_tsvector(
                  'english',
                  coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' ||
                  coalesce(tags, '')
                )
              ) STORED;
            CREATE INDEX idx_articles_fts ON articles USING gin(fts_vector)
            """
        )
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind)
            VALUES ('source', 'Source', 'https://example.com/feed', 'tech', 'rss_feed')
            """
        )
        embedding = struct.pack(
            f"{EMBEDDING_DIMENSIONS}f", 1.0, *([0.0] * (EMBEDDING_DIMENSIONS - 1))
        )
        conn.execute(
            """
            INSERT INTO articles(
              url, canonical_url, title, source_slug, source_name, category, kind, embedding
            ) VALUES (
              'https://example.com/article', 'https://example.com/article', 'Kept article',
              'source', 'Source', 'tech', 'rss_feed', %s
            )
            """,
            (embedding,),
        )
        conn.execute("CREATE TABLE articles_old AS TABLE articles")

    _INITIALIZED_DATABASES.clear()
    init_db(database_url=pg_clean)

    assert _article_attribute_counts(pg_clean) == (37, 2)
    with connect(database_url=pg_clean) as conn:
        article = conn.execute(
            "SELECT title, embedding_vec FROM articles WHERE url = %s",
            ("https://example.com/article",),
        ).fetchone()
        rollback_count = conn.execute("SELECT COUNT(*) AS count FROM articles_old").fetchone()
        index_names = {
            row["indexname"]
            for row in conn.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = current_schema() AND tablename = 'articles'
                """
            ).fetchall()
        }
        constraints = {
            (row["conname"], row["contype"])
            for row in conn.execute(
                """
                SELECT conname, contype
                FROM pg_constraint
                WHERE conrelid = 'articles'::regclass
                """
            ).fetchall()
        }

    assert article is not None
    vector = parse_vector(article["embedding_vec"])
    assert article["title"] == "Kept article"
    assert len(vector) == EMBEDDING_DIMENSIONS
    assert vector[0] == 1.0
    assert vector[1:] == [0.0] * (EMBEDDING_DIMENSIONS - 1)
    assert rollback_count == {"count": 1}
    assert index_names == _EXPECTED_ARTICLE_INDEXES
    assert constraints == _EXPECTED_ARTICLE_CONSTRAINTS

    _INITIALIZED_DATABASES.clear()
    init_db(database_url=pg_clean)

    assert _article_attribute_counts(pg_clean) == (37, 2)
