"""Bounded, connected app time. Never article-reading evidence or a session history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from news_dashboard.analytics import analytics_globally_enabled
from news_dashboard.db import connect, init_db
from news_dashboard.reading_progress.daily import (
    account,
    effective_zone,
    lock_account,
    next_midnight,
    utc_now,
)
from news_dashboard.reading_progress.rewards import TIME_TARGETS, award_rewards

# Monotone bounded bits, not an availability timeline. Global history is always unknown.
GLOBAL_UNKNOWN, CONSENT_GAP, ZONE_CHANGE, TRANSPORT_GAP, RETENTION_UNKNOWN = 1, 2, 4, 8, 16
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class ActivityHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window_id: UUID
    start_ms: int = Field(ge=0, lt=30000, strict=True)
    end_ms: int = Field(gt=0, le=30000, strict=True)

    @model_validator(mode="after")
    def ordered(self) -> ActivityHeartbeat:
        if self.end_ms <= self.start_ms:
            msg = "Interval must be positive"
            raise ValueError(msg)
        return self


def milliseconds(value: datetime) -> int:
    return (value - EPOCH) // timedelta(milliseconds=1)


def instant(value: int) -> datetime:
    return EPOCH + timedelta(milliseconds=value)


def uncovered(start: int, end: int, union: list[list[int]]) -> list[list[int]]:
    result = []
    for left, right in union:
        if left > start:
            result.append([start, min(end, left)])
        start = max(start, right) if left <= end else end
        if start >= end:
            break
    if start < end:
        result.append([start, end])
    return result


def merge(intervals: list[list[int]]) -> list[list[int]]:
    result: list[list[int]] = []
    for left, right in sorted(intervals):
        if result and result[-1][1] >= left:
            result[-1][1] = max(result[-1][1], right)
        else:
            result.append([left, right])
    return result


def ensure_total(conn: Any, user_id: int) -> None:
    conn.execute(
        "INSERT INTO user_activity_totals(user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,)
    )


def mark_gap(conn: Any, user_id: int, zone: str, revision: int, flag: int, now: datetime) -> None:
    ensure_total(conn, user_id)
    conn.execute(
        "UPDATE user_activity_totals SET coverage_flags=coverage_flags | %s WHERE user_id=%s",
        (flag, user_id),
    )
    conn.execute(
        """INSERT INTO user_activity_days(user_id,local_date,timezone,coverage_flags,revision)
           VALUES (%s,%s,%s,%s,%s) ON CONFLICT(user_id,local_date,timezone) DO UPDATE
           SET coverage_flags=user_activity_days.coverage_flags | EXCLUDED.coverage_flags,
               revision=GREATEST(user_activity_days.revision,EXCLUDED.revision)""",
        (user_id, now.astimezone(ZoneInfo(zone)).date(), zone, flag | GLOBAL_UNKNOWN, revision),
    )


def invalidate(conn: Any, user_id: int, *, flag: int = CONSENT_GAP) -> None:
    """Caller holds account lock; consent and timezone changes fence both protocols."""
    revision = conn.execute(
        "UPDATE users SET activity_revision=activity_revision+1 "
        "WHERE id=%s RETURNING activity_revision",
        (user_id,),
    ).fetchone()["activity_revision"]
    conn.execute("DELETE FROM user_activity_windows WHERE user_id=%s", (user_id,))
    conn.execute("DELETE FROM user_reader_evidence WHERE user_id=%s", (user_id,))
    mark_gap(conn, user_id, effective_zone(account(conn, user_id)), revision, flag, utc_now())


def consent(conn: Any, user_id: int) -> Any:
    return conn.execute(
        "SELECT analytics_enabled,activity_revision FROM users WHERE id=%s", (user_id,)
    ).fetchone()


def set_consent(conn: Any, user_id: int, enabled: bool) -> None:
    """Settings and archive writers share this fence on their locked caller transaction."""
    if consent(conn, user_id)["analytics_enabled"] != enabled:
        if not account(conn, user_id)["is_guest"]:
            invalidate(conn, user_id)
        else:
            conn.execute("DELETE FROM user_reader_evidence WHERE user_id=%s", (user_id,))
    conn.execute("UPDATE users SET analytics_enabled=%s WHERE id=%s", (enabled, user_id))


def snapshot(conn: Any, user_id: int) -> dict[str, Any]:
    user = account(conn, user_id)
    if user["is_guest"]:
        return {"available": False}
    enabled = bool(consent(conn, user_id)["analytics_enabled"] and analytics_globally_enabled())
    row = conn.execute("SELECT * FROM user_activity_totals WHERE user_id=%s", (user_id,)).fetchone()
    total = row["total_ms"] if row else 0
    flags = row["coverage_flags"] if row else GLOBAL_UNKNOWN
    reasons = ["global_gap_or_unknown"]
    reasons.extend(
        name
        for flag, name in (
            (CONSENT_GAP, "consent_gap"),
            (ZONE_CHANGE, "timezone_change"),
            (TRANSPORT_GAP, "transport_incomplete"),
            (RETENTION_UNKNOWN, "retention_unknown"),
        )
        if flags & flag
    )
    if not row or row["measured_since"] is None:
        reasons.append("pre_measurement")
    return {
        "available": True,
        "measurement_enabled": enabled,
        "total_ms": total,
        "measured_since": row["measured_since"].isoformat()
        if row and row["measured_since"]
        else None,
        "approximate": True,
        "coverage": {
            "status": "partial" if row and row["measured_since"] else "unknown",
            "reasons": reasons,
        },
        "next_target_ms": next((n * 1000 for n in TIME_TARGETS if n * 1000 > total), None),
    }


def get_activity(user_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return snapshot(conn, user_id)


def rate_limit(conn: Any, user_id: int, now_ms: int) -> None:
    ensure_total(conn, user_id)
    row = conn.execute(
        "SELECT rate_minute,rate_count FROM user_activity_totals WHERE user_id=%s", (user_id,)
    ).fetchone()
    minute = now_ms // 60000
    count = row["rate_count"] if row["rate_minute"] == minute else 0
    if count >= 120:
        raise HTTPException(429, "activity_rate_limit", headers={"Retry-After": "60"})
    conn.execute(
        "UPDATE user_activity_totals SET rate_minute=%s,rate_count=%s WHERE user_id=%s",
        (minute, count + 1, user_id),
    )


def enabled_or_invalidate(conn: Any, user_id: int) -> Any:
    saved = consent(conn, user_id)
    if not saved["analytics_enabled"] or not analytics_globally_enabled():
        invalidate(conn, user_id)
        return None
    return saved


def open_window(user_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        user = lock_account(conn, user_id)
        now = utc_now()  # Authoritative clock is sampled after the shared account lock.
        anchor = milliseconds(now)
        rate_limit(conn, user_id, anchor)
        saved = enabled_or_invalidate(conn, user_id)
        if saved is None:
            return {"available": False, "reason": "measurement_disabled"}
        conn.execute(
            "DELETE FROM user_activity_windows WHERE user_id=%s AND expires_at<=%s",
            (user_id, now - timedelta(seconds=90)),
        )
        count = conn.execute(
            "SELECT count(*) AS n FROM user_activity_windows "
            "WHERE user_id=%s AND expires_at>%s AND receipt IS NULL",
            (user_id, now),
        ).fetchone()["n"]
        if count >= 16:
            conn.commit()  # Keep the abuse counter; no time/window/award was created.
            raise HTTPException(429, "activity_window_capacity")
        zone = effective_zone(user)
        if user["progress_timezone"] is None:
            conn.execute("UPDATE users SET progress_timezone=%s WHERE id=%s", (zone, user_id))
        token = uuid4()
        conn.execute(
            """INSERT INTO user_activity_windows(id,user_id,issued_ms,revision,timezone,expires_at)
                        VALUES (%s,%s,%s,%s,%s,%s)""",
            (token, user_id, anchor, saved["activity_revision"], zone, instant(anchor + 30000)),
        )
        return {"available": True, "window_id": str(token), "duration_ms": 30000}


def add_days(conn: Any, user_id: int, intervals: list[list[int]], zone: str, revision: int) -> None:
    for start, right in intervals:
        left = start
        while left < right:
            day = instant(left).astimezone(ZoneInfo(zone)).date()
            boundary = min(right, milliseconds(next_midnight(day, zone)))
            conn.execute(
                """INSERT INTO user_activity_days(user_id,local_date,timezone,active_ms,revision)
                            VALUES (%s,%s,%s,%s,%s) ON CONFLICT(user_id,local_date,timezone)
                            DO UPDATE SET active_ms=user_activity_days.active_ms+EXCLUDED.active_ms,
                            revision=GREATEST(user_activity_days.revision,EXCLUDED.revision)""",
                (user_id, day, zone, boundary - left, revision),
            )
            left = boundary


def heartbeat(
    user_id: int, payload: ActivityHeartbeat, *, database_url: str | None = None
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        lock_account(conn, user_id)
        now = utc_now()
        now_ms = milliseconds(now)
        rate_limit(conn, user_id, now_ms)
        saved = enabled_or_invalidate(conn, user_id)
        if saved is None:
            return {"available": False, "reason": "measurement_disabled"}
        row = conn.execute(
            "SELECT * FROM user_activity_windows WHERE id=%s AND user_id=%s",
            (payload.window_id, user_id),
        ).fetchone()
        digest = sha256(f"{payload.start_ms}:{payload.end_ms}".encode()).hexdigest()
        error = None
        if not row:
            error = "activity_window_invalid"
        elif now_ms >= row["issued_ms"] + 120000 or row["revision"] != saved["activity_revision"]:
            error = "activity_window_expired"
        elif row["receipt"] is not None:
            if digest != row["payload_hash"]:
                error = "activity_payload_conflict"
            else:
                return dict(row["receipt"])
        elif now >= row["expires_at"] or row["issued_ms"] + payload.end_ms > now_ms:
            error = "activity_window_expired_or_future"
        if error:
            conn.commit()  # Persist rejected-request rate accounting, never partial eligibility.
            raise HTTPException(409, error)
        total_row = conn.execute(
            "SELECT * FROM user_activity_totals WHERE user_id=%s", (user_id,)
        ).fetchone()
        union = [
            [max(a, now_ms - 120000), b]
            for a, b in total_row["recent_union"]
            if b > now_ms - 120000
        ]
        left, right = row["issued_ms"] + payload.start_ms, row["issued_ms"] + payload.end_ms
        delta = uncovered(left, right, union)
        accepted = sum(b - a for a, b in delta)
        total = total_row["total_ms"] + accepted
        add_days(conn, user_id, delta, row["timezone"], row["revision"])
        conn.execute(
            """UPDATE user_activity_totals SET total_ms=%s,
                        measured_since=COALESCE(measured_since,%s),recent_union=%s,union_updated_at=%s
                        WHERE user_id=%s""",
            (total, instant(left), Jsonb(merge([*union, [left, right]])), now, user_id),
        )
        awards = award_rewards(
            conn,
            user_id,
            cause_key=f"activity:{sha256(payload.window_id.bytes).hexdigest()}",
            origin="live",
            earned_at=now,
            candidates=[
                {
                    "key": f"active_time_{n}",
                    "criteria_version": 1,
                    "progress": total // 1000,
                    "target": n,
                }
                for n in TIME_TARGETS
                if total >= n * 1000
            ],
        )
        result = {
            **snapshot(conn, user_id),
            **awards,
            "accepted_ms": accepted,
            "window_id": str(payload.window_id),
        }
        conn.execute(
            "UPDATE user_activity_windows SET payload_hash=%s,receipt=%s WHERE id=%s",
            (digest, Jsonb(result), payload.window_id),
        )
        return result


def cleanup_activity(*, database_url: str | None = None) -> None:
    """Minute job; only expired transient data and 400-day aggregates, never rewards/totals."""
    init_db(database_url=database_url)
    now = utc_now()
    stale_rate_minute = milliseconds(now) // 60000 - 1
    with connect(database_url=database_url) as conn:
        ids = conn.execute(
            """SELECT user_id FROM user_activity_windows WHERE expires_at<=%s
            UNION SELECT user_id FROM user_activity_totals
            WHERE union_updated_at<=%s OR (rate_count>0 AND rate_minute<%s)
            UNION SELECT user_id FROM user_activity_days
            WHERE local_date < (%s AT TIME ZONE timezone)::date - 399 ORDER BY user_id""",
            (
                now - timedelta(seconds=90),
                now - timedelta(seconds=120),
                stale_rate_minute,
                now,
            ),
        ).fetchall()
    for row in ids:
        with connect(database_url=database_url) as conn:
            # Match writer ordering; never hold a totals/day row while waiting for its account.
            conn.execute("SELECT pg_advisory_xact_lock(1623,%s)", (row["user_id"],))
            uid = row["user_id"]
            conn.execute(
                "DELETE FROM user_activity_windows WHERE user_id=%s AND expires_at<=%s",
                (uid, now - timedelta(seconds=90)),
            )
            conn.execute(
                "UPDATE user_activity_totals SET recent_union='[]',union_updated_at=NULL "
                "WHERE user_id=%s AND union_updated_at<=%s",
                (uid, now - timedelta(seconds=120)),
            )
            conn.execute(
                "UPDATE user_activity_totals SET rate_minute=0,rate_count=0 "
                "WHERE user_id=%s AND rate_minute<%s",
                (uid, stale_rate_minute),
            )
            deleted = conn.execute(
                "DELETE FROM user_activity_days "
                "WHERE user_id=%s AND local_date < (%s AT TIME ZONE timezone)::date - 399 "
                "RETURNING local_date",
                (uid, now),
            ).fetchone()
            if deleted:
                conn.execute(
                    "UPDATE user_activity_totals SET coverage_flags=coverage_flags | %s "
                    "WHERE user_id=%s",
                    (RETENTION_UNKNOWN, uid),
                )
