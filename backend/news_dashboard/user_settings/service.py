"""Business logic and PostgreSQL access for user preferences and settings."""

from __future__ import annotations

import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from news_dashboard.analytics import analytics_globally_enabled
from news_dashboard.briefing_email.service import public_base_url_configured
from news_dashboard.db import connect
from news_dashboard.email import smtp_configured
from news_dashboard.user_settings.models import NotificationSettingsUpdate

_BRIEFING_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_NOTIFICATION_COLS = (
    "briefing_time, briefing_push_enabled, briefing_timezone, recap_enabled, recap_day, "
    "briefing_include_reading_list, briefing_reading_list_limit, "
    "briefing_email_enabled, email, is_guest"
)
_RECAP_DAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})
_READING_LIST_LIMIT_MAX = 20


def preference_payload(preferences: Any) -> dict[str, Any]:
    """Serialize stored recommendation preferences for API responses."""
    return {
        "category_weights": preferences.category_weights,
        "novelty_weight": preferences.novelty_weight,
    }


def _notification_payload(row: Any, *, include_vapid_key: bool) -> dict[str, Any]:
    email = str(row["email"]).strip() if row["email"] is not None else ""
    result = {
        "briefing_time": row["briefing_time"] or "09:00",
        "briefing_timezone": row["briefing_timezone"] or "UTC",
        "push_enabled": bool(row["briefing_push_enabled"]),
        "email_enabled": bool(row["briefing_email_enabled"]),
        "email_address": email or None,
        "email_available": bool(email and not row["is_guest"]),
        "email_delivery_configured": smtp_configured() and public_base_url_configured(),
        "recap_enabled": bool(row["recap_enabled"]),
        "recap_day": row["recap_day"] or "mon",
        "briefing_include_reading_list": bool(row["briefing_include_reading_list"]),
        "briefing_reading_list_limit": row["briefing_reading_list_limit"] or 3,
    }
    if include_vapid_key:
        from news_dashboard.push import get_vapid_public_key

        result["vapid_public_key"] = get_vapid_public_key()
    return result


def get_notification_settings(user_id: int) -> dict[str, Any]:
    """Read notification preferences and public push configuration."""
    with connect() as conn:
        row = conn.execute(
            f"SELECT {_NOTIFICATION_COLS} FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    if row is None:
        msg = "user not found"
        raise LookupError(msg)
    return _notification_payload(row, include_vapid_key=True)


def _notification_updates(payload: NotificationSettingsUpdate) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if payload.briefing_time is not None:
        if not _BRIEFING_TIME_RE.match(payload.briefing_time):
            msg = "briefing_time must be HH:MM (00:00-23:59)"
            raise ValueError(msg)
        updates["briefing_time"] = payload.briefing_time
    if payload.push_enabled is not None:
        updates["briefing_push_enabled"] = payload.push_enabled
    if payload.email_enabled is not None:
        updates["briefing_email_enabled"] = payload.email_enabled
    if payload.briefing_timezone is not None:
        try:
            ZoneInfo(payload.briefing_timezone)
        except (ZoneInfoNotFoundError, KeyError):
            msg = "unknown timezone"
            raise ValueError(msg) from None
        updates["briefing_timezone"] = payload.briefing_timezone
    if payload.recap_enabled is not None:
        updates["recap_enabled"] = payload.recap_enabled
    if payload.recap_day is not None:
        if payload.recap_day not in _RECAP_DAYS:
            msg = "recap_day must be one of: " + ", ".join(sorted(_RECAP_DAYS))
            raise ValueError(msg)
        updates["recap_day"] = payload.recap_day
    if payload.briefing_include_reading_list is not None:
        updates["briefing_include_reading_list"] = payload.briefing_include_reading_list
    if payload.briefing_reading_list_limit is not None:
        if not 1 <= payload.briefing_reading_list_limit <= _READING_LIST_LIMIT_MAX:
            msg = f"briefing_reading_list_limit must be between 1 and {_READING_LIST_LIMIT_MAX}"
            raise ValueError(msg)
        updates["briefing_reading_list_limit"] = payload.briefing_reading_list_limit
    return updates


def update_notification_settings(
    user_id: int, payload: NotificationSettingsUpdate
) -> dict[str, Any]:
    """Validate, persist, and return notification preferences."""
    if payload.email_enabled:
        with connect() as conn:
            account = conn.execute(
                "SELECT email, is_guest FROM users WHERE id = %s", (user_id,)
            ).fetchone()
        if account is None:
            msg = "user not found"
            raise LookupError(msg)
        email = str(account["email"]).strip() if account["email"] is not None else ""
        if not email or account["is_guest"]:
            msg = "account email is required"
            raise ValueError(msg)
        if not smtp_configured():
            msg = "email delivery is not configured"
            raise ValueError(msg)
        if not public_base_url_configured():
            msg = "public application URL is not configured"
            raise ValueError(msg)

    updates = _notification_updates(payload)
    if updates:
        set_clauses = ", ".join(f"{key} = %s" for key in updates)
        with connect() as conn:
            conn.execute(
                f"UPDATE users SET {set_clauses} WHERE id = %s",
                [*updates.values(), user_id],
            )
    with connect() as conn:
        row = conn.execute(
            f"SELECT {_NOTIFICATION_COLS} FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    if row is None:
        msg = "user not found"
        raise LookupError(msg)
    return _notification_payload(row, include_vapid_key=False)


def get_analytics_settings(user_id: int) -> dict[str, bool]:
    """Read per-user analytics consent together with the global switch."""
    with connect() as conn:
        row = conn.execute(
            "SELECT analytics_enabled FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    return {
        "enabled": bool(row["analytics_enabled"]) if row else True,
        "global_enabled": analytics_globally_enabled(),
    }


def update_analytics_settings(user_id: int, *, enabled: bool) -> dict[str, bool]:
    """Persist per-user analytics consent."""
    with connect() as conn:
        conn.execute(
            "UPDATE users SET analytics_enabled = %s WHERE id = %s",
            (enabled, user_id),
        )
    return {"enabled": enabled, "global_enabled": analytics_globally_enabled()}
