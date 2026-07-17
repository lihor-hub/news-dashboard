"""Database and transport operations for briefing-email actions."""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone, tzinfo
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from news_dashboard.briefing_email.rendering import render_briefing_email
from news_dashboard.briefing_email.tokens import make_unsubscribe_token
from news_dashboard.db import connect, row_to_dict
from news_dashboard.email import send_email

_COOLDOWN_SECONDS = 60.0
_COOLDOWN_MAX_ENTRIES = 10_000
_MISSING_EMAIL = "missing_email"
_GUEST_ACCOUNT = "guest_account"
_MISSING_BRIEFING = "missing_briefing"
_DELIVERY_FAILED = "delivery_failed"
_preview_sent_at: OrderedDict[tuple[str, int], float] = OrderedDict()
_preview_lock = threading.Lock()


class PreviewUnavailableError(RuntimeError):
    """Raised when a preview cannot be created from account state."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PreviewCooldownError(RuntimeError):
    """Raised when a user requests another preview inside the cooldown."""


def unsubscribe_user(user_id: int, *, database_url: str | None = None) -> bool:
    """Disable scheduled briefing email for a user, idempotently."""
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE users
            SET briefing_email_enabled = FALSE
            WHERE id = %s
            RETURNING id
            """,
            (user_id,),
        ).fetchone()
    return row is not None


def _claim_preview_cooldown(user_id: int) -> None:
    key = ("briefing_email_preview", user_id)
    now = time.monotonic()
    with _preview_lock:
        previous = _preview_sent_at.get(key)
        if previous is not None and now - previous < _COOLDOWN_SECONDS:
            raise PreviewCooldownError
        _preview_sent_at[key] = now
        _preview_sent_at.move_to_end(key)
        while len(_preview_sent_at) > _COOLDOWN_MAX_ENTRIES:
            _preview_sent_at.popitem(last=False)


def _release_preview_cooldown(user_id: int) -> None:
    with _preview_lock:
        _preview_sent_at.pop(("briefing_email_preview", user_id), None)


def _base_url() -> str:
    return (
        os.getenv("NEWS_DASHBOARD_BASE_URL")
        or os.getenv("NEWS_DASHBOARD_URL")
        or "http://localhost:5173"
    ).rstrip("/")


def _load_preview(database_url: str | None, user_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    with connect(database_url=database_url) as conn:
        user_row = conn.execute(
            "SELECT email, briefing_timezone, is_guest FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
        briefing_row = conn.execute(
            """
            SELECT id, title, summary, content, created_at
            FROM briefings
            WHERE user_id = %s AND status = 'complete'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if user_row is None or not str(user_row["email"] or "").strip():
        raise PreviewUnavailableError(_MISSING_EMAIL)
    if bool(user_row["is_guest"]):
        raise PreviewUnavailableError(_GUEST_ACCOUNT)
    if briefing_row is None:
        raise PreviewUnavailableError(_MISSING_BRIEFING)
    return row_to_dict(user_row), row_to_dict(briefing_row)


def send_preview(user_id: int, *, database_url: str | None = None) -> bool:
    """Render and send the latest complete briefing without touching schedule state."""
    user, briefing = _load_preview(database_url, user_id)
    _claim_preview_cooldown(user_id)
    try:
        timezone_name = str(user.get("briefing_timezone") or "UTC")
        try:
            zone: tzinfo = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            timezone_name = "UTC"
            zone = timezone.utc
        base_url = _base_url()
        token = make_unsubscribe_token(user_id)
        unsubscribe_url = f"{base_url}/email/briefing/unsubscribe?token={quote(token, safe='')}"
        briefing_id = int(briefing["id"])
        rendered = render_briefing_email(
            briefing,
            local_date=datetime.now(zone).date(),
            timezone_name=timezone_name,
            briefing_url=f"{base_url}/briefings/{briefing_id}",
            preferences_url=f"{base_url}/settings/notifications",
            unsubscribe_url=unsubscribe_url,
        )
        error = send_email(
            recipient=str(user["email"]).strip(),
            subject=rendered.subject,
            text_body=rendered.text_body,
            html_body=rendered.html_body,
            headers={
                "List-Unsubscribe": f"<{unsubscribe_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
    except Exception:
        _release_preview_cooldown(user_id)
        raise
    if error is not None:
        _release_preview_cooldown(user_id)
        raise PreviewUnavailableError(_DELIVERY_FAILED)
    return True
