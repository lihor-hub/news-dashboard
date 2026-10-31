"""Frozen seven-completed-local-date recaps in the existing JSONB store."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db
from news_dashboard.reading_progress.daily import effective_zone, lock_account
from news_dashboard.reading_progress.service import get_streak
from news_dashboard.recaps.progress import progress_snapshot, recap_period

logger = logging.getLogger(__name__)

SKIM_THRESHOLD_MS = 30_000


def assemble_weekly_recap(
    user_id: int,
    now: datetime | None = None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
    *,
    period: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Freeze seven completed progress-local dates, anchored before generation delay."""
    init_db(db_path, database_url=database_url)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        msg = "now must be timezone aware"
        raise ValueError(msg)
    if period is not None:
        expected = recap_period(datetime.fromisoformat(period["scheduled_for"]), period["timezone"])
        if period != expected:
            msg = "Invalid recap period"
            raise ValueError(msg)
    with connect(db_path, database_url=database_url) as conn:
        user = lock_account(conn, user_id)
        zone = effective_zone(user)
        if user["progress_timezone"] is None:
            conn.execute(
                "UPDATE users SET progress_timezone=%s WHERE id=%s",
                (period["timezone"] if period else zone, user_id),
            )
    period = period or recap_period(now, zone)
    start = datetime.fromisoformat(period["start_at"])
    end = datetime.fromisoformat(period["end_at"])
    from news_dashboard.personalization_nudges import generate_nudges

    nudges = generate_nudges(user_id, database_url=database_url, db_path=db_path, max_results=2)
    with connect(db_path, database_url=database_url) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot_at = conn.execute("SELECT transaction_timestamp() AS at").fetchone()["at"]
        return {
            "snapshot_version": 2,
            "period": {**period, "snapshot_at": snapshot_at.isoformat()},
            "progress": progress_snapshot(conn, user_id, period),
            "week_start": period["start_local_date"],
            "week_end": (
                date.fromisoformat(period["end_local_date"]) - timedelta(days=1)
            ).isoformat(),
            "generated_at": now.isoformat(),
            "articles_read": _articles_read(conn, user_id, start, end),
            "categories": _top_field(conn, user_id, start, end, "a.category", "category"),
            "sources": _top_field(conn, user_id, start, end, "a.source_name", "source"),
            "minutes_read": _minutes_read(conn, user_id, start, end),
            "current_streak_days": get_streak(user_id, now=now, connection=conn)[
                "current_streak_days"
            ],
            "saved": _saved_backlog(conn, user_id, start, end),
            "dwell": _dwell_profile(conn, user_id, start, end),
            "nudges": nudges,
        }


def save_weekly_recap(
    user_id: int,
    recap: dict[str, Any],
    narrative: str | None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """First v2 snapshot wins, including conflicts with untouched legacy rows."""
    init_db(db_path, database_url=database_url)
    week_start = date.fromisoformat(recap["week_start"])
    with connect(db_path, database_url=database_url) as conn:
        lock_account(conn, user_id, mutation=False)
        if recap.get("snapshot_version") == 2:
            row = conn.execute(
                """INSERT INTO user_weekly_recaps(user_id,week_start,data,narrative)
                   VALUES (%s,%s,%s::jsonb,%s) ON CONFLICT(user_id,week_start) DO NOTHING
                   RETURNING *""",
                (user_id, week_start, json.dumps(recap), narrative),
            ).fetchone()
            inserted = row is not None
            if row is None:
                row = conn.execute(
                    "SELECT * FROM user_weekly_recaps WHERE user_id=%s AND week_start=%s",
                    (user_id, week_start),
                ).fetchone()
            return {"snapshot": dict(row), "inserted": inserted}
        row = conn.execute(
            """
            INSERT INTO user_weekly_recaps (user_id, week_start, data, narrative)
            VALUES (%s, %s, %s::jsonb, %s)
            ON CONFLICT (user_id, week_start)
            DO UPDATE SET data = EXCLUDED.data, narrative = EXCLUDED.narrative
            WHERE user_weekly_recaps.data->>'snapshot_version' IS DISTINCT FROM '2'
            RETURNING id, user_id, week_start, created_at, data, narrative
            """,
            (user_id, week_start, json.dumps(recap), narrative),
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM user_weekly_recaps WHERE user_id=%s AND week_start=%s",
                (user_id, week_start),
            ).fetchone()
    return dict(row)


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


def get_recap(
    user_id: int, recap_id: int, *, database_url: str | None = None
) -> dict[str, Any] | None:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "SELECT * FROM user_weekly_recaps WHERE user_id=%s AND id=%s", (user_id, recap_id)
        ).fetchone()
    return dict(row) if row else None


def fill_narrative(user_id: int, recap_id: int, narrative: str) -> None:
    """One-time enrichment, never changes the frozen measurement JSON."""
    with connect() as conn:
        lock_account(conn, user_id, mutation=False)
        conn.execute(
            """UPDATE user_weekly_recaps SET narrative=%s WHERE user_id=%s AND id=%s
               AND narrative IS NULL AND data->>'snapshot_version'='2'""",
            (narrative, user_id, recap_id),
        )


def _articles_read(conn: Any, user_id: int, start: datetime, end: datetime) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM user_article_state
        WHERE user_id = %s AND state = 'done' AND done_at >= %s AND done_at < %s
        """,
        (user_id, start, end),
    ).fetchone()
    return int(row["n"]) if row and row["n"] is not None else 0


def _top_field(
    conn: Any,
    user_id: int,
    start: datetime,
    end: datetime,
    field_sql: str,
    alias: str,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT {field_sql} AS {alias}, COUNT(*) AS count
        FROM user_article_state s
        JOIN articles a ON a.id = s.article_id
        WHERE s.user_id = %s AND s.state = 'done' AND s.done_at >= %s AND s.done_at < %s
        GROUP BY 1
        ORDER BY count DESC, {alias}
        LIMIT 5
        """,
        (user_id, start, end),
    ).fetchall()
    return [dict(r) for r in rows]


def _minutes_read(conn: Any, user_id: int, start: datetime, end: datetime) -> float:
    row = conn.execute(
        """
        SELECT ROUND(COALESCE(SUM(duration_ms), 0) / 60000.0, 1) AS minutes
        FROM user_events
        WHERE user_id = %s AND event_type = 'heartbeat' AND created_at >= %s AND created_at < %s
        """,
        (user_id, start, end),
    ).fetchone()
    if row is None or row["minutes"] is None:
        return 0.0
    return float(row["minutes"])


def _saved_backlog(conn: Any, user_id: int, start: datetime, end: datetime) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) FILTER (
            WHERE starred_at >= %(start)s AND starred_at < %(end)s
          ) AS starred_this_week,
          COUNT(*) FILTER (
            WHERE state = 'done' AND done_at >= %(start)s AND done_at < %(end)s AND starred = TRUE
          ) AS read_from_backlog,
          COUNT(*) FILTER (
            WHERE starred = TRUE AND state NOT IN ('done', 'archived')
          ) AS backlog_total
        FROM user_article_state
        WHERE user_id = %(user_id)s
        """,
        {"user_id": user_id, "start": start, "end": end},
    ).fetchone()
    return {
        "starred_this_week": int(row["starred_this_week"]) if row else 0,
        "read_from_backlog": int(row["read_from_backlog"]) if row else 0,
        "backlog_total": int(row["backlog_total"]) if row else 0,
    }


def _dwell_profile(conn: Any, user_id: int, start: datetime, end: datetime) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE duration_ms < %(threshold)s) AS skims,
          COUNT(*) FILTER (WHERE duration_ms >= %(threshold)s) AS reads,
          ROUND(AVG(duration_ms) / 1000.0, 1) AS average_seconds
        FROM user_events
        WHERE user_id = %(user_id)s
          AND event_type = 'article_close'
          AND duration_ms IS NOT NULL
          AND created_at >= %(start)s AND created_at < %(end)s
        """,
        {"user_id": user_id, "start": start, "end": end, "threshold": SKIM_THRESHOLD_MS},
    ).fetchone()
    return {
        "skims": int(row["skims"]) if row else 0,
        "reads": int(row["reads"]) if row else 0,
        "average_seconds": float(row["average_seconds"])
        if row and row["average_seconds"] is not None
        else 0.0,
    }
