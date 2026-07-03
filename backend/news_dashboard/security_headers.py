"""Baseline browser security headers for FastAPI responses.

The edge Caddy config (``deploy/Caddyfile``) already sets these headers for
the ``news.lihor.ro`` deployment, but the app can also be run directly via
``docker run``, ``docker-compose.prod.yml``, or a different reverse proxy
where Caddy isn't in front of it. This makes the baseline part of the app's
own contract instead of depending on which front door is used.

``Strict-Transport-Security`` is opt-in via ``ENABLE_HSTS`` since it's only
correct behind HTTPS; setting it on plain local HTTP dev would tell browsers
to force TLS on a server that doesn't offer it.
"""

from __future__ import annotations

import os

from starlette.responses import Response

X_CONTENT_TYPE_OPTIONS = "nosniff"
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "no-referrer"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"
HSTS_VALUE = "max-age=31536000; includeSubDomains; preload"


def hsts_enabled() -> bool:
    return os.getenv("ENABLE_HSTS", "").strip().lower() in ("1", "true", "yes", "on")


def apply_security_headers(response: Response) -> None:
    """Set conservative baseline security headers, without overriding existing ones.

    Uses ``setdefault`` so an upstream proxy or a route that deliberately sets
    a stricter value keeps its own choice.
    """
    response.headers.setdefault("X-Content-Type-Options", X_CONTENT_TYPE_OPTIONS)
    response.headers.setdefault("X-Frame-Options", X_FRAME_OPTIONS)
    response.headers.setdefault("Referrer-Policy", REFERRER_POLICY)
    response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
    if hsts_enabled():
        response.headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
