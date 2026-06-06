from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row

POSTGRES_PREFIXES = ("postgres://", "postgresql://")

POSTGRES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS sources (
      slug TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      url TEXT NOT NULL,
      category TEXT NOT NULL,
      kind TEXT NOT NULL,
      priority INTEGER NOT NULL DEFAULT 50,
      enabled INTEGER NOT NULL DEFAULT 1,
      last_checked_at TEXT,
      last_success_at TEXT,
      last_error TEXT,
      last_fetched_count INTEGER NOT NULL DEFAULT 0,
      last_inserted_count INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS articles (
      id BIGSERIAL PRIMARY KEY,
      url TEXT NOT NULL UNIQUE,
      canonical_url TEXT NOT NULL,
      title TEXT NOT NULL,
      source_slug TEXT NOT NULL REFERENCES sources(slug),
      source_name TEXT NOT NULL,
      category TEXT NOT NULL,
      kind TEXT NOT NULL,
      published_at TEXT,
      discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','read','saved','skipped','archived')),
      importance_score INTEGER NOT NULL DEFAULT 50,
      summary TEXT NOT NULL DEFAULT '',
      reason TEXT NOT NULL DEFAULT '',
      tags TEXT NOT NULL DEFAULT '',
      read_at TEXT,
      saved_at TEXT,
      skipped_at TEXT,
      archived_at TEXT,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_success_at TEXT",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_error TEXT",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_fetched_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_inserted_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS canonical_id BIGINT REFERENCES articles(id)",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding BYTEA",
    """
    ALTER TABLE articles ADD COLUMN IF NOT EXISTS fts_vector tsvector
      GENERATED ALWAYS AS (
        to_tsvector(
          'english',
          coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(tags,'')
        )
      ) STORED
    """,
    "CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)",
    "CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)",
    "CREATE INDEX IF NOT EXISTS idx_articles_discovered ON articles(discovered_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_slug)",
    "CREATE INDEX IF NOT EXISTS idx_articles_fts ON articles USING gin(fts_vector)",
]

INSERT_ARTICLE_SQL = """
    INSERT INTO articles(
      url, canonical_url, title, source_slug, source_name, category, kind,
      published_at, summary, reason, importance_score, tags
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (url) DO NOTHING
    """

INSERT_DUPLICATE_ARTICLE_SQL = """
    INSERT INTO articles(
      url, canonical_url, title, source_slug, source_name, category, kind,
      published_at, summary, reason, importance_score, tags,
      status, canonical_id
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'archived', %s)
    ON CONFLICT (url) DO NOTHING
    """


def active_database_url(database_url: str | None = None) -> str:
    if database_url:
        url = database_url
    elif os.getenv("DATABASE_URL"):
        url = os.environ["DATABASE_URL"]
    else:
        host = os.getenv("POSTGRES_HOST")
        if not host:
            raise RuntimeError("Postgres is required. Set DATABASE_URL or POSTGRES_HOST.")

        user = os.getenv("POSTGRES_USER", "news_dashboard")
        password = os.getenv("POSTGRES_PASSWORD", "")
        database = os.getenv("POSTGRES_DB", "news_dashboard")
        port = os.getenv("POSTGRES_PORT", "5432")
        url = f"postgresql://{user}:{password}@{host}:{port}/{database}"

    if not url.startswith(POSTGRES_PREFIXES):
        raise RuntimeError("Postgres is required. DATABASE_URL must start with postgresql:// or postgres://.")
    return url


def describe_database(db_path: Path | None = None, database_url: str | None = None) -> str:
    del db_path
    url = active_database_url(database_url)
    parts = urlsplit(url)
    if parts.password:
        host = parts.hostname or ""
        netloc = f"{parts.username}:***@{host}"
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return url


@contextmanager
def connect(db_path: Path | None = None, database_url: str | None = None) -> Iterator[Any]:
    del db_path
    conn = psycopg.connect(active_database_url(database_url), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None, database_url: str | None = None) -> None:
    del db_path
    with connect(database_url=database_url) as conn:
        for statement in POSTGRES_SCHEMA:
            conn.execute(statement)


def row_to_dict(row: Any) -> dict:
    return dict(row)


def insert_article_sql() -> str:
    return INSERT_ARTICLE_SQL


def insert_duplicate_article_sql() -> str:
    return INSERT_DUPLICATE_ARTICLE_SQL


def search_articles_sql(terms: list[str], limit: int) -> tuple[str, list[Any]]:
    if not terms:
        return "SELECT * FROM articles ORDER BY discovered_at DESC LIMIT %s", [limit]

    clauses = []
    params: list[Any] = []
    for term in terms:
        like = f"%{term}%"
        clauses.append(
            "(title ILIKE %s OR summary ILIKE %s OR tags ILIKE %s OR source_name ILIKE %s OR reason ILIKE %s)"
        )
        params.extend([like, like, like, like, like])

    params.append(limit)
    where = " AND ".join(clauses)
    return f"SELECT * FROM articles WHERE {where} ORDER BY importance_score DESC, discovered_at DESC LIMIT %s", params
