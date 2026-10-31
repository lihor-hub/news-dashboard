"""Derive reading streaks and award local achievements."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from news_dashboard.db import connect, init_db

QUALIFYING_ACTIVITY = "days with a finished article or article dwell event"


@dataclass(frozen=True)
class AchievementDefinition:
    key: str
    title: str
    description: str
    target: int
    progress: Callable[[dict[str, int]], int]


ACHIEVEMENTS: tuple[AchievementDefinition, ...] = (
    AchievementDefinition(
        key="seven_day_streak",
        title="Legacy reading streak (7 days)",
        description="Retired criterion; previously earned rewards remain.",
        target=7,
        progress=lambda stats: stats["current_streak_days"],
    ),
    AchievementDefinition(
        key="hundred_articles_read",
        title="100 articles read",
        description="Mark 100 articles as done.",
        target=100,
        progress=lambda stats: stats["articles_read"],
    ),
    AchievementDefinition(
        key="first_quiz_passed",
        title="First quiz passed",
        description="Submit a quiz with at least one correct answer.",
        target=1,
        progress=lambda stats: stats["passed_quizzes"],
    ),
    AchievementDefinition(
        key="inbox_zero",
        title="Inbox zero (retired)",
        description="Retired criterion; previously earned rewards remain.",
        target=1,
        progress=lambda stats: 1 if stats["today_articles"] == 0 else 0,
    ),
)


def _utc_today(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).date()


def _consecutive_run(active_days: set[date], start: date) -> int:
    count = 0
    day = start
    while day in active_days:
        count += 1
        day -= timedelta(days=1)
    return count


def _longest_run(active_days: set[date]) -> int:
    longest = 0
    for day in active_days:
        if day - timedelta(days=1) not in active_days:
            run = 0
            cursor = day
            while cursor in active_days:
                run += 1
                cursor += timedelta(days=1)
            longest = max(longest, run)
    return longest


def active_reading_days(
    user_id: int,
    *,
    database_url: str | None = None,
    connection: Any = None,
) -> set[date]:
    if connection is None:
        init_db(database_url=database_url)
    with (
        nullcontext(connection)
        if connection is not None
        else connect(database_url=database_url) as conn
    ):
        rows = conn.execute(
            """
            SELECT DISTINCT activity_day
            FROM (
              SELECT (created_at AT TIME ZONE 'UTC')::date AS activity_day
              FROM user_events
              WHERE user_id = %s
                AND event_type IN ('article_open', 'article_close')
                AND article_id IS NOT NULL
              UNION
              SELECT (done_at AT TIME ZONE 'UTC')::date AS activity_day
              FROM user_article_state
              WHERE user_id = %s
                AND state = 'done'
                AND done_at IS NOT NULL
            ) days
            ORDER BY activity_day
            """,
            (user_id, user_id),
        ).fetchall()
    return {row["activity_day"] for row in rows}


def get_streak(
    user_id: int,
    *,
    now: datetime | None = None,
    database_url: str | None = None,
    connection: Any = None,
) -> dict[str, Any]:
    days = active_reading_days(user_id, database_url=database_url, connection=connection)
    today = _utc_today(now)
    if not days:
        return {
            "current_streak_days": 0,
            "longest_streak_days": 0,
            "last_active_date": None,
            "active_days": [],
            "qualifying_activity": QUALIFYING_ACTIVITY,
        }

    last_active = max(days)
    if last_active == today:
        current = _consecutive_run(days, today)
    elif last_active == today - timedelta(days=1):
        current = _consecutive_run(days, last_active)
    else:
        current = 0

    return {
        "current_streak_days": current,
        "longest_streak_days": _longest_run(days),
        "last_active_date": last_active.isoformat(),
        "active_days": [day.isoformat() for day in sorted(days, reverse=True)[:30]],
        "qualifying_activity": QUALIFYING_ACTIVITY,
    }


def _achievement_stats(
    user_id: int,
    *,
    now: datetime | None = None,
    database_url: str | None = None,
) -> dict[str, int]:
    streak = get_streak(user_id, now=now, database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            SELECT
              (
                SELECT COUNT(*)
                FROM user_read_credits
                WHERE user_id = %s
              ) AS articles_read,
              (
                SELECT COUNT(*)
                FROM user_quizzes
                WHERE user_id = %s AND submitted_at IS NOT NULL AND COALESCE(score, 0) > 0
              ) AS passed_quizzes,
              (
                SELECT COUNT(*)
                FROM articles
                WHERE state = 'today'
              ) AS today_articles
            """,
            (user_id, user_id),
        ).fetchone()
    return {
        "current_streak_days": int(streak["current_streak_days"]),
        "articles_read": int(row["articles_read"]),
        "passed_quizzes": int(row["passed_quizzes"]),
        "today_articles": int(row["today_articles"]),
    }


def list_achievements(
    user_id: int,
    *,
    now: datetime | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(database_url=database_url)
    stats = _achievement_stats(user_id, now=now, database_url=database_url)
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM user_achievements
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()

    unlocked = {row["achievement_key"]: row["unlocked_at"] for row in rows}
    items = [
        {
            "key": definition.key,
            "title": definition.title,
            "description": definition.description,
            "unlocked": definition.key in unlocked,
            "unlocked_at": unlocked[definition.key].isoformat()
            if definition.key in unlocked
            else None,
            "progress": min(definition.progress(stats), definition.target),
            "target": definition.target,
        }
        for definition in ACHIEVEMENTS
    ]
    known = {definition.key for definition in ACHIEVEMENTS}
    from news_dashboard.reading_progress.rewards import descriptor

    items.extend(descriptor(row) for row in rows if row["achievement_key"] not in known)
    return items
