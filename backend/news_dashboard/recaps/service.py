"""Weekly reading recap assembly and persistence.

A recap summarizes one user's trailing 7-day reading activity: volume, top
categories/sources, and a simple consecutive-day streak. Aggregation mirrors
``news_dashboard.analytics.reading_dna`` but scoped to a fixed 7-day window
and persisted so history can be listed via ``GET /api/recaps``.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db
from news_dashboard.reading_progress.service import get_streak

logger = logging.getLogger(__name__)

RECAP_WINDOW_DAYS = 7


def assemble_weekly_recap(
    user_id: int,
    now: datetime | None = None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Aggregate the trailing 7 days of activity for ``user_id``."""
    init_db(db_path, database_url=database_url)
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=RECAP_WINDOW_DAYS)
    streak = get_streak(user_id, now=now, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        return {
            "week_start": start.date().isoformat(),
            "week_end": now.date().isoformat(),
            "generated_at": now.isoformat(),
            "articles_read": _articles_read(conn, user_id, start),
            "categories": _top_field(conn, user_id, start, "a.category", "category"),
            "sources": _top_field(conn, user_id, start, "a.source_name", "source"),
            "minutes_read": _minutes_read(conn, user_id, start),
            "current_streak_days": streak["current_streak_days"],
        }


def save_weekly_recap(
    user_id: int,
    recap: dict[str, Any],
    narrative: str | None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Persist a computed recap, upserting on (user_id, week_start)."""
    init_db(db_path, database_url=database_url)
    week_start = date.fromisoformat(recap["week_start"])
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_weekly_recaps (user_id, week_start, data, narrative)
            VALUES (%s, %s, %s::jsonb, %s)
            ON CONFLICT (user_id, week_start)
            DO UPDATE SET data = EXCLUDED.data, narrative = EXCLUDED.narrative
            RETURNING id, user_id, week_start, created_at, data, narrative
            """,
            (user_id, week_start, json.dumps(recap), narrative),
        ).fetchone()
    result = dict(row)
    result["data"] = recap
    return result


def list_recaps(
    user_id: int,
    limit: int = 12,
    offset: int = 0,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, week_start, created_at, data, narrative
            FROM user_weekly_recaps
            WHERE user_id = %s
            ORDER BY week_start DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_recap(
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    recaps = list_recaps(user_id, limit=1, db_path=db_path, database_url=database_url)
    return recaps[0] if recaps else None


def _articles_read(conn: Any, user_id: int, start: datetime) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM user_article_state
        WHERE user_id = %s AND state = 'done' AND done_at >= %s
        """,
        (user_id, start),
    ).fetchone()
    return int(row["n"]) if row and row["n"] is not None else 0


def _top_field(
    conn: Any,
    user_id: int,
    start: datetime,
    field_sql: str,
    alias: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT {field_sql} AS {alias}, COUNT(*) AS count
        FROM user_article_state s
        JOIN articles a ON a.id = s.article_id
        WHERE s.user_id = %s AND s.state = 'done' AND s.done_at >= %s
        GROUP BY 1
        ORDER BY count DESC, {alias}
        LIMIT 5
        """,
        (user_id, start),
    ).fetchall()
    return [dict(r) for r in rows]


def _minutes_read(conn: Any, user_id: int, start: datetime) -> float:
    row = conn.execute(
        """
        SELECT ROUND(COALESCE(SUM(duration_ms), 0) / 60000.0, 1) AS minutes
        FROM user_events
        WHERE user_id = %s AND event_type = 'heartbeat' AND created_at >= %s
        """,
        (user_id, start),
    ).fetchone()
    if row is None or row["minutes"] is None:
        return 0.0
    return float(row["minutes"])
