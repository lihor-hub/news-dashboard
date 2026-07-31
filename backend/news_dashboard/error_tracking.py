"""Optional Sentry/GlitchTip-compatible error tracking.

Gated by the ``SENTRY_DSN`` env var (backend) and ``SENTRY_DSN_FRONTEND``
(exposed to the SPA via ``GET /api/config``). Both are off by default: when
unset, no SDK is initialized and no telemetry leaves the process.
"""

from __future__ import annotations

import os
import re
from ipaddress import ip_address
from typing import TYPE_CHECKING, Any, cast
from unicodedata import category
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint

_MAX_FRONTEND_DSN_LENGTH = 2_048
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_DSN_USERINFO = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=:%-]+")
_DSN_PATH = re.compile(r"/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*[A-Za-z0-9._~!$&'()*+,;=:@%-]")


def error_tracking_enabled() -> bool:
    return bool(os.getenv("SENTRY_DSN", "").strip())


def _normalized_hostname(value: str) -> str | None:
    candidate = value.lower()
    try:
        return ip_address(candidate).compressed
    except ValueError:
        pass
    try:
        candidate = candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if len(candidate) > 253 or any(
        _HOST_LABEL.fullmatch(label) is None for label in candidate.split(".")
    ):
        return None
    return candidate


def _normalized_frontend_dsn(value: str) -> str | None:
    candidate = value.strip()
    if (
        not candidate
        or len(candidate) > _MAX_FRONTEND_DSN_LENGTH
        or any(category(char) in {"Cc", "Cf"} for char in value)
    ):
        return None
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return None
    hostname = _normalized_hostname(parsed.hostname) if parsed.hostname is not None else None
    if (
        parsed.scheme not in {"http", "https"}
        or hostname is None
        or parsed.username is None
        or _DSN_USERINFO.fullmatch(parsed.username) is None
        or (parsed.password is not None and _DSN_USERINFO.fullmatch(parsed.password) is None)
        or _DSN_PATH.fullmatch(parsed.path) is None
        or parsed.query
        or parsed.fragment
    ):
        return None

    userinfo = parsed.netloc.rsplit("@", maxsplit=1)[0]
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme, f"{userinfo}@{netloc}", parsed.path, "", ""))


def frontend_error_tracking_dsn() -> str | None:
    return _normalized_frontend_dsn(os.getenv("SENTRY_DSN_FRONTEND", ""))


def frontend_error_tracking_origin() -> str | None:
    """Return the validated DSN's origin without credentials or project path."""
    dsn = frontend_error_tracking_dsn()
    if dsn is None:
        return None
    parsed = urlsplit(dsn)
    hostname = parsed.hostname
    if hostname is None:
        return None
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, "", "", ""))


def _scrub_pii(event: Event, _hint: Hint) -> Event | None:
    # Sentry's Event/RequestContext TypedDicts are loosely typed (Any-derived),
    # so treat the mutable pieces as plain dicts rather than fighting the checker.
    untyped_event = cast("dict[str, Any]", event)
    request = untyped_event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for key in [k for k in headers if str(k).lower() in ("authorization", "cookie")]:
                headers.pop(key, None)
    untyped_event.pop("user", None)
    return event


def init_error_tracking() -> None:
    """Initialize the Sentry SDK when SENTRY_DSN is configured; no-op otherwise."""
    if not error_tracking_enabled():
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("SENTRY_RELEASE") or None,
        send_default_pii=False,
        before_send=_scrub_pii,
    )


__all__ = [
    "error_tracking_enabled",
    "frontend_error_tracking_dsn",
    "frontend_error_tracking_origin",
    "init_error_tracking",
]
