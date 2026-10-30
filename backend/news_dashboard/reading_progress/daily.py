"""Functional saved-local visit ledger; never inferred from reading or analytics."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

from news_dashboard.db import connect, init_db
from news_dashboard.reading_progress.rewards import award_rewards


class ProgressPreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    progress_timezone: str | None = None
    daily_welcome_enabled: StrictBool | None = None
    reward_animations_enabled: StrictBool | None = None

    @field_validator("progress_timezone")
    @classmethod
    def valid_zone(cls, value: str | None) -> str:
        if not isinstance(value, str) or not 1 <= len(value) <= 255:
            msg = "Use an IANA timezone, for example Europe/Bucharest"
            raise ValueError(msg)
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            msg = "Unknown IANA timezone"
            raise ValueError(msg) from exc
        return value

    @field_validator("daily_welcome_enabled", "reward_animations_enabled")
    @classmethod
    def not_null(cls, value: bool | None) -> bool:
        if value is None:
            msg = "Preference must be a boolean"
            raise ValueError(msg)
        return value


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def lock_account(conn: Any, user_id: int, *, mutation: bool = True) -> dict[str, Any]:
    conn.execute("SELECT pg_advisory_xact_lock(1623, %s)", (user_id,))
    return account(conn, user_id, mutation=mutation)


def account(conn: Any, user_id: int, *, mutation: bool = False) -> dict[str, Any]:
    row = conn.execute(
        """SELECT progress_timezone, briefing_timezone, daily_welcome_enabled,
                  reward_animations_enabled, is_guest FROM users WHERE id = %s""",
        (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(401, "Account not available")
    if mutation and row["is_guest"]:
        raise HTTPException(403, "progress_not_available")
    return dict(row)


def effective_zone(user: dict[str, Any]) -> str:
    zone: str | None = user["progress_timezone"]
    if zone:
        return zone
    try:
        briefing_zone: str = user["briefing_timezone"]
        ZoneInfo(briefing_zone)
        return briefing_zone
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        return "UTC"


def preferences(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "progress_timezone": effective_zone(user),
        "timezone_initialized": user["progress_timezone"] is not None,
        "daily_welcome_enabled": user["daily_welcome_enabled"],
        "reward_animations_enabled": user["reward_animations_enabled"],
    }


def next_midnight(day: date, zone: str) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, ZoneInfo(zone)).astimezone(
        timezone.utc
    )


def snapshot(conn: Any, user_id: int, user: dict[str, Any], now: datetime) -> dict[str, Any]:
    if user["is_guest"]:
        return {"available": False}
    zone = effective_zone(user)
    today = now.astimezone(ZoneInfo(zone)).date()
    state = conn.execute(
        "SELECT * FROM user_daily_visit_state WHERE user_id = %s", (user_id,)
    ).fetchone()
    rows = conn.execute(
        """SELECT * FROM user_daily_visits WHERE user_id = %s
           AND local_date BETWEEN %s AND %s ORDER BY local_date""",
        (user_id, today - timedelta(days=6), today),
    ).fetchall()
    visits = {r["local_date"]: r for r in rows}
    visit = visits.get(today)
    current = 0
    if state and state["last_credited_date"] in (today, today - timedelta(days=1)):
        current = state["current_streak_days"]
    target = (
        {"expected_visit_date": today.isoformat()}
        if visit
        and visit["credited"]
        and visit["welcome_status"] == "pending"
        and user["daily_welcome_enabled"]
        else None
    )
    return {
        "available": True,
        "timezone": zone,
        "timezone_initialized": user["progress_timezone"] is not None,
        "local_date": today.isoformat(),
        "server_now": now.isoformat(),
        "next_local_boundary_at": next_midnight(today, zone).isoformat(),
        "next_credit_at": state["next_credit_at"].isoformat()
        if state and state["next_credit_at"]
        else None,
        "current_streak_days": current,
        "best_streak_days": state["best_streak_days"] if state else 0,
        "visit_kind": visit["visit_kind"] if visit else None,
        "seven_days": [
            {
                "date": (d := today - timedelta(days=offset)).isoformat(),
                "visited": d in visits,
                "credited": bool(visits.get(d, {}).get("credited")),
            }
            for offset in range(6, -1, -1)
        ],
        "welcome_target": target,
        "newly_unlocked": [],
        "reward_group_id": None,
    }


def get_daily_streak(user_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        return snapshot(conn, user_id, account(conn, user_id), utc_now())


def record_visit(user_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        user = lock_account(conn, user_id)
        # Waiting across midnight must count the new day, not transaction start time.
        now = utc_now()
        zone = effective_zone(user)
        if user["progress_timezone"] is None:
            conn.execute("UPDATE users SET progress_timezone = %s WHERE id = %s", (zone, user_id))
            user["progress_timezone"] = zone
        day = now.astimezone(ZoneInfo(zone)).date()
        conn.execute(
            "INSERT INTO user_daily_visit_state(user_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (user_id,),
        )
        conn.execute(
            """INSERT INTO user_daily_visits(user_id, local_date, timezone, first_visited_at,
                  welcome_status, welcome_consumed_at) VALUES (%s,%s,%s,%s,%s,%s)
                  ON CONFLICT DO NOTHING""",
            (
                user_id,
                day,
                zone,
                now,
                "pending" if user["daily_welcome_enabled"] else "suppressed",
                None if user["daily_welcome_enabled"] else now,
            ),
        )
        state = conn.execute(
            "SELECT * FROM user_daily_visit_state WHERE user_id = %s", (user_id,)
        ).fetchone()
        last = state["last_credited_date"]
        awards: dict[str, Any] = {"newly_unlocked": [], "reward_group_id": None}
        if last is None or (day > last and now >= state["next_credit_at"]):
            continuing = last == day - timedelta(days=1)
            current = state["current_streak_days"] + 1 if continuing else 1
            kind = "first" if last is None else "continuing" if continuing else "restart"
            conn.execute(
                """UPDATE user_daily_visit_state SET last_credited_date=%s, current_streak_days=%s,
                    best_streak_days=GREATEST(best_streak_days,%s), next_credit_at=%s
                    WHERE user_id=%s""",
                (day, current, current, next_midnight(day, zone), user_id),
            )
            conn.execute(
                """UPDATE user_daily_visits SET credited=TRUE, visit_kind=%s
                   WHERE user_id=%s AND local_date=%s""",
                (kind, user_id, day),
            )
            awards = award_rewards(
                conn,
                user_id,
                cause_key=f"daily:{day}",
                origin="live",
                earned_at=now,
                candidates=[
                    {
                        "key": f"daily_streak_{n}",
                        "criteria_version": 1,
                        "progress": current,
                        "target": n,
                    }
                    for n in (3, 7, 14, 30, 100)
                    if current >= n
                ],
            )
        return {**snapshot(conn, user_id, user, now), **awards}


def get_preferences(user_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        return preferences(account(conn, user_id))


def update_preferences(conn: Any, user_id: int, patch: ProgressPreferencesPatch) -> dict[str, Any]:
    user = lock_account(conn, user_id)
    updates = patch.model_dump(exclude_unset=True)
    updates.setdefault("progress_timezone", effective_zone(user))
    # Keys are validated by the closed Pydantic schema, never interpolated client SQL.
    conn.execute(
        "UPDATE users SET " + ", ".join(f"{key}=%s" for key in updates) + " WHERE id=%s",
        (*updates.values(), user_id),
    )
    user.update(updates)
    if updates.get("daily_welcome_enabled") is False:
        now = utc_now()
        day = now.astimezone(ZoneInfo(effective_zone(user))).date()
        conn.execute(
            """UPDATE user_daily_visits SET welcome_status='suppressed', welcome_consumed_at=%s
                        WHERE user_id=%s AND local_date=%s AND welcome_status='pending'""",
            (now, user_id, day),
        )
    return preferences(user)


def save_preferences(
    user_id: int, patch: ProgressPreferencesPatch, *, database_url: str | None = None
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        return update_preferences(conn, user_id, patch)


def claim_presentation(  # noqa: PLR0911 - explicit losing receipts preserve bundle semantics
    user_id: int,
    expected_visit_date: date | None,
    historical_group_id: Any = None,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        user = lock_account(conn, user_id)
        history = None
        if historical_group_id:
            history = conn.execute(
                "SELECT * FROM user_reward_groups WHERE user_id=%s AND id=%s",
                (user_id, historical_group_id),
            ).fetchone()
            if not history:
                raise HTTPException(404, "Not found")
            if history["kind"] != "historical_intro":
                raise HTTPException(409, "wrong_claim_kind")
        elif expected_visit_date is None:
            raise HTTPException(422, "History target required for inline mode")
        now = utc_now()
        daily = snapshot(conn, user_id, user, now)
        result: dict[str, Any] = {
            "show": False,
            "reason": "not_eligible",
            "target": {
                "expected_visit_date": expected_visit_date.isoformat()
                if expected_visit_date
                else None,
                "historical_group_id": str(historical_group_id) if historical_group_id else None,
            },
            "authorization": {"welcome": False, "history": False, "rewards": False},
            "welcome": None,
            "history": None,
            "rewards": [],
        }
        if expected_visit_date is not None:
            if expected_visit_date.isoformat() != daily["local_date"]:
                return {**result, "reason": "stale_visit"}
            if not user["daily_welcome_enabled"]:
                return {**result, "reason": "disabled"}
            visit = conn.execute(
                "SELECT * FROM user_daily_visits WHERE user_id=%s AND local_date=%s",
                (user_id, expected_visit_date),
            ).fetchone()
            if not visit or not visit["credited"]:
                return result
            if visit["welcome_status"] != "pending":
                return {**result, "reason": "already_consumed"}
            conn.execute(
                """UPDATE user_daily_visits SET welcome_status='claimed', welcome_consumed_at=%s
                   WHERE user_id=%s AND local_date=%s""",
                (now, user_id, expected_visit_date),
            )
            result["authorization"]["welcome"] = True
            result["welcome"] = {**daily, "highlight_kind": "collection_summary"}
        elif user["daily_welcome_enabled"]:
            return result
        if history and history["claimed_at"] is None:
            conn.execute(
                "UPDATE user_reward_groups SET claimed_at=%s WHERE id=%s AND user_id=%s",
                (now, historical_group_id, user_id),
            )
            result["authorization"]["history"] = True
            result["history"] = {"group_id": str(historical_group_id), **history["summary"]}
        if any(result["authorization"].values()):
            return {**result, "show": True, "reason": "claimed"}
        return {**result, "reason": "already_consumed"}
