"""Public runtime configuration for the optional Dify chat widget."""

from __future__ import annotations

import os
from unicodedata import category
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_TITLE = "News Assistant"
_MAX_BASE_URL_LENGTH = 2_048
_MAX_APP_TOKEN_LENGTH = 512
_MAX_TITLE_LENGTH = 120
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _disabled_config() -> dict[str, object]:
    return {
        "enabled": False,
        "base_url": None,
        "app_token": None,
        "title": _DEFAULT_TITLE,
    }


def _is_valid_text(value: str, *, max_length: int) -> bool:
    return (
        bool(value)
        and len(value) <= max_length
        and not any(category(char) in {"Cc", "Cf"} for char in value)
    )


def _normalized_base_url(value: str) -> str | None:
    candidate = value.strip().rstrip("/")
    if not _is_valid_text(candidate, max_length=_MAX_BASE_URL_LENGTH):
        return None
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    if parsed.scheme == "http" and parsed.hostname not in _LOOPBACK_HOSTS:
        return None
    netloc = parsed.hostname
    if ":" in netloc:
        netloc = f"[{netloc}]"
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def public_dify_config() -> dict[str, object]:
    """Return safe-to-expose Dify embed settings, or a disabled object."""
    if os.getenv("DIFY_CHAT_ENABLED", "").strip().lower() != "true":
        return _disabled_config()

    base_url = _normalized_base_url(os.getenv("DIFY_CHAT_BASE_URL", ""))
    app_token = os.getenv("DIFY_CHAT_APP_TOKEN", "").strip()
    title = os.getenv("DIFY_CHAT_TITLE", _DEFAULT_TITLE).strip()
    if (
        base_url is None
        or not _is_valid_text(app_token, max_length=_MAX_APP_TOKEN_LENGTH)
        or not _is_valid_text(title, max_length=_MAX_TITLE_LENGTH)
    ):
        return _disabled_config()
    return {
        "enabled": True,
        "base_url": base_url,
        "app_token": app_token,
        "title": title,
    }
