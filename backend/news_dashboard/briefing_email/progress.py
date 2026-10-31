"""Read-only, recipient-bound personal progress for existing mail attempts."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from news_dashboard.db import connect
from news_dashboard.email_theme import EMAIL_COLORS, compact_text
from news_dashboard.reading_progress import daily, topics
from news_dashboard.reading_progress.rewards import reward_catalog

logger = logging.getLogger(__name__)


def mailbox(value: str) -> str | None:
    """One unambiguous addr-spec; never guess aliases or recipient lists."""
    if any(c in value for c in "\r\n"):
        return None
    try:
        addresses = getaddresses([value], strict=True)
    except (TypeError, ValueError):
        return None
    if len(addresses) != 1:
        return None
    address = addresses[0][1]
    if address.count("@") != 1 or any(c.isspace() for c in address):
        return None
    local, domain = address.rsplit("@", 1)
    return f"{local}@{domain.lower()}" if local and domain else None


def recipient_matches(conn: Any, user_id: int, recipient: str) -> bool:
    expected = mailbox(recipient)
    if expected is None:
        return False
    # Case-insensitive collision detection is deliberately stricter than ownership matching.
    rows = conn.execute(
        "SELECT id, email, is_guest FROM users WHERE lower(trim(email)) = lower(%s)",
        (expected,),
    ).fetchall()
    return (
        len(rows) == 1
        and rows[0]["id"] == user_id
        and not rows[0]["is_guest"]
        and mailbox(str(rows[0]["email"] or "")) == expected
    )


def progress_recipient_matches(
    user_id: int, recipient: str, *, database_url: str | None = None
) -> bool:
    """Fail closed for optional progress without interrupting the existing news send."""
    try:
        with connect(database_url=database_url) as conn:
            return recipient_matches(conn, user_id, recipient)
    except Exception:
        logger.warning("Email progress unavailable; omitted")
        return False


def _instant(value: object) -> datetime | None:
    try:
        instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return instant if instant.tzinfo is not None and instant.utcoffset() is not None else None


def select_progress(
    user_id: int,
    *,
    recipient: str,
    base_url: str,
    briefing: dict[str, Any] | None = None,
    now: datetime | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Select once per attempt for both MIME parts; optional failures omit only progress."""
    try:
        instant = now or datetime.now(timezone.utc)
        start = (
            _instant(briefing.get("since_at"))
            if briefing is not None
            else instant - timedelta(days=1)
        )
        end = _instant(briefing.get("until_at")) if briefing is not None else instant
        if not start or not end or not start < end <= instant:
            return None
        href = f"{base_url.rstrip('/')}/reading-dna#progress"
        if not safe_progress_url(href):
            return None
        with connect(database_url=database_url) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if not recipient_matches(conn, user_id, recipient):
                return None
            user = daily.account(conn, user_id)
            zone_name = daily.effective_zone(user)
            zone = ZoneInfo(zone_name)
            catalog = reward_catalog()
            keys = list(catalog)
            rows = conn.execute(
                """WITH definitions AS (
                     SELECT * FROM unnest(%s::text[], %s::text[], %s::int[])
                       AS d(key, topic, target)
                   ), ranked AS (
                     SELECT a.achievement_key, a.earned_at,
                       row_number() OVER (
                         PARTITION BY coalesce(d.topic, d.key)
                         ORDER BY d.target DESC, a.earned_at DESC, a.achievement_key) AS rank
                     FROM user_achievements a JOIN definitions d ON d.key=a.achievement_key
                     JOIN user_reward_groups g ON g.id=a.reward_group_id AND g.user_id=a.user_id
                     WHERE a.user_id=%s AND a.origin='live' AND g.kind='live'
                       AND a.earned_at >= %s AND a.earned_at < %s
                   ) SELECT achievement_key, earned_at FROM ranked WHERE rank=1
                   ORDER BY earned_at DESC, achievement_key LIMIT 2""",
                (
                    keys,
                    [topics.reward_topic(key) for key in keys],
                    [catalog[key][0] for key in keys],
                    user_id,
                    start,
                    end,
                ),
            ).fetchall()
            titles = [
                compact_text(catalog[row["achievement_key"]][1], fallback="Reward", limit=120)
                for row in rows
            ]
            titles = [
                f"Approximately {title}"
                if row["achievement_key"].startswith("active_time_")
                else title
                for title, row in zip(titles, rows, strict=True)
            ]
            streak = (
                0 if titles else daily.snapshot(conn, user_id, user, instant)["current_streak_days"]
            )
            if not titles and streak < 3:
                return None

            def stamp(value: datetime) -> str:
                return value.astimezone(zone).strftime("%Y-%m-%d %H:%M %z")

            return {
                "titles": titles,
                "period": f"{stamp(start)} to {stamp(end)} ({zone_name}; end exclusive)",
                "streak": (
                    f"At preparation for sending on {stamp(instant)} ({zone_name}): "
                    f"{streak}-day daily streak."
                )
                if not titles
                else None,
                "href": href,
            }
    except Exception:
        # Optional personal content must not break news delivery or log private payloads.
        logger.warning("Email progress unavailable; omitted")
        return None


def safe_progress_url(value: object) -> bool:
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        return bool(
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and parsed.path == "/reading-dna"
            and not parsed.query
            and parsed.fragment == "progress"
        )
    except ValueError:
        return False


def render_progress(progress: dict[str, Any] | None, *, html: bool) -> str:
    """Shared dedicated partials, also used by the legacy multipart renderer."""
    if not progress or not safe_progress_url(progress.get("href")):
        return ""
    from news_dashboard.briefing_email.rendering import _ENVIRONMENT

    return _ENVIRONMENT.get_template(f"progress.{'html' if html else 'txt'}.j2").render(
        progress=progress, colors={name: color.email_hex for name, color in EMAIL_COLORS.items()}
    )
