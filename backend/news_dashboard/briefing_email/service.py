"""Database and transport operations for briefing-email actions."""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from news_dashboard.briefing_email.rendering import render_briefing_email
from news_dashboard.briefing_email.tokens import make_unsubscribe_token
from news_dashboard.db import connect, row_to_dict
from news_dashboard.email import send_email, smtp_configured

_COOLDOWN_SECONDS = 60.0
_COOLDOWN_MAX_ENTRIES = 10_000
_MISSING_EMAIL = "missing_email"
_GUEST_ACCOUNT = "guest_account"
_MISSING_BRIEFING = "missing_briefing"
_DELIVERY_FAILED = "delivery_failed"
_preview_sent_at: OrderedDict[tuple[str, int], float] = OrderedDict()
_preview_lock = threading.Lock()
_STALE_CLAIM_AFTER = timedelta(minutes=30)
_RETRY_DELAY = timedelta(minutes=15)


@dataclass(frozen=True)
class Delivery:
    """Persistent scheduled-delivery state."""

    id: int
    user_id: int
    local_delivery_date: date
    status: str
    briefing_id: int | None
    attempt_count: int
    next_attempt_at: datetime | None


@dataclass(frozen=True)
class DeliveryOutcome:
    """Safe result returned to the scheduler for one channel attempt."""

    status: str
    delivery: Delivery
    briefing: dict[str, Any] | None = None


def _delivery(row: Any) -> Delivery:
    data = row_to_dict(row)
    return Delivery(
        id=int(data["id"]),
        user_id=int(data["user_id"]),
        local_delivery_date=data["local_delivery_date"],
        status=str(data["status"]),
        briefing_id=int(data["briefing_id"]) if data.get("briefing_id") is not None else None,
        attempt_count=int(data["attempt_count"]),
        next_attempt_at=data.get("next_attempt_at"),
    )


def claim_delivery(
    user_id: int,
    local_date: date,
    *,
    database_url: str | None = None,
) -> Delivery | None:
    """Atomically claim a user's local delivery date once."""
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefing_email_deliveries(user_id, local_delivery_date)
            VALUES (%s, %s)
            ON CONFLICT (user_id, local_delivery_date) DO NOTHING
            RETURNING id, user_id, local_delivery_date, status, briefing_id,
                      attempt_count, next_attempt_at
            """,
            (user_id, local_date),
        ).fetchone()
    return _delivery(row) if row is not None else None


def _acquire_delivery(
    user_id: int, local_date: date, now: datetime, database_url: str | None
) -> Delivery | None:
    claimed = claim_delivery(user_id, local_date, database_url=database_url)
    if claimed is not None:
        return claimed
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE briefing_email_deliveries
            SET status = 'claimed', claimed_at = %s, updated_at = %s,
                next_attempt_at = NULL, error_code = NULL, error_message = NULL
            WHERE user_id = %s AND local_delivery_date = %s
              AND ((status = 'claimed' AND claimed_at <= %s)
                   OR (status = 'retryable_failed' AND next_attempt_at <= %s))
            RETURNING id, user_id, local_delivery_date, status, briefing_id,
                      attempt_count, next_attempt_at
            """,
            (now, now, user_id, local_date, now - _STALE_CLAIM_AFTER, now),
        ).fetchone()
    return _delivery(row) if row is not None else None


def _set_delivery(  # noqa: PLR0913  # explicit transition fields keep SQL updates auditable
    delivery_id: int,
    status: str,
    *,
    database_url: str | None,
    briefing_id: int | None = None,
    now: datetime,
    error_code: str | None = None,
    next_attempt_at: datetime | None = None,
    sent: bool = False,
) -> Delivery:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE briefing_email_deliveries
            SET status = %s, briefing_id = COALESCE(%s, briefing_id),
                attempt_count = attempt_count + CASE WHEN %s = 'sending' THEN 1 ELSE 0 END,
                next_attempt_at = %s, error_code = %s, error_message = %s,
                sent_at = CASE WHEN %s THEN %s ELSE sent_at END, updated_at = %s
            WHERE id = %s
            RETURNING id, user_id, local_delivery_date, status, briefing_id,
                      attempt_count, next_attempt_at
            """,
            (
                status,
                briefing_id,
                status,
                next_attempt_at,
                error_code,
                error_code,
                sent,
                now,
                now,
                delivery_id,
            ),
        ).fetchone()
    if row is None:
        msg = "Delivery state transition lost its row"
        raise RuntimeError(msg)
    return _delivery(row)


def _local_day_bounds(local_date: date, zone: tzinfo) -> tuple[datetime, datetime]:
    start = datetime.combine(local_date, datetime.min.time(), tzinfo=zone)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _find_local_day_briefing(
    user_id: int, local_date: date, zone: tzinfo, database_url: str | None
) -> dict[str, Any] | None:
    start, end = _local_day_bounds(local_date, zone)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            SELECT id, title, summary, content, created_at, since_at, until_at, status
            FROM briefings
            WHERE user_id = %s AND status = 'complete'
              AND until_at >= %s AND until_at < %s
            ORDER BY until_at DESC, id DESC LIMIT 1
            """,
            (user_id, start, end),
        ).fetchone()
    return row_to_dict(row) if row is not None else None


def deliver_daily_briefing(  # noqa: PLR0911  # terminal ledger states return immediately
    user_id: int,
    *,
    now: datetime | None = None,
    database_url: str | None = None,
) -> DeliveryOutcome:
    """Generate or reuse and deliver today's canonical briefing at most once."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        msg = "now must be timezone-aware"
        raise ValueError(msg)
    with connect(database_url=database_url) as conn:
        user_row = conn.execute(
            "SELECT email, briefing_timezone FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    timezone_name = str(user_row["briefing_timezone"] or "UTC") if user_row else "UTC"
    try:
        zone: tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        timezone_name = "UTC"
        zone = timezone.utc
    local_date = instant.astimezone(zone).date()
    delivery = _acquire_delivery(user_id, local_date, instant, database_url)
    if delivery is None:
        with connect(database_url=database_url) as conn:
            existing = conn.execute(
                """
                SELECT id, user_id, local_delivery_date, status, briefing_id,
                       attempt_count, next_attempt_at
                FROM briefing_email_deliveries
                WHERE user_id = %s AND local_delivery_date = %s
                """,
                (user_id, local_date),
            ).fetchone()
        if existing is None:
            msg = "Delivery claim disappeared"
            raise RuntimeError(msg)
        current = _delivery(existing)
        return DeliveryOutcome(current.status, current)

    from news_dashboard.briefings.service import generate_briefing

    briefing = _find_local_day_briefing(user_id, local_date, zone, database_url)
    if briefing is None:
        try:
            briefing = generate_briefing(
                database_url=database_url,
                user_id=user_id,
                langfuse_session_id=f"daily-email:{user_id}:{local_date.isoformat()}",
                langfuse_tags=["daily-email", "briefing"],
            )
        except Exception:
            failed = _set_delivery(
                delivery.id,
                "retryable_failed",
                database_url=database_url,
                now=instant,
                error_code="generation_failed",
                next_attempt_at=instant + _RETRY_DELAY,
            )
            return DeliveryOutcome(failed.status, failed)
    if briefing.get("status") == "no_candidates":
        skipped = _set_delivery(delivery.id, "skipped", database_url=database_url, now=instant)
        return DeliveryOutcome(skipped.status, skipped, briefing)

    briefing_id = int(briefing["id"])
    rendered_state = _set_delivery(
        delivery.id, "rendered", database_url=database_url, now=instant, briefing_id=briefing_id
    )
    base_url = _base_url()
    token = make_unsubscribe_token(user_id)
    unsubscribe_url = f"{base_url}/email/briefing/unsubscribe?token={quote(token, safe='')}"
    rendered = render_briefing_email(
        briefing,
        local_date=local_date,
        timezone_name=timezone_name,
        briefing_url=f"{base_url}/briefings/{briefing_id}",
        preferences_url=f"{base_url}/settings/notifications",
        unsubscribe_url=unsubscribe_url,
    )
    with connect(database_url=database_url) as conn:
        consent = conn.execute(
            "SELECT email, briefing_email_enabled FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    if consent is None or not bool(consent["briefing_email_enabled"]):
        stopped = _set_delivery(delivery.id, "unsubscribed", database_url=database_url, now=instant)
        return DeliveryOutcome(stopped.status, stopped, briefing)
    recipient = str(consent["email"] or "").strip()
    if not recipient or not smtp_configured():
        failed = _set_delivery(
            delivery.id,
            "permanent_failed",
            database_url=database_url,
            now=instant,
            error_code="smtp_not_configured" if recipient else "missing_email",
        )
        return DeliveryOutcome(failed.status, failed, briefing)

    sending = _set_delivery(rendered_state.id, "sending", database_url=database_url, now=instant)
    error = send_email(
        recipient=recipient,
        subject=rendered.subject,
        text_body=rendered.text_body,
        html_body=rendered.html_body,
        headers={
            "List-Unsubscribe": f"<{unsubscribe_url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    if error is None:
        complete = _set_delivery(
            sending.id, "sent", database_url=database_url, now=instant, sent=True
        )
        return DeliveryOutcome(complete.status, complete, briefing)
    retryable = error == "smtp_error"
    failed = _set_delivery(
        sending.id,
        "retryable_failed" if retryable else "permanent_failed",
        database_url=database_url,
        now=instant,
        error_code=error,
        next_attempt_at=instant + _RETRY_DELAY if retryable else None,
    )
    return DeliveryOutcome(failed.status, failed, briefing)


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
