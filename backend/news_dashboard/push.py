"""Web Push notification helpers (VAPID via pywebpush)."""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Literal
from urllib.parse import urlparse

import requests
from requests.structures import CaseInsensitiveDict

from news_dashboard.url_safety import (
    UnsafeUrlError,
    open_server_fetch_url,
    validate_server_fetch_url,
)

logger = logging.getLogger(__name__)

# Maximum lengths for push subscription fields
_MAX_ENDPOINT_LEN = 2083
_MAX_KEY_LEN = 256
_PUSH_DELIVERY_TIMEOUT_SECONDS = 15.0
_PUSH_RESPONSE_BYTE_CAP = 64 * 1024

# Base64url alphabet (no padding required)
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_\-]+=*$")


def validate_push_subscription(endpoint: str, p256dh: str, auth: str) -> None:
    """Raise ValueError if the subscription fields fail basic sanity checks.

    Checks performed:
    - endpoint is an HTTPS URL with a non-empty hostname
    - every endpoint DNS answer is publicly routable
    - endpoint and key lengths are within reasonable Web Push bounds
    - p256dh and auth are non-empty base64url-like strings
    """
    if len(endpoint) > _MAX_ENDPOINT_LEN:
        msg = "endpoint too long"
        raise ValueError(msg)
    if len(p256dh) > _MAX_KEY_LEN:
        msg = "p256dh too long"
        raise ValueError(msg)
    if len(auth) > _MAX_KEY_LEN:
        msg = "auth too long"
        raise ValueError(msg)

    parsed = urlparse(endpoint)
    if parsed.scheme != "https":
        msg = "endpoint must use the https scheme"
        raise ValueError(msg)
    hostname = parsed.hostname or ""
    if not hostname:
        msg = "endpoint must have a non-empty hostname"
        raise ValueError(msg)

    if not p256dh:
        msg = "p256dh must not be empty"
        raise ValueError(msg)
    if not auth:
        msg = "auth must not be empty"
        raise ValueError(msg)
    if not _BASE64URL_RE.match(p256dh):
        msg = "p256dh must be a base64url string"
        raise ValueError(msg)
    if not _BASE64URL_RE.match(auth):
        msg = "auth must be a base64url string"
        raise ValueError(msg)

    try:
        validate_server_fetch_url(endpoint)
    except UnsafeUrlError as exc:
        msg = "endpoint hostname resolves to a non-public address or cannot be proven public"
        raise ValueError(msg) from exc


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
        from langfuse import propagate_attributes

        from news_dashboard.ai_client import (
            free_llm_config,
            get_chat_model,
            langfuse_enabled,
            response_text,
        )

        api_key, base_url = free_llm_config()
        if not api_key:
            return fallback

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

        chat_model = get_chat_model(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tokens=40,
            temperature=0.7,
        )
        callbacks: list[Any] = []
        if langfuse_enabled():
            from langfuse.langchain import CallbackHandler

            callbacks.append(CallbackHandler())
        with propagate_attributes(tags=["push"], trace_name="push-hook"):
            response = chat_model.invoke(
                [{"role": "user", "content": prompt}], config={"callbacks": callbacks}
            )
        hook = response_text(response).strip()
        if hook:
            return hook
    except Exception:
        logger.warning("Push hook LLM generation failed; using default message")

    return fallback


_DEFAULT_RECAP_TITLE = "Your weekly reading recap is ready"


def generate_recap_push_hook(recap: dict[str, Any]) -> str:
    """Generate an AI narrative hook for a weekly recap push notification.

    Takes the recap dict from ``recaps.service.assemble_weekly_recap()``
    (keys: ``articles_read``, ``categories``, ``sources``, ``minutes_read``,
    ``current_streak_days``). Falls back to a plain summary sentence if the
    LLM is not configured or the call fails, matching ``generate_push_hook``.
    """
    articles_read = int(recap.get("articles_read") or 0)
    categories: list[dict[str, Any]] = recap.get("categories") or []
    top_category = categories[0].get("category") if categories else None

    if articles_read <= 0:
        fallback = _DEFAULT_RECAP_TITLE
    elif top_category:
        fallback = f"You read {articles_read} articles this week, mostly on {top_category}."
    else:
        fallback = f"You read {articles_read} articles this week."

    try:
        from langfuse import propagate_attributes

        from news_dashboard.ai_client import (
            free_llm_config,
            get_chat_model,
            langfuse_enabled,
            response_text,
        )

        api_key, base_url = free_llm_config()
        if not api_key:
            return fallback

        model = os.getenv("OPENAI_BRIEFING_MODEL", "gpt-4o-mini")

        prompt = (
            "Write a single encouraging mobile push notification hook (max 20 words) "
            "summarizing this user's weekly reading recap. "
            f"Articles read: {articles_read}. "
            f"Top category: {top_category or 'n/a'}. "
            f"Current streak: {recap.get('current_streak_days', 0)} day(s).\n\n"
            "Reply with only the hook text, no quotes or punctuation at the end."
        )

        chat_model = get_chat_model(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tokens=40,
            temperature=0.7,
        )
        callbacks: list[Any] = []
        if langfuse_enabled():
            from langfuse.langchain import CallbackHandler

            callbacks.append(CallbackHandler())
        with propagate_attributes(tags=["push", "recap"], trace_name="recap-push-hook"):
            response = chat_model.invoke(
                [{"role": "user", "content": prompt}], config={"callbacks": callbacks}
            )
        hook = response_text(response).strip()
        if hook:
            return hook
    except Exception:
        logger.warning("Recap push hook LLM generation failed; using default message")

    return fallback


PushDeliveryResult = Literal["sent", "skipped_not_configured", "temporary_failure", "gone"]


class _PinnedPushSession(requests.Session):
    """Requests-compatible pywebpush session backed by the pinned URL opener."""

    def __init__(self) -> None:
        super().__init__()
        self.trust_env = False

    def send(self, request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
        """Send one prepared request without a hostname-based second resolution."""
        if not isinstance(request.url, str):
            message = "Push request URL must be a string"
            raise UnsafeUrlError(message)
        if request.method != "POST":
            message = "Pinned push transport only supports POST"
            raise UnsafeUrlError(message)

        body = request.body
        if isinstance(body, str):
            request_data: bytes | None = body.encode()
        elif isinstance(body, bytes) or body is None:
            request_data = body
        else:
            message = "Pinned push transport requires an in-memory request body"
            raise UnsafeUrlError(message)

        timeout_value = kwargs.get("timeout", _PUSH_DELIVERY_TIMEOUT_SECONDS)
        if timeout_value is None:
            timeout_value = _PUSH_DELIVERY_TIMEOUT_SECONDS
        if not isinstance(timeout_value, int | float):
            message = "Pinned push transport requires a numeric timeout"
            raise UnsafeUrlError(message)

        request_headers: dict[str, str] = {}
        for name, value in request.headers.items():
            request_headers[str(name)] = (
                value.decode("latin-1") if isinstance(value, bytes) else str(value)
            )

        url_request = urllib.request.Request(  # noqa: S310 - central opener validates and pins
            request.url,
            data=request_data,
            headers=request_headers,
            method=request.method,
        )
        try:
            with open_server_fetch_url(url_request, timeout=float(timeout_value)) as opened:
                return _push_response(opened, request)
        except urllib.error.HTTPError as exc:
            with exc:
                return _push_response(exc, request)


def _push_response(source: Any, request: requests.PreparedRequest) -> requests.Response:
    """Adapt a bounded urllib response to the subset pywebpush consumes."""
    content: bytes = source.read(_PUSH_RESPONSE_BYTE_CAP + 1)
    status_code = getattr(source, "status", None)
    if not isinstance(status_code, int):
        status_code = getattr(source, "code", None)
    if not isinstance(status_code, int):
        message = "Push service response did not include an HTTP status"
        raise UnsafeUrlError(message)
    response = requests.Response()
    response.status_code = status_code
    response.reason = str(getattr(source, "reason", ""))
    response.headers = CaseInsensitiveDict(source.headers.items())
    response.url = str(source.geturl())
    response.request = request
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    response._content = content[:_PUSH_RESPONSE_BYTE_CAP]
    return response


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
        with _PinnedPushSession() as session:
            webpush(
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {"p256dh": p256dh, "auth": auth},
                },
                data=payload,
                vapid_private_key=_vapid_private_key(),
                vapid_claims=_vapid_claims(),
                timeout=_PUSH_DELIVERY_TIMEOUT_SECONDS,
                requests_session=session,
            )
        return "sent"
    except (UnsafeUrlError, urllib.error.URLError) as exc:
        logger.warning("Push notification blocked or failed before delivery: %s", exc)
        return "temporary_failure"
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
