"""Instance-wide article retention policy and cleanup operations."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg import sql

from news_dashboard.db import connect, init_db, row_to_dict

_SETTING_KEY = "article_retention_days"
ARTICLE_RETENTION_LOCK_KEY = 72_563_811

_PROTECTED_PREDICATE = """
EXISTS (
  SELECT 1 FROM user_article_state uas
  WHERE uas.article_id = a.id AND uas.starred = TRUE
)
OR EXISTS (SELECT 1 FROM article_highlights ah WHERE ah.article_id = a.id)
OR EXISTS (SELECT 1 FROM article_tags at WHERE at.article_id = a.id)
OR EXISTS (SELECT 1 FROM briefing_articles ba WHERE ba.article_id = a.id)
OR EXISTS (SELECT 1 FROM article_shares ashare WHERE ashare.article_id = a.id)
OR EXISTS (SELECT 1 FROM articles child WHERE child.canonical_id = a.id)
"""

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RetentionPreview:
    enabled: bool
    retention_days: int | None
    eligible_articles: int
    protected_articles: int
    estimated_payload_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CleanupResult:
    status: str
    retention_days: int | None
    deleted_articles: int
    protected_articles: int
    estimated_deleted_payload_bytes: int
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_retention_days(database_url: str | None = None) -> int | None:
    """Return the enabled retention window, or None for keep forever."""
    init_db(database_url)
    with connect(database_url) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = %s", (_SETTING_KEY,)).fetchone()
    if row is None:
        return None
    try:
        days = int(row["value"])
    except (TypeError, ValueError):
        logger.warning("Ignoring malformed article retention setting")
        return None
    if days < 1:
        logger.warning("Ignoring non-positive article retention setting")
        return None
    return days


def set_retention_days(days: int | None, database_url: str | None = None) -> int | None:
    """Persist a retention window without running cleanup."""
    if days is not None and days < 1:
        message = "retention days must be at least 1"
        raise ValueError(message)
    init_db(database_url)
    with connect(database_url) as conn:
        if days is None:
            conn.execute("DELETE FROM settings WHERE key = %s", (_SETTING_KEY,))
        else:
            conn.execute(
                """
                INSERT INTO settings(key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (_SETTING_KEY, str(days)),
            )
    return days


def retention_preview(
    days: int | None = None,
    database_url: str | None = None,
    *,
    now: datetime | None = None,
) -> RetentionPreview:
    """Count old eligible and protected articles for the active policy."""
    retention_days = days if days is not None else get_retention_days(database_url)
    if retention_days is None:
        return RetentionPreview(False, None, 0, 0, 0)
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    query = sql.SQL(
        """
        SELECT
          COUNT(*) FILTER (WHERE NOT ({protected})) AS eligible_articles,
          COUNT(*) FILTER (WHERE ({protected})) AS protected_articles,
          COALESCE(SUM(pg_column_size(a.*)) FILTER (WHERE NOT ({protected})), 0)
            AS estimated_payload_bytes
        FROM articles a
        WHERE a.discovered_at < %s
        """
    ).format(protected=sql.SQL(_PROTECTED_PREDICATE))
    init_db(database_url)
    with connect(database_url) as conn:
        row = row_to_dict(conn.execute(query, (cutoff,)).fetchone())
    return RetentionPreview(
        True,
        retention_days,
        int(row["eligible_articles"] or 0),
        int(row["protected_articles"] or 0),
        int(row["estimated_payload_bytes"] or 0),
    )


def cleanup_old_articles(
    database_url: str | None = None,
    batch_size: int = 500,
) -> CleanupResult:
    """Delete all currently eligible articles in bounded transactions."""
    retention_days = get_retention_days(database_url)
    if retention_days is None:
        return CleanupResult("skipped", None, 0, 0, 0, "retention disabled")
    if batch_size < 1:
        message = "batch size must be at least 1"
        raise ValueError(message)

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    delete_query = sql.SQL(
        """
        WITH candidates AS (
          SELECT a.id, pg_column_size(a.*) AS payload_bytes
          FROM articles a
          WHERE a.discovered_at < %s AND NOT ({protected})
          ORDER BY a.discovered_at, a.id
          LIMIT %s
          FOR UPDATE OF a SKIP LOCKED
        ), deleted AS (
          DELETE FROM articles a USING candidates c
          WHERE a.id = c.id
          RETURNING c.payload_bytes
        )
        SELECT COUNT(*) AS deleted_articles,
               COALESCE(SUM(payload_bytes), 0) AS deleted_payload_bytes
        FROM deleted
        """
    ).format(protected=sql.SQL(_PROTECTED_PREDICATE))

    total_deleted = 0
    total_payload = 0
    init_db(database_url)
    with connect(database_url) as conn:
        lock_row = conn.execute(
            "SELECT pg_try_advisory_lock(%s, hashtext(current_schema())) AS acquired",
            (ARTICLE_RETENTION_LOCK_KEY,),
        ).fetchone()
        if lock_row is None or not lock_row["acquired"]:
            return CleanupResult("skipped", retention_days, 0, 0, 0, "cleanup already running")
        try:
            while True:
                row = row_to_dict(conn.execute(delete_query, (cutoff, batch_size)).fetchone())
                deleted = int(row["deleted_articles"] or 0)
                total_deleted += deleted
                total_payload += int(row["deleted_payload_bytes"] or 0)
                conn.commit()
                if deleted < batch_size:
                    break
        finally:
            conn.execute(
                "SELECT pg_advisory_unlock(%s, hashtext(current_schema()))",
                (ARTICLE_RETENTION_LOCK_KEY,),
            )

    protected = retention_preview(retention_days, database_url).protected_articles
    message = f"deleted {total_deleted} articles older than {retention_days} days"
    return CleanupResult(
        "success",
        retention_days,
        total_deleted,
        protected,
        total_payload,
        message,
    )
