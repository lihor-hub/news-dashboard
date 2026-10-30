"""Shared permanent award insertion and exact-target presentation authority.

Call award_rewards with the caller's connection and account advisory lock held.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from news_dashboard.db import connect, init_db

DAILY_TARGETS = (3, 7, 14, 30, 100)


def descriptor(row: Any) -> dict[str, Any]:
    key = row["achievement_key"]
    target = (
        int(key.removeprefix("daily_streak_"))
        if key in {f"daily_streak_{n}" for n in DAILY_TARGETS}
        else None
    )
    recorded = row["unlocked_at"].isoformat()
    title = f"{target}-day daily streak" if target else key.replace("_", " ")
    if key == "seven_day_streak":
        title = "Legacy reading streak (7 days)"
    return {
        "key": key,
        "title": title,
        "description": f"Visit on {target} consecutive saved-local dates."
        if target
        else "Previously earned reward",
        "unlocked": True,
        "unlocked_at": recorded,
        "recorded_at": recorded,
        "earned_at": row["earned_at"].isoformat() if row["earned_at"] else None,
        "origin": row["origin"],
        "date_precision": "exact" if row["earned_at"] else "unknown",
        "criteria_version": row["metadata"].get("criteria_version", 1),
        "progress": target or row["metadata"].get("progress", 0),
        "target": target,
        "href": f"/reading-dna?reward={quote(key, safe='')}#progress",
        "retired": target is None,
        "metadata": row["metadata"],
    }


def award_rewards(
    conn: Any,
    user_id: int,
    *,
    cause_key: str,
    origin: str,
    earned_at: datetime | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if origin not in ("live", "historical", "import", "legacy") or (
        (origin == "live") != (earned_at is not None)
    ):
        msg = "Invalid award provenance"
        raise ValueError(msg)
    inserted = []
    for candidate in candidates:
        target = candidate["target"]
        if (
            target not in DAILY_TARGETS
            or candidate["key"] != f"daily_streak_{target}"
            or candidate["criteria_version"] != 1
            or candidate["progress"] < target
        ):
            msg = "Unknown or ineligible reward candidate"
            raise ValueError(msg)
        row = conn.execute(
            """INSERT INTO user_achievements(
                user_id, achievement_key, origin, earned_at, unlocked_at, metadata)
              VALUES (%s,%s,%s,%s,clock_timestamp(),%s)
              ON CONFLICT(user_id,achievement_key) DO NOTHING RETURNING achievement_key""",
            (user_id, candidate["key"], origin, earned_at, Jsonb(candidate)),
        ).fetchone()
        if row:
            inserted.append(row["achievement_key"])
    group_id = None
    if inserted and origin == "live":
        group_id = conn.execute(
            """INSERT INTO user_reward_groups(id,user_id,source_key,kind,recorded_at)
              VALUES (%s,%s,%s,'live',%s) ON CONFLICT(user_id,source_key)
              DO UPDATE SET source_key=EXCLUDED.source_key RETURNING id""",
            (uuid4(), user_id, cause_key, earned_at),
        ).fetchone()["id"]
        conn.execute(
            """UPDATE user_achievements SET reward_group_id=%s
               WHERE user_id=%s AND achievement_key=ANY(%s)""",
            (group_id, user_id, inserted),
        )
    return {"newly_unlocked": inserted, "reward_group_id": str(group_id) if group_id else None}


def daily_collection(user_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    from news_dashboard.reading_progress.daily import account

    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        user = account(conn, user_id)
        if user["is_guest"]:
            return {"items": [], "pending_reward_group_ids": []}
        rows = conn.execute(
            """SELECT * FROM user_achievements WHERE user_id=%s
               ORDER BY unlocked_at, achievement_key""",
            (user_id,),
        ).fetchall()
        items = [descriptor(row) for row in rows]
        keys = {row["achievement_key"] for row in rows}
        items.extend(
            {
                "key": f"daily_streak_{n}",
                "title": f"{n}-day daily streak",
                "description": f"Visit on {n} consecutive saved-local dates.",
                "unlocked": False,
                "target": n,
                "earned_at": None,
                "recorded_at": None,
                "origin": None,
                "date_precision": "unknown",
            }
            for n in DAILY_TARGETS
            if f"daily_streak_{n}" not in keys
        )
        pending = conn.execute(
            """SELECT id FROM user_reward_groups WHERE user_id=%s
               AND kind='live' AND claimed_at IS NULL ORDER BY recorded_at,id LIMIT 20""",
            (user_id,),
        ).fetchall()
        return {"items": items, "pending_reward_group_ids": [str(r["id"]) for r in pending]}


def claim_reward(
    user_id: int, group_id: Any, *, acknowledge: bool = False, database_url: str | None = None
) -> dict[str, Any]:
    from news_dashboard.reading_progress.daily import lock_account, utc_now

    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        lock_account(conn, user_id)
        group = conn.execute(
            "SELECT * FROM user_reward_groups WHERE user_id=%s AND id=%s", (user_id, group_id)
        ).fetchone()
        if not group:
            raise HTTPException(404, "Not found")
        if group["kind"] != "live":
            raise HTTPException(409, "wrong_claim_kind")
        if acknowledge:
            if not group["claimed_at"]:
                raise HTTPException(409, "not_claimed")
            conn.execute(
                """UPDATE user_reward_groups SET acknowledged_at=COALESCE(acknowledged_at,%s)
                   WHERE id=%s AND user_id=%s""",
                (utc_now(), group_id, user_id),
            )
            return {"acknowledged": True}
        result = {
            "show": False,
            "reason": "already_consumed",
            "target": {"group_id": str(group_id)},
            "authorization": {"welcome": False, "history": False, "rewards": False},
            "welcome": None,
            "history": None,
            "rewards": [],
        }
        if group["claimed_at"]:
            return result
        conn.execute(
            "UPDATE user_reward_groups SET claimed_at=%s WHERE user_id=%s AND id=%s",
            (utc_now(), user_id, group_id),
        )
        rows = conn.execute(
            """SELECT * FROM user_achievements WHERE user_id=%s AND reward_group_id=%s
               ORDER BY achievement_key""",
            (user_id, group_id),
        ).fetchall()
        return {
            **result,
            "show": True,
            "reason": "claimed",
            "authorization": {"welcome": False, "history": False, "rewards": True},
            "rewards": [descriptor(row) for row in rows],
        }
