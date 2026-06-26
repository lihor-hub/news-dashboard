"""User-behavior analytics: ingest client telemetry and aggregate it for admins.

Events are emitted by the frontend tracker (see ``frontend/src/lib/analytics.ts``)
and stored one row per event in ``user_events``. Time-on-app is reconstructed from
``heartbeat`` events whose ``duration_ms`` is the active foreground time since the
previous heartbeat; sessions are derived from gaps between heartbeats at query time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db

logger = logging.getLogger(__name__)

ALLOWED_EVENT_TYPES = frozenset({"heartbeat", "route", "article_open", "article_close", "feature"})
# Clamp a single heartbeat's reported active time so a misbehaving or malicious
# client cannot inflate time-on-app. The tracker beats every 15s; 5 min is slack.
MAX_HEARTBEAT_MS = 5 * 60 * 1000
# Gap (seconds) of heartbeat silence that ends one session and starts the next.
SESSION_GAP_SECONDS = 30 * 60


def record_events(
    user_id: int,
    events: list[dict[str, Any]],
    db_path: Path | None = None,
    database_url: str | None = None,
) -> int:
    """Bulk-insert validated telemetry events for ``user_id``; return the count stored."""
    init_db(db_path, database_url=database_url)
    rows: list[tuple[int, str, str | None, int | None, str | None, int | None]] = []
    for event in events:
        event_type = str(event.get("type") or "")
        if event_type not in ALLOWED_EVENT_TYPES:
            continue
        route = _clean_text(event.get("route"))
        feature = _clean_text(event.get("feature"))
        article_id = _coerce_int(event.get("article_id"))
        duration_ms = _coerce_int(event.get("duration_ms"))
        if duration_ms is not None:
            duration_ms = max(0, min(duration_ms, MAX_HEARTBEAT_MS))
        rows.append((user_id, event_type, route, article_id, feature, duration_ms))

    if not rows:
        return 0

    with connect(db_path, database_url=database_url) as conn:
        conn.cursor().executemany(
            """
            INSERT INTO user_events
              (user_id, event_type, route, article_id, feature, duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    return len(rows)


def admin_analytics(
    days: int = 30,
    db_path: Path | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Aggregate user consumption and behavior over the trailing ``days`` window."""
    init_db(db_path, database_url=database_url)
    days = max(1, min(days, 365))
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    with connect(db_path, database_url=database_url) as conn:
        return {
            "range_days": days,
            "generated_at": now.isoformat(),
            "summary": _summary(conn, start, now),
            "active_over_time": _active_over_time(conn, start),
            "users": _per_user(conn, start),
            "route_popularity": _route_popularity(conn, start),
            "feature_usage": _feature_usage(conn, start),
            "article_dwell": _article_dwell(conn, start),
            "category_consumption": _category_consumption(conn, start),
            "source_consumption": _source_consumption(conn, start),
            "hourly_heatmap": _hourly_heatmap(conn, start),
            "skip_rate_trend": _skip_rate_trend(conn, start),
            "recommendation_funnel": _recommendation_funnel(conn, start),
        }


def _summary(conn: Any, start: datetime, now: datetime) -> dict[str, Any]:
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    dau = _scalar(
        conn,
        "SELECT COUNT(DISTINCT user_id) FROM user_events WHERE created_at >= %s",
        (day_ago,),
    )
    wau = _scalar(
        conn,
        "SELECT COUNT(DISTINCT user_id) FROM user_events WHERE created_at >= %s",
        (week_ago,),
    )
    mau = _scalar(
        conn,
        "SELECT COUNT(DISTINCT user_id) FROM user_events WHERE created_at >= %s",
        (start,),
    )
    total_ms = _scalar(
        conn,
        "SELECT COALESCE(SUM(duration_ms), 0) FROM user_events"
        " WHERE event_type = 'heartbeat' AND created_at >= %s",
        (start,),
    )
    total_reads = _scalar(
        conn,
        "SELECT COUNT(*) FROM user_article_state WHERE state = 'done' AND done_at >= %s",
        (start,),
    )
    total_events = _scalar(
        conn, "SELECT COUNT(*) FROM user_events WHERE created_at >= %s", (start,)
    )
    sessions = _session_stats(conn, start)
    return {
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "stickiness": round(dau / mau, 3) if mau else 0.0,
        "total_minutes": round(total_ms / 60000, 1),
        "total_sessions": sessions["count"],
        "avg_session_minutes": sessions["avg_minutes"],
        "total_reads": total_reads,
        "total_events": total_events,
    }


def _session_stats(conn: Any, start: datetime) -> dict[str, Any]:
    """Derive session count and average length from heartbeat gaps per user."""
    rows = _query(
        conn,
        """
        SELECT user_id, created_at
        FROM user_events
        WHERE event_type = 'heartbeat' AND created_at >= %s
        ORDER BY user_id, created_at
        """,
        (start,),
    )
    sessions = 0
    durations: list[float] = []
    prev_user: int | None = None
    prev_time: datetime | None = None
    session_start: datetime | None = None
    for row in rows:
        user_id = int(row["user_id"])
        ts = _as_datetime(row["created_at"])
        new_session = (
            user_id != prev_user
            or prev_time is None
            or (ts - prev_time).total_seconds() > SESSION_GAP_SECONDS
        )
        if new_session:
            if session_start is not None and prev_time is not None:
                durations.append((prev_time - session_start).total_seconds())
            sessions += 1
            session_start = ts
        prev_user = user_id
        prev_time = ts
    if session_start is not None and prev_time is not None:
        durations.append((prev_time - session_start).total_seconds())

    avg_minutes = round(sum(durations) / len(durations) / 60, 1) if durations else 0.0
    return {"count": sessions, "avg_minutes": avg_minutes}


def _active_over_time(conn: Any, start: datetime) -> list[dict[str, Any]]:
    return _query(
        conn,
        """
        SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
               COUNT(DISTINCT user_id) AS active_users,
               ROUND(COALESCE(SUM(duration_ms) FILTER (WHERE event_type = 'heartbeat'), 0)
                     / 60000.0, 1) AS minutes
        FROM user_events
        WHERE created_at >= %s
        GROUP BY 1
        ORDER BY 1
        """,
        (start,),
    )


def _per_user(conn: Any, start: datetime) -> list[dict[str, Any]]:
    return _query(
        conn,
        """
        SELECT u.id AS user_id,
               u.username,
               u.last_login_at,
               ROUND(COALESCE(ev.total_ms, 0) / 60000.0, 1) AS minutes,
               COALESCE(ev.events, 0) AS events,
               COALESCE(st.reads, 0) AS reads,
               COALESCE(st.skips, 0) AS skips,
               COALESCE(st.starred, 0) AS starred,
               COALESCE(br.briefings, 0) AS briefings
        FROM users u
        LEFT JOIN (
            SELECT user_id,
                   COUNT(*) AS events,
                   SUM(duration_ms) FILTER (WHERE event_type = 'heartbeat') AS total_ms
            FROM user_events WHERE created_at >= %(start)s GROUP BY user_id
        ) ev ON ev.user_id = u.id
        LEFT JOIN (
            SELECT user_id,
                   COUNT(*) FILTER (WHERE state = 'done' AND done_at >= %(start)s) AS reads,
                   COUNT(*) FILTER (WHERE skipped_at >= %(start)s) AS skips,
                   COUNT(*) FILTER (WHERE starred_at >= %(start)s) AS starred
            FROM user_article_state GROUP BY user_id
        ) st ON st.user_id = u.id
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS briefings
            FROM briefings WHERE created_at >= %(start)s GROUP BY user_id
        ) br ON br.user_id = u.id
        ORDER BY minutes DESC, reads DESC, u.username
        """,
        {"start": start},
    )


def _route_popularity(conn: Any, start: datetime) -> list[dict[str, Any]]:
    return _query(
        conn,
        """
        SELECT route,
               COUNT(*) AS views,
               COUNT(DISTINCT user_id) AS users
        FROM user_events
        WHERE event_type = 'route' AND route IS NOT NULL AND created_at >= %s
        GROUP BY route
        ORDER BY views DESC
        LIMIT 30
        """,
        (start,),
    )


def _feature_usage(conn: Any, start: datetime) -> list[dict[str, Any]]:
    return _query(
        conn,
        """
        SELECT feature,
               COUNT(*) AS count,
               COUNT(DISTINCT user_id) AS users
        FROM user_events
        WHERE event_type = 'feature' AND feature IS NOT NULL AND created_at >= %s
        GROUP BY feature
        ORDER BY count DESC
        LIMIT 30
        """,
        (start,),
    )


def _article_dwell(conn: Any, start: datetime) -> list[dict[str, Any]]:
    return _query(
        conn,
        """
        SELECT e.article_id,
               a.title,
               COUNT(*) AS opens,
               ROUND(AVG(e.duration_ms) / 1000.0, 1) AS avg_dwell_seconds
        FROM user_events e
        JOIN articles a ON a.id = e.article_id
        WHERE e.event_type = 'article_close'
          AND e.duration_ms IS NOT NULL
          AND e.created_at >= %s
        GROUP BY e.article_id, a.title
        ORDER BY opens DESC, avg_dwell_seconds DESC
        LIMIT 20
        """,
        (start,),
    )


def _category_consumption(conn: Any, start: datetime) -> list[dict[str, Any]]:
    return _query(
        conn,
        """
        SELECT a.category, COUNT(*) AS reads
        FROM user_article_state s
        JOIN articles a ON a.id = s.article_id
        WHERE s.state = 'done' AND s.done_at >= %s
        GROUP BY a.category
        ORDER BY reads DESC
        """,
        (start,),
    )


def _source_consumption(conn: Any, start: datetime) -> list[dict[str, Any]]:
    return _query(
        conn,
        """
        SELECT a.source_name, COUNT(*) AS reads
        FROM user_article_state s
        JOIN articles a ON a.id = s.article_id
        WHERE s.state = 'done' AND s.done_at >= %s
        GROUP BY a.source_name
        ORDER BY reads DESC
        LIMIT 20
        """,
        (start,),
    )


def _hourly_heatmap(conn: Any, start: datetime) -> list[dict[str, Any]]:
    return _query(
        conn,
        """
        SELECT EXTRACT(DOW FROM created_at)::int AS dow,
               EXTRACT(HOUR FROM created_at)::int AS hour,
               COUNT(*) AS events
        FROM user_events
        WHERE created_at >= %s
        GROUP BY 1, 2
        ORDER BY 1, 2
        """,
        (start,),
    )


def _skip_rate_trend(conn: Any, start: datetime) -> list[dict[str, Any]]:
    return _query(
        conn,
        """
        SELECT to_char(date_trunc('day', ts), 'YYYY-MM-DD') AS day,
               COUNT(*) FILTER (WHERE kind = 'skip') AS skips,
               COUNT(*) FILTER (WHERE kind = 'read') AS reads
        FROM (
            SELECT done_at AS ts, 'read' AS kind FROM user_article_state
            WHERE state = 'done' AND done_at >= %(start)s
            UNION ALL
            SELECT skipped_at AS ts, 'skip' AS kind FROM user_article_state
            WHERE skipped_at >= %(start)s
        ) events
        GROUP BY 1
        ORDER BY 1
        """,
        {"start": start},
    )


def _recommendation_funnel(conn: Any, start: datetime) -> dict[str, Any]:
    recommended = _scalar(
        conn,
        "SELECT COUNT(*) FROM user_article_recommendations WHERE computed_at >= %s",
        (start,),
    )
    read = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM user_article_recommendations r
        JOIN user_article_state s
          ON s.user_id = r.user_id AND s.article_id = r.article_id
        WHERE r.computed_at >= %s AND s.state = 'done'
        """,
        (start,),
    )
    skipped = _scalar(
        conn,
        """
        SELECT COUNT(*) FROM user_article_recommendations r
        JOIN user_article_state s
          ON s.user_id = r.user_id AND s.article_id = r.article_id
        WHERE r.computed_at >= %s AND s.skipped_at IS NOT NULL
        """,
        (start,),
    )
    return {"recommended": recommended, "read": read, "skipped": skipped}


def _query(conn: Any, sql: str, params: Any) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params)
    return [dict(row) for row in cursor.fetchall()]


def _scalar(conn: Any, sql: str, params: Any) -> int:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return 0
    value = next(iter(row.values()))
    return int(value) if value is not None else 0


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value))


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:200] if text else None


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
