"""Optional Sentry/GlitchTip-compatible error tracking.

Gated by the ``SENTRY_DSN`` env var (backend) and ``SENTRY_DSN_FRONTEND``
(exposed to the SPA via ``GET /api/config``). Both are off by default: when
unset, no SDK is initialized and no telemetry leaves the process.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint


def error_tracking_enabled() -> bool:
    return bool(os.getenv("SENTRY_DSN", "").strip())


def frontend_error_tracking_dsn() -> str | None:
    dsn = os.getenv("SENTRY_DSN_FRONTEND", "").strip()
    return dsn or None


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


__all__ = ["error_tracking_enabled", "frontend_error_tracking_dsn", "init_error_tracking"]
