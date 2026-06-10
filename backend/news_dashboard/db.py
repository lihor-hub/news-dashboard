from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional unless DATABASE_URL is PostgreSQL
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]

DB_PATH = Path(os.getenv("NEWS_DASHBOARD_DB", "/data/news-dashboard.db"))
POSTGRES_PREFIXES = ("postgres:" + "//", "postgresql:" + "//")

logger = logging.getLogger(__name__)

SQLITE_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

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
);

CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
);

CREATE TABLE IF NOT EXISTS ingest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_ms INTEGER,
  total_new INTEGER,
  total_errors INTEGER
);

CREATE TABLE IF NOT EXISTS ingest_run_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER REFERENCES ingest_runs(id),
  source_name TEXT NOT NULL,
  articles_found INTEGER,
  articles_new INTEGER,
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_discovered ON articles(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_slug);

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
  title, summary, reason, tags, source_name,
  content=articles, content_rowid=id
);

CREATE TABLE IF NOT EXISTS ingest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  duration_ms INTEGER,
  total_new INTEGER,
  total_errors INTEGER
);

CREATE TABLE IF NOT EXISTS ingest_run_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER REFERENCES ingest_runs(id),
  source_name TEXT NOT NULL,
  articles_found INTEGER,
  articles_new INTEGER,
  error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingest_run_sources_source_run
  ON ingest_run_sources(source_name, run_id DESC);
CREATE INDEX IF NOT EXISTS idx_ingest_runs_started ON ingest_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_ingest_run_sources_run ON ingest_run_sources(run_id);
"""

# Additive columns to add when upgrading existing databases
SQLITE_COLUMN_MIGRATIONS = [
    ("sources", "last_success_at", "TEXT"),
    ("sources", "last_error", "TEXT"),
    ("sources", "last_fetched_count", "INTEGER NOT NULL DEFAULT 0"),
    ("sources", "last_inserted_count", "INTEGER NOT NULL DEFAULT 0"),
    ("articles", "canonical_id", "INTEGER REFERENCES articles(id)"),
    ("articles", "embedding", "BLOB"),
    ("articles", "body", "TEXT"),
    ("articles", "body_status", "TEXT NOT NULL DEFAULT 'missing'"),
    # #87 workflow state model
    ("articles", "state", "TEXT NOT NULL DEFAULT 'today'"),
    ("articles", "starred", "INTEGER NOT NULL DEFAULT 0"),
    ("articles", "done_at", "TEXT"),
    ("articles", "starred_at", "TEXT"),
    ("articles", "later_until", "TEXT"),
    ("articles", "restored_at", "TEXT"),
]

# Data-only migrations run after column additions (idempotent via WHERE guard)
SQLITE_DATA_MIGRATIONS = [
    # Migrate legacy status → state+starred (only touches rows that still need it)
    """UPDATE articles SET state = CASE status
         WHEN 'new'      THEN 'today'
         WHEN 'read'     THEN 'done'
         WHEN 'saved'    THEN 'today'
         WHEN 'skipped'  THEN 'skipped'
         WHEN 'archived' THEN 'archived'
         ELSE 'today'
       END
       WHERE state = 'today' AND status != 'new'""",
    "UPDATE articles SET starred = 1, starred_at = saved_at WHERE status = 'saved' AND starred = 0",
    (
        "UPDATE articles SET done_at = read_at"
        " WHERE status = 'read' AND done_at IS NULL AND read_at IS NOT NULL"
    ),
]

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
      status TEXT NOT NULL DEFAULT 'new'
        CHECK(status IN ('new','read','saved','skipped','archived')),
      importance_score INTEGER NOT NULL DEFAULT 50,
      summary TEXT NOT NULL DEFAULT '',
      reason TEXT NOT NULL DEFAULT '',
      tags TEXT NOT NULL DEFAULT '',
      read_at TEXT,
      saved_at TEXT,
      skipped_at TEXT,
      archived_at TEXT,
      embedding BYTEA,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)",
    "CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)",
    "CREATE INDEX IF NOT EXISTS idx_articles_discovered ON articles(discovered_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_slug)",
    """
    CREATE TABLE IF NOT EXISTS ingest_runs (
      id           SERIAL PRIMARY KEY,
      started_at   TIMESTAMPTZ NOT NULL,
      finished_at  TIMESTAMPTZ,
      duration_ms  INTEGER,
      total_new    INTEGER,
      total_errors INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingest_run_sources (
      id             SERIAL PRIMARY KEY,
      run_id         INTEGER REFERENCES ingest_runs(id),
      source_name    TEXT NOT NULL,
      articles_found INTEGER,
      articles_new   INTEGER,
      error_message  TEXT
    )
    """,
    # PostgreSQL FTS via tsvector — added as a generated column if not present
    """
    ALTER TABLE articles ADD COLUMN IF NOT EXISTS fts_vector tsvector
      GENERATED ALWAYS AS (
        to_tsvector(
          'english',
          coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(tags, '')
        )
      ) STORED
    """,
    "CREATE INDEX IF NOT EXISTS idx_articles_fts ON articles USING gin(fts_vector)",
    # Settings table for persistent configuration
    """
    CREATE TABLE IF NOT EXISTS settings (
      key   TEXT PRIMARY KEY,
      value TEXT NOT NULL
    )
    """,
    # Source health columns (safe to run repeatedly)
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_success_at TEXT",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_error TEXT",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_fetched_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_inserted_count INTEGER NOT NULL DEFAULT 0",
    # Deduplication column
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS canonical_id BIGINT REFERENCES articles(id)",
    # AI Q&A embeddings for saved/read article retrieval
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding BYTEA",
    # Full body text extracted on first reader open (#79)
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS body TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS body_status TEXT NOT NULL DEFAULT 'missing'",
    # #87 workflow state model: new columns + data migration from legacy status
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'today'",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS starred INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS done_at TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS starred_at TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS later_until TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS restored_at TEXT",
    # Migrate existing status values to state + starred
    """
    UPDATE articles SET state = CASE status
      WHEN 'new'      THEN 'today'
      WHEN 'read'     THEN 'done'
      WHEN 'saved'    THEN 'today'
      WHEN 'skipped'  THEN 'skipped'
      WHEN 'archived' THEN 'archived'
      ELSE 'today'
    END
    WHERE state = 'today' AND status != 'new'
    """,
    "UPDATE articles SET starred = 1, starred_at = saved_at WHERE status = 'saved' AND starred = 0",
    (
        "UPDATE articles SET done_at = read_at"
        " WHERE status = 'read' AND done_at IS NULL AND read_at IS NOT NULL"
    ),
    "CREATE INDEX IF NOT EXISTS idx_articles_state ON articles(state)",
    "CREATE INDEX IF NOT EXISTS idx_articles_starred ON articles(starred)",
    # Ingest run telemetry from issue #50. Stats endpoints read these tables.
    """
    CREATE INDEX IF NOT EXISTS idx_ingest_run_sources_source_run
      ON ingest_run_sources(source_name, run_id DESC)
    """,
    "CREATE INDEX IF NOT EXISTS idx_ingest_runs_started ON ingest_runs(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_ingest_run_sources_run ON ingest_run_sources(run_id)",
]


def _validate_postgres_url(url: str) -> str:
    if not url.startswith(POSTGRES_PREFIXES):
        message = f"DATABASE_URL must start with 'postgresql://' or 'postgres://'; got: {url!r}"
        raise RuntimeError(message)
    return url


def active_database_url(database_url: str | None = None) -> str:
    """Resolve the PostgreSQL DSN from arguments or environment variables."""
    if database_url is not None:
        return _validate_postgres_url(database_url)
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return _validate_postgres_url(env_url)
    host = os.getenv("POSTGRES_HOST")
    if not host:
        message = "Postgres is required: set DATABASE_URL or POSTGRES_HOST"
        raise RuntimeError(message)
    user = os.getenv("POSTGRES_USER", "news_dashboard")
    password = os.getenv("POSTGRES_PASSWORD", "")
    database = os.getenv("POSTGRES_DB", "news_dashboard")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def is_postgres(database_url: str | None = None) -> bool:
    try:
        url = active_database_url(database_url)
    except RuntimeError:
        return False
    return bool(url and url.startswith(POSTGRES_PREFIXES))


def describe_database(db_path: Path | None = None, database_url: str | None = None) -> str:
    url = active_database_url(database_url)
    if url:
        parts = urlsplit(url)
        if parts.password:
            host = parts.hostname or ""
            netloc = f"{parts.username}:***@{host}"
            if parts.port:
                netloc += f":{parts.port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        return url
    return str(db_path or DB_PATH)


class PostgresConnection:
    """Thin adapter exposing a sqlite3-like ``execute`` API over a psycopg connection."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> Any:
        return self.conn.execute(sql.replace("?", "%s"), params)

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


@contextmanager
def connect(db_path: Path | None = None, database_url: str | None = None) -> Iterator[Any]:
    try:
        url: str | None = active_database_url(database_url)
    except RuntimeError:
        url = None
    if url and url.startswith(POSTGRES_PREFIXES):
        # psycopg is an optional import; mypy sees it as always present
        if psycopg is None:
            message = "DATABASE_URL is PostgreSQL but psycopg is not installed"  # type: ignore[unreachable]
            raise RuntimeError(message)
        pg_conn = psycopg.connect(url, row_factory=dict_row)
        wrapped = PostgresConnection(pg_conn)
        try:
            yield wrapped
            wrapped.commit()
        finally:
            wrapped.close()
        return

    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _apply_sqlite_column_migrations(conn: Any) -> None:
    """Idempotently add new columns to existing SQLite databases."""
    for table, column, typedef in SQLITE_COLUMN_MIGRATIONS:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")
        except sqlite3.OperationalError:
            logger.debug("Column %s.%s already exists; skipping migration", table, column)


def _build_fts_index(conn: Any) -> None:
    """Populate FTS index from existing articles (safe to re-run)."""
    try:
        conn.execute("INSERT INTO articles_fts(articles_fts) VALUES('rebuild')")
    except sqlite3.OperationalError:
        logger.debug("FTS rebuild skipped: articles_fts not available")


def _apply_sqlite_data_migrations(conn: Any) -> None:
    """Idempotently run data-only migrations for SQLite (WHERE-guarded updates)."""
    for sql in SQLITE_DATA_MIGRATIONS:
        try:
            conn.execute(sql)
        except Exception:
            logger.debug("Data migration skipped: %.80s", sql)


def init_db(db_path: Path | None = None, database_url: str | None = None) -> None:
    if is_postgres(database_url):
        with connect(db_path, database_url) as conn:
            for statement in POSTGRES_SCHEMA:
                try:
                    conn.execute(statement)
                except Exception:  # idempotent best-effort schema statements
                    logger.debug("Schema statement skipped (already applied): %.80s", statement)
        return
    with connect(db_path, database_url) as conn:
        conn.executescript(SQLITE_SCHEMA)
        _apply_sqlite_column_migrations(conn)
        _apply_sqlite_data_migrations(conn)
        _build_fts_index(conn)


def get_setting(key: str, default: str | None = None) -> str | None:
    """Read a value from the settings table."""
    try:
        with connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if row:
                return str(row["value"] if isinstance(row, dict) else row[0])
    except Exception:  # settings are optional; fall back to the default
        logger.debug("Could not read setting %r; using default", key)
    return default


def set_setting(key: str, value: str) -> None:
    """Upsert a key/value pair in the settings table."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value) VALUES(?, ?)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, value),
        )


def row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a sqlite3.Row or psycopg dict row into a plain dict."""
    if isinstance(row, dict):
        return dict(row)
    return {key: row[key] for key in row.keys()}  # noqa: SIM118 - sqlite3.Row is not a Mapping


def insert_article_sql() -> str:
    return """
        INSERT INTO articles(
          url, canonical_url, title, source_slug, source_name, category, kind,
          published_at, summary, reason, importance_score, tags
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO NOTHING
        """


def search_articles_sql(terms: list[str], limit: int) -> tuple[str, list[Any]]:
    """Build a LIKE-based search query compatible with both SQLite and PostgreSQL."""
    if not terms:
        return "SELECT * FROM articles ORDER BY discovered_at DESC LIMIT ?", [limit]
    clauses = []
    params: list[Any] = []
    for term in terms:
        like = f"%{term}%"
        clauses.append(
            "(title LIKE ? OR summary LIKE ? OR tags LIKE ? OR source_name LIKE ? OR reason LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    params.append(limit)
    where = " AND ".join(clauses)
    sql = (
        f"SELECT * FROM articles WHERE {where} "
        "ORDER BY importance_score DESC, discovered_at DESC LIMIT ?"
    )
    return sql, params
