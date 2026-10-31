"""Read-only frozen progress metrics; existing domain records remain authoritative."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from news_dashboard.reading_progress.rewards import descriptor


def recap_period(scheduled_for: datetime, zone: str) -> dict[str, str]:
    if scheduled_for.tzinfo is None:
        msg = "scheduled_for must be timezone aware"
        raise ValueError(msg)
    tz = ZoneInfo(zone)
    end = scheduled_for.astimezone(tz).date()
    start = end - timedelta(days=7)
    return {
        "timezone": zone,
        "start_local_date": start.isoformat(),
        "end_local_date": end.isoformat(),
        "start_at": datetime.combine(start, time.min, tz).astimezone(timezone.utc).isoformat(),
        "end_at": datetime.combine(end, time.min, tz).astimezone(timezone.utc).isoformat(),
        "scheduled_for": scheduled_for.astimezone(timezone.utc).isoformat(),
    }


def progress_snapshot(conn: Any, user_id: int, period: dict[str, str]) -> dict[str, Any]:
    params = (user_id, period["start_local_date"], period["end_local_date"])
    visits = conn.execute(
        """SELECT local_date,timezone,first_visited_at FROM user_daily_visits
           WHERE user_id=%s AND local_date >= %s AND local_date < %s ORDER BY local_date""",
        params,
    ).fetchall()
    start_at = datetime.fromisoformat(period["start_at"])
    end_at = datetime.fromisoformat(period["end_at"])
    visits = [row for row in visits if start_at <= row["first_visited_at"] < end_at]
    first_visit = conn.execute(
        "SELECT MIN(first_visited_at) AS first FROM user_daily_visits WHERE user_id=%s",
        (user_id,),
    ).fetchone()["first"]
    days = conn.execute(
        """SELECT local_date,timezone,active_ms,coverage_flags FROM user_activity_days
           WHERE user_id=%s AND local_date >= %s AND local_date < %s
           ORDER BY local_date,timezone""",
        params,
    ).fetchall()
    totals = conn.execute(
        "SELECT measured_since,coverage_flags FROM user_activity_totals WHERE user_id=%s",
        (user_id,),
    ).fetchone()
    if first_visit and first_visit >= end_at:
        first_visit = None
    measured_since = totals["measured_since"] if totals else None
    if measured_since and measured_since >= end_at:
        measured_since = None
    same_zone_days = [row for row in days if row["timezone"] == period["timezone"]]
    active = bool(same_zone_days) and measured_since is not None
    flags = totals["coverage_flags"] if totals else 1
    for row in days:
        flags |= row["coverage_flags"]
    reasons = ["global_gap_or_unknown"]
    for bit, reason in (
        (2, "consent_gap"),
        (4, "timezone_change"),
        (8, "transport_incomplete"),
        (16, "retention_unknown"),
    ):
        if flags & bit:
            reasons.append(reason)
    if len(same_zone_days) < 7:
        reasons.append("missing_days")
    if (
        any(row["timezone"] != period["timezone"] for row in [*visits, *days])
        and "timezone_change" not in reasons
    ):
        reasons.append("timezone_change")
    rewards = []
    for row in conn.execute(
        """SELECT * FROM user_achievements WHERE user_id=%s AND origin='live'
           AND earned_at >= %s AND earned_at < %s ORDER BY earned_at,achievement_key""",
        (user_id, period["start_at"], period["end_at"]),
    ).fetchall():
        item = descriptor(row)
        # Freeze only display fields, not mutable metadata or presentation state.
        rewards.append(
            {key: item[key] for key in ("key", "title", "description", "topic_id", "earned_at")}
        )
    return {
        "days_visited": sum(row["timezone"] == period["timezone"] for row in visits)
        if first_visit
        else None,
        "active_seconds": sum(row["active_ms"] for row in same_zone_days) / 1000
        if active
        else None,
        "coverage": {
            "visits": {
                "status": "partial" if first_visit else "unavailable",
                "measured_from": first_visit.isoformat() if first_visit else None,
                "reasons": ["frozen_observations_only"]
                + (["timezone_change"] if "timezone_change" in reasons else []),
            },
            "active_time": {
                "status": "partial" if active else "unavailable",
                "measured_from": measured_since.isoformat() if measured_since else None,
                "reasons": reasons,
            },
            "rewards": {
                "status": "partial",
                "measured_from": None,
                "reasons": ["trusted_live_only"],
            },
        },
        "rewards": rewards,
    }
