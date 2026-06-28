"""Web Push notification helpers (VAPID via pywebpush)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

logger = logging.getLogger(__name__)

_DEFAULT_PUSH_TITLE = "Your daily brief is ready"


def generate_push_hook(briefing: dict[str, Any]) -> str:
    """Generate a punchy AI push notification hook from a briefing dict.

    Takes the briefing result from ``generate_briefing()`` (keys: ``title``,
    ``content`` → ``sections``).  Uses the free LLM gateway to produce a
    single engaging sentence (≤ 15 words) for the lock screen.  Falls back to
    a clean default if the LLM is not configured or the call fails.
    """
    title: str = briefing.get("title") or ""
    content: dict[str, Any] = briefing.get("content") or {}
    sections: list[dict[str, Any]] = content.get("sections") or []
    headlines = [s.get("title", "") for s in sections if s.get("title")][:3]

    fallback = f"Your daily brief: {title}" if title else _DEFAULT_PUSH_TITLE

    try:
        from news_dashboard.ai_client import free_llm_config, get_chat_client

        api_key, base_url = free_llm_config()
        if not api_key:
            return fallback

        client = get_chat_client(api_key=api_key, base_url=base_url)
        model = os.getenv("OPENAI_BRIEFING_MODEL", "gpt-4o-mini")

        if headlines:
            headline_block = "\n".join(f"- {h}" for h in headlines)
        else:
            headline_block = f"- {title}" if title else "(no headlines)"

        prompt = (
            "Write a single punchy mobile push notification hook (max 15 words) "
            "that entices the user to open their news briefing. "
            f"Top headlines:\n{headline_block}\n\n"
            "Reply with only the hook text, no quotes or punctuation at the end."
        )

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=40,
            temperature=0.7,
        )
        hook = (response.choices[0].message.content or "").strip()
        if hook:
            return hook
    except Exception:
        logger.warning("Push hook LLM generation failed; using default message")

    return fallback


PushDeliveryResult = Literal["sent", "skipped_not_configured", "temporary_failure", "gone"]


def _is_permanent_push_failure(exc: Exception) -> bool:
    """Return True if the exception represents a permanent failure (e.g. HTTP 404 or 410)."""
    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if status_code in (404, 410):
            return True
    return False


def get_vapid_public_key() -> str | None:
    """Return the VAPID public key (base64url-encoded) from env, or None if unset."""
    return os.getenv("VAPID_PUBLIC_KEY")


def _vapid_private_key() -> str:
    key = os.getenv("VAPID_PRIVATE_KEY")
    if not key:
        msg = "VAPID_PRIVATE_KEY environment variable not set"
        raise RuntimeError(msg)
    return key


def _vapid_claims() -> dict[str, str | int]:
    email = os.getenv("VAPID_EMAIL", "admin@example.com")
    return {"sub": f"mailto:{email}"}


def send_push_notification(
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    title: str,
    body: str,
    target_url: str | None = None,
    tag: str | None = None,
) -> PushDeliveryResult:
    """Send a single Web Push notification to the given subscription."""
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.warning("pywebpush not installed — push notification skipped")
        return "skipped_not_configured"

    data: dict[str, str] = {"title": title, "body": body}
    if target_url is not None:
        data["url"] = target_url
    if tag is not None:
        data["tag"] = tag
    payload = json.dumps(data)
    try:
        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            data=payload,
            vapid_private_key=_vapid_private_key(),
            vapid_claims=_vapid_claims(),
        )
        return "sent"
    except WebPushException as exc:
        if _is_permanent_push_failure(exc):
            logger.warning("Push notification to %s failed permanently: %s", endpoint[:40], exc)
            return "gone"
        logger.warning("Push notification to %s failed temporarily: %s", endpoint[:40], exc)
        return "temporary_failure"
    except RuntimeError:
        logger.warning("Push notification skipped: VAPID key not configured")
        return "skipped_not_configured"


def save_push_subscription(
    user_id: int,
    endpoint: str,
    p256dh: str,
    auth: str,
    *,
    database_url: str | None = None,
) -> None:
    """Upsert a push subscription for a user."""
    from news_dashboard.db import connect

    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO user_push_subscriptions (user_id, endpoint, p256dh_key, auth_key)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (endpoint) DO UPDATE
              SET user_id    = EXCLUDED.user_id,
                  p256dh_key = EXCLUDED.p256dh_key,
                  auth_key   = EXCLUDED.auth_key
            """,
            (user_id, endpoint, p256dh, auth),
        )


def delete_push_subscriptions(
    user_id: int,
    *,
    endpoint: str | None = None,
    database_url: str | None = None,
) -> None:
    """Remove push subscriptions for a user.  Deletes all if endpoint is None."""
    from news_dashboard.db import connect

    with connect(database_url=database_url) as conn:
        if endpoint is not None:
            conn.execute(
                "DELETE FROM user_push_subscriptions WHERE user_id = %s AND endpoint = %s",
                (user_id, endpoint),
            )
        else:
            conn.execute(
                "DELETE FROM user_push_subscriptions WHERE user_id = %s",
                (user_id,),
            )


def get_user_push_subscriptions(
    user_id: int,
    *,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    """Return all push subscriptions for a user."""
    from news_dashboard.db import connect, row_to_dict

    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT endpoint, p256dh_key, auth_key
            FROM user_push_subscriptions
            WHERE user_id = %s
            """,
            (user_id,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def send_push_for_user(
    user_id: int,
    title: str,
    body: str,
    *,
    target_url: str | None = None,
    tag: str | None = None,
    database_url: str | None = None,
) -> None:
    """Send a push notification to all subscriptions registered by a user."""
    subs = get_user_push_subscriptions(user_id, database_url=database_url)
    for sub in subs:
        result = send_push_notification(
            endpoint=sub["endpoint"],
            p256dh=sub["p256dh_key"],
            auth=sub["auth_key"],
            title=title,
            body=body,
            target_url=target_url,
            tag=tag,
        )
        if result == "gone":
            delete_push_subscriptions(
                user_id,
                endpoint=sub["endpoint"],
                database_url=database_url,
            )
