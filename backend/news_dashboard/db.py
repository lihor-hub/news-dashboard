from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

POSTGRES_PREFIXES = ("postgres:" + "//", "postgresql:" + "//")

logger = logging.getLogger(__name__)
_INIT_DB_LOCK = threading.Lock()
_INITIALIZED_DATABASES: set[tuple[str, str | None, str]] = set()


class SchemaInitializationError(RuntimeError):
    """Raised when PostgreSQL schema initialization cannot complete."""


POSTGRES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
      id            SERIAL PRIMARY KEY,
      username      TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      email         TEXT,
      is_admin      BOOLEAN NOT NULL DEFAULT FALSE,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      last_login_at TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sources (
      slug TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      url TEXT NOT NULL,
      category TEXT NOT NULL,
      kind TEXT NOT NULL,
      priority INTEGER NOT NULL DEFAULT 50,
      enabled BOOLEAN NOT NULL DEFAULT TRUE,
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
      error_message  TEXT,
      duration_ms    INTEGER
    )
    """,
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
    """
    CREATE TABLE IF NOT EXISTS settings (
      key   TEXT PRIMARY KEY,
      value TEXT NOT NULL
    )
    """,
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_success_at TEXT",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_error TEXT",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_fetched_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS last_inserted_count INTEGER NOT NULL DEFAULT 0",
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'sources'
          AND column_name = 'enabled'
          AND data_type = 'integer'
      ) THEN
        ALTER TABLE sources ALTER COLUMN enabled DROP DEFAULT;
        ALTER TABLE sources ALTER COLUMN enabled TYPE BOOLEAN USING enabled <> 0;
      END IF;
      ALTER TABLE sources ALTER COLUMN enabled SET DEFAULT TRUE;
    END $$;
    """,
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS canonical_id BIGINT REFERENCES articles(id)",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS embedding BYTEA",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS body TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS body_status TEXT NOT NULL DEFAULT 'missing'",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS insights TEXT",
    """
    ALTER TABLE articles ADD COLUMN IF NOT EXISTS search_vector tsvector
      GENERATED ALWAYS AS (
        to_tsvector(
          'english',
          coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' ||
          coalesce(reason, '') || ' ' || coalesce(tags, '') || ' ' ||
          coalesce(source_name, '') || ' ' || coalesce(body, '')
        )
      ) STORED
    """,
    "CREATE INDEX IF NOT EXISTS idx_articles_search ON articles USING gin(search_vector)",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'today'",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS starred BOOLEAN NOT NULL DEFAULT FALSE",
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'articles'
          AND column_name = 'starred'
          AND data_type = 'integer'
      ) THEN
        ALTER TABLE articles ALTER COLUMN starred DROP DEFAULT;
        ALTER TABLE articles ALTER COLUMN starred TYPE BOOLEAN USING starred <> 0;
      END IF;
      ALTER TABLE articles ALTER COLUMN starred SET DEFAULT FALSE;
    END $$;
    """,
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS done_at TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS starred_at TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS later_until TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS restored_at TEXT",
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
    (
        "UPDATE articles SET starred = TRUE, starred_at = saved_at"
        " WHERE status = 'saved' AND NOT starred"
    ),
    (
        "UPDATE articles SET done_at = read_at"
        " WHERE status = 'read' AND done_at IS NULL AND read_at IS NOT NULL"
    ),
    "CREATE INDEX IF NOT EXISTS idx_articles_state ON articles(state)",
    "CREATE INDEX IF NOT EXISTS idx_articles_starred ON articles(starred)",
    """
    CREATE INDEX IF NOT EXISTS idx_articles_state_discovered_id
      ON articles(state, discovered_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_articles_category_discovered_id
      ON articles(category, discovered_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_articles_visible_discovered_id
      ON articles(discovered_at DESC, id DESC)
      WHERE canonical_id IS NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ingest_run_sources_source_run
      ON ingest_run_sources(source_name, run_id DESC)
    """,
    "CREATE INDEX IF NOT EXISTS idx_ingest_runs_started ON ingest_runs(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_ingest_run_sources_run ON ingest_run_sources(run_id)",
    """
    CREATE TABLE IF NOT EXISTS briefings (
      id          SERIAL PRIMARY KEY,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      scope       TEXT NOT NULL DEFAULT 'since_last_briefing',
      since_at    TIMESTAMPTZ,
      until_at    TIMESTAMPTZ,
      status      TEXT NOT NULL DEFAULT 'complete',
      title       TEXT,
      summary     TEXT,
      content     JSONB,
      model       TEXT,
      error       TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_briefings_created ON briefings(created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS briefing_articles (
      briefing_id  INTEGER NOT NULL REFERENCES briefings(id) ON DELETE CASCADE,
      article_id   BIGINT  NOT NULL REFERENCES articles(id),
      section_index   INTEGER,
      citation_index  INTEGER,
      PRIMARY KEY (briefing_id, article_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_briefing_articles_briefing ON briefing_articles(briefing_id)",
    (
        "ALTER TABLE sources ADD COLUMN IF NOT EXISTS"
        " owner_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE"
    ),
    "ALTER TABLE briefings ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id)",
    "CREATE INDEX IF NOT EXISTS idx_briefings_user ON briefings(user_id, created_at DESC)",
    "ALTER TABLE briefings ADD COLUMN IF NOT EXISTS script JSONB",
    "ALTER TABLE ingest_run_sources ADD COLUMN IF NOT EXISTS duration_ms INTEGER",
    "ALTER TABLE briefings ADD COLUMN IF NOT EXISTS focus_prompt TEXT",
]

POSTGRES_MULTIUSER_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS user_sources (
      user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      source_slug TEXT    NOT NULL REFERENCES sources(slug) ON DELETE CASCADE,
      enabled     BOOLEAN NOT NULL DEFAULT TRUE,
      added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (user_id, source_slug)
    )
    """,
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'user_sources'
          AND column_name = 'enabled'
          AND data_type = 'integer'
      ) THEN
        ALTER TABLE user_sources ALTER COLUMN enabled DROP DEFAULT;
        ALTER TABLE user_sources ALTER COLUMN enabled TYPE BOOLEAN USING enabled <> 0;
      END IF;
      ALTER TABLE user_sources ALTER COLUMN enabled SET DEFAULT TRUE;
    END $$;
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_sources_user ON user_sources(user_id, enabled)",
    """
    CREATE TABLE IF NOT EXISTS user_interest_profiles (
      user_id      INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      interests    JSONB NOT NULL DEFAULT '[]'::jsonb,
      completed_at TIMESTAMPTZ,
      updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_article_state (
      user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      article_id  BIGINT  NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
      state       TEXT NOT NULL DEFAULT 'today'
                    CHECK(state IN ('today','done','skipped','archived','later')),
      starred     BOOLEAN NOT NULL DEFAULT FALSE,
      done_at     TIMESTAMPTZ,
      starred_at  TIMESTAMPTZ,
      skipped_at  TIMESTAMPTZ,
      archived_at TIMESTAMPTZ,
      later_until TIMESTAMPTZ,
      restored_at TIMESTAMPTZ,
      updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (user_id, article_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_uas_user_state ON user_article_state(user_id, state)",
    (
        "CREATE INDEX IF NOT EXISTS idx_uas_user_starred"
        " ON user_article_state(user_id, starred) WHERE starred = TRUE"
    ),
    "CREATE INDEX IF NOT EXISTS idx_uas_article_id ON user_article_state(article_id)",
    """
    CREATE INDEX IF NOT EXISTS idx_uas_user_state_article
      ON user_article_state(user_id, state, article_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS user_article_recommendations (
      user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      article_id           BIGINT  NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
      recommendation_score DOUBLE PRECISION NOT NULL,
      cold_start_score     DOUBLE PRECISION,
      signals              JSONB NOT NULL DEFAULT '{}'::jsonb,
      model_version        TEXT NOT NULL DEFAULT 'cold-start-v1',
      computed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      PRIMARY KEY (user_id, article_id),
      CHECK (recommendation_score >= 0 AND recommendation_score <= 100)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_uar_user_score
      ON user_article_recommendations(user_id, recommendation_score DESC, article_id)
    """,
    # `stale` flags scores whose inputs changed (preference history) and that need
    # a background recalculation; the partial index keeps the "find stale" sweep cheap.
    (
        "ALTER TABLE user_article_recommendations"
        " ADD COLUMN IF NOT EXISTS stale BOOLEAN NOT NULL DEFAULT FALSE"
    ),
    """
    CREATE INDEX IF NOT EXISTS idx_uar_user_stale
      ON user_article_recommendations(user_id) WHERE stale = TRUE
    """,
    ("ALTER TABLE user_article_recommendations ADD COLUMN IF NOT EXISTS explanation TEXT"),
    # Behavioral telemetry: every row is one client-emitted event. A single
    # table covers time-on-app (heartbeat), page popularity (route), per-article
    # dwell (article_open/article_close), and feature usage (feature). Sessions
    # are derived at query time from heartbeat gaps rather than stored.
    """
    CREATE TABLE IF NOT EXISTS user_events (
      id          BIGSERIAL PRIMARY KEY,
      user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      event_type  TEXT NOT NULL
                    CHECK(event_type IN ('heartbeat','route','article_open',
                                         'article_close','feature')),
      route       TEXT,
      article_id  BIGINT REFERENCES articles(id) ON DELETE SET NULL,
      feature     TEXT,
      duration_ms INTEGER,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_events_user_time ON user_events(user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_user_events_type_time ON user_events(event_type, created_at)",
    """
    CREATE TABLE IF NOT EXISTS user_settings (
      user_id          INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      category_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
      novelty_weight   DOUBLE PRECISION NOT NULL DEFAULT 1.0,
      updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CHECK (novelty_weight >= 0 AND novelty_weight <= 3)
    )
    """,
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS briefing_time TEXT DEFAULT '09:00'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS briefing_push_enabled"
    " BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS briefing_timezone TEXT NOT NULL DEFAULT 'UTC'",
    """
    CREATE TABLE IF NOT EXISTS user_push_subscriptions (
      id          SERIAL PRIMARY KEY,
      user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      endpoint    TEXT NOT NULL UNIQUE,
      p256dh_key  TEXT NOT NULL,
      auth_key    TEXT NOT NULL,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_push_subs_user ON user_push_subscriptions(user_id)",
    """
    CREATE TABLE IF NOT EXISTS article_shares (
      id            BIGSERIAL PRIMARY KEY,
      article_id    BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
      from_user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      to_user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      note          TEXT,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      read_at       TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_article_shares_recipient"
    " ON article_shares(to_user_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_article_shares_unread"
    " ON article_shares(to_user_id) WHERE read_at IS NULL",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS perspective_analysis JSONB",
    """
    CREATE TABLE IF NOT EXISTS user_goals (
      id          SERIAL PRIMARY KEY,
      user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      description TEXT NOT NULL,
      keywords    TEXT NOT NULL DEFAULT '',
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_goals_user ON user_goals(user_id)",
    """
    CREATE TABLE IF NOT EXISTS user_quizzes (
      id          SERIAL PRIMARY KEY,
      user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      questions   JSONB NOT NULL DEFAULT '[]'::jsonb,
      score       INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_quizzes_user ON user_quizzes(user_id, created_at DESC)",
    "ALTER TABLE article_shares ADD COLUMN IF NOT EXISTS context_summary TEXT",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
    """
    CREATE TABLE IF NOT EXISTS share_annotations (
      id              BIGSERIAL PRIMARY KEY,
      share_id        BIGINT NOT NULL REFERENCES article_shares(id) ON DELETE CASCADE,
      highlighted_text TEXT NOT NULL,
      offset_chars    INTEGER NOT NULL DEFAULT 0,
      note            TEXT,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_share_annotations_share"
    " ON share_annotations(share_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS article_highlights (
      id               BIGSERIAL PRIMARY KEY,
      user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      article_id       BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
      highlighted_text TEXT NOT NULL,
      offset_chars     INTEGER NOT NULL DEFAULT 0,
      note             TEXT,
      created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_article_highlights_user_article"
    " ON article_highlights(user_id, article_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS share_messages (
      id          BIGSERIAL PRIMARY KEY,
      share_id    BIGINT NOT NULL REFERENCES article_shares(id) ON DELETE CASCADE,
      user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      message     TEXT NOT NULL,
      created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_share_messages_share ON share_messages(share_id, created_at)",
    "ALTER TABLE sources ADD COLUMN IF NOT EXISTS lang VARCHAR(5) DEFAULT 'en'",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS original_title TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS original_body TEXT",
    "ALTER TABLE articles ADD COLUMN IF NOT EXISTS detected_lang VARCHAR(5) DEFAULT 'en'",
    """
    CREATE TABLE IF NOT EXISTS user_nudge_dismissals (
      id              SERIAL PRIMARY KEY,
      user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      nudge_kind      VARCHAR(20) NOT NULL,
      nudge_target    TEXT NOT NULL,
      dismissed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      cooldown_until  TIMESTAMPTZ NOT NULL,
      UNIQUE(user_id, nudge_kind, nudge_target)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_nudge_dismissals_user"
    " ON user_nudge_dismissals(user_id, cooldown_until)",
    "ALTER TABLE user_quizzes ADD COLUMN IF NOT EXISTS submitted_answers JSONB",
    "ALTER TABLE user_quizzes ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ",
    """
    CREATE TABLE IF NOT EXISTS scheduled_job_runs (
      id           SERIAL PRIMARY KEY,
      job_name     TEXT NOT NULL,
      started_at   TIMESTAMPTZ NOT NULL,
      finished_at  TIMESTAMPTZ,
      duration_ms  INTEGER,
      status       TEXT NOT NULL,
      message      TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_scheduled_job_runs_job_started"
    " ON scheduled_job_runs(job_name, started_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS user_otps (
      id         SERIAL PRIMARY KEY,
      user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      otp_hash   TEXT NOT NULL,
      expires_at TIMESTAMPTZ NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_otps_user ON user_otps(user_id, expires_at DESC)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_guest BOOLEAN NOT NULL DEFAULT FALSE",
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
    encoded_user = quote(user, safe="")
    encoded_password = quote(password, safe="")
    encoded_database = quote(database, safe="")
    return f"postgresql://{encoded_user}:{encoded_password}@{host}:{port}/{encoded_database}"


def describe_database(database_url: str | None = None) -> str:
    url = active_database_url(database_url)
    parts = urlsplit(url)
    if parts.password:
        host = parts.hostname or ""
        netloc = f"{parts.username}:***@{host}"
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return url


def _open_connection(database_url: str | None) -> Any:
    """Open a psycopg connection, retrying transient connection failures.

    PostgreSQL may not yet be accepting TCP connections when the app starts
    (a common race in containerized/Kubernetes deployments where the app pod
    comes up before the database). Retry ``OperationalError`` — the
    connection-level failure class — with a fixed backoff before giving up, so
    startup waits the database out instead of crashing. Non-connection errors
    are not retried. Tunable via ``DB_CONNECT_MAX_ATTEMPTS`` and
    ``DB_CONNECT_RETRY_DELAY_SECONDS``.
    """
    dsn = active_database_url(database_url)
    try:
        max_attempts = max(1, int(os.getenv("DB_CONNECT_MAX_ATTEMPTS", "30")))
    except ValueError:
        max_attempts = 30
    try:
        delay = max(0.0, float(os.getenv("DB_CONNECT_RETRY_DELAY_SECONDS", "2.0")))
    except ValueError:
        delay = 2.0
    for attempt in range(1, max_attempts + 1):
        try:
            # ty mis-resolves psycopg's overloaded connect() and infers the
            # default tuple row_factory; mypy and pyrefly both accept dict_row.
            return psycopg.connect(dsn, row_factory=dict_row)  # ty: ignore[invalid-argument-type]
        except psycopg.OperationalError as exc:
            if attempt >= max_attempts:
                raise
            logger.warning(
                "PostgreSQL connection attempt %d/%d failed (%s); retrying in %.1fs",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            time.sleep(delay)
    # Unreachable: range starts at 1 and max_attempts >= 1, so the loop body
    # always runs and either returns or raises.
    message = "PostgreSQL connection retry loop exited without connecting"
    raise RuntimeError(message)  # pragma: no cover


@contextmanager
def connect(
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> Iterator[Any]:
    """Open a PostgreSQL connection using psycopg-native SQL and parameters."""
    if isinstance(db_path, str) and db_path.startswith(POSTGRES_PREFIXES):
        database_url = db_path
        db_path = None
    conn = _open_connection(database_url)
    try:
        if isinstance(db_path, Path):
            schema = _schema_name(db_path)
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None, database_url: str | None = None) -> None:
    if isinstance(db_path, str) and db_path.startswith(POSTGRES_PREFIXES):
        database_url = db_path
        db_path = None
    schema_fingerprint = sha256(
        "\0".join(POSTGRES_SCHEMA + POSTGRES_MULTIUSER_SCHEMA).encode("utf-8")
    ).hexdigest()
    env_key = (
        database_url
        or os.getenv("DATABASE_URL")
        or "|".join(
            (
                os.getenv("POSTGRES_HOST", ""),
                os.getenv("POSTGRES_PORT", ""),
                os.getenv("POSTGRES_DB", ""),
                os.getenv("POSTGRES_USER", ""),
            )
        )
    )
    cache_key = (
        str(db_path or ""),
        env_key,
        schema_fingerprint,
    )
    with _INIT_DB_LOCK:
        if cache_key in _INITIALIZED_DATABASES:
            return

    # Each statement runs in its own transaction so one failed statement does
    # not leave later attempts in an aborted transaction.
    applied = 0
    for statement in POSTGRES_SCHEMA + POSTGRES_MULTIUSER_SCHEMA:
        try:
            with connect(db_path, database_url=database_url) as conn:
                conn.execute(statement)
                applied += 1
        except Exception as exc:
            statement_preview = " ".join(statement.split())[:240]
            logger.exception("Schema initialization failed on statement: %s", statement_preview)
            message = f"Schema initialization failed on statement: {statement_preview}"
            raise SchemaInitializationError(message) from exc
    if applied > 0:
        with _INIT_DB_LOCK:
            _INITIALIZED_DATABASES.add(cache_key)


def _schema_name(token: Path) -> str:
    digest = sha256(str(token).encode("utf-8")).hexdigest()[:16]
    return f"test_{digest}"


def get_setting(key: str, default: str | None = None) -> str | None:
    """Read a value from the settings table."""
    try:
        with connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = %s", (key,)).fetchone()
            if row:
                return str(row["value"])
    except Exception:
        logger.debug("Could not read setting %r; using default", key)
    return default


def set_setting(key: str, value: str) -> None:
    """Upsert a key/value pair in the settings table."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings(key, value) VALUES(%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, value),
        )


def row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a psycopg dict row into a plain dict."""
    if isinstance(row, Mapping):
        return dict(row)
    return {key: row[key] for key in row}


def placeholders(values: Sequence[Any]) -> str:
    """Return psycopg placeholders for a non-empty dynamic SQL list."""
    if not values:
        message = "placeholders() requires at least one value"
        raise ValueError(message)
    return ", ".join("%s" for _ in values)


def insert_article_sql() -> str:
    return """
        INSERT INTO articles(
          url, canonical_url, title, source_slug, source_name, category, kind,
          published_at, summary, reason, importance_score, tags,
          original_title, original_body, detected_lang
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (url) DO NOTHING
        """


def search_articles_sql(terms: list[str], limit: int) -> tuple[str, list[Any]]:
    if not terms:
        return "SELECT * FROM articles ORDER BY discovered_at DESC LIMIT %s", [limit]
    clauses = []
    params: list[Any] = []
    for term in terms:
        like = f"%{term}%"
        clauses.append(
            "(title ILIKE %s OR summary ILIKE %s OR tags ILIKE %s"
            " OR source_name ILIKE %s OR reason ILIKE %s)"
        )
        params.extend([like, like, like, like, like])
    params.append(limit)
    where = " AND ".join(clauses)
    sql = (
        f"SELECT * FROM articles WHERE {where} "
        "ORDER BY importance_score DESC, discovered_at DESC LIMIT %s"
    )
    return sql, params
