"""Signed, expiring tokens for briefing-email unsubscribe links."""

from __future__ import annotations

import os
from typing import Any

from itsdangerous import BadData, URLSafeTimedSerializer

_SALT = "news-dashboard-briefing-email-unsubscribe-v1"
_ACTION = "unsubscribe"
_VERSION = 1


def _payload_user_id(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("user_id")
    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
        or payload.get("action") != _ACTION
        or payload.get("version") != _VERSION
    ):
        return None
    return user_id


def _secret() -> str:
    secret = (
        os.getenv("TOKEN_SECRET") or os.getenv("SESSION_SECRET") or os.getenv("TEST_SESSION_SECRET")
    )
    if secret:
        return secret
    message = "TOKEN_SECRET or SESSION_SECRET is required to sign unsubscribe tokens"
    raise RuntimeError(message)


def make_unsubscribe_token(user_id: int) -> str:
    """Create a purpose-bound token containing only the recipient's user ID."""
    serializer = URLSafeTimedSerializer(_secret(), salt=_SALT)
    return serializer.dumps({"user_id": user_id, "action": _ACTION, "version": _VERSION})


def verify_unsubscribe_token(
    token: str,
    *,
    max_age_seconds: int = 2_592_000,
) -> int:
    """Return the bound user ID or raise ``ValueError`` for any invalid token."""
    serializer = URLSafeTimedSerializer(_secret(), salt=_SALT)
    try:
        payload: Any = serializer.loads(token, max_age=max_age_seconds)
    except (BadData, TypeError) as exc:
        message = "Invalid unsubscribe token"
        raise ValueError(message) from exc
    user_id = _payload_user_id(payload)
    if user_id is None:
        message = "Invalid unsubscribe token"
        raise ValueError(message)
    return user_id
