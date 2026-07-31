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
from urllib.parse import urlsplit, urlunsplit

from starlette.responses import PlainTextResponse, Response

from news_dashboard.dify import public_dify_config
from news_dashboard.error_tracking import frontend_error_tracking_origin

X_CONTENT_TYPE_OPTIONS = "nosniff"
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "no-referrer"
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"
HSTS_VALUE = "max-age=31536000; includeSubDomains; preload"


def _content_security_directives() -> dict[str, list[str]]:
    frame_sources = ["'self'"]
    dify_config = public_dify_config()
    if dify_config["enabled"] and dify_config["base_url"] is not None:
        parsed = urlsplit(dify_config["base_url"])
        frame_sources.append(urlunsplit((parsed.scheme, parsed.netloc, "", "", "")))

    connect_sources = ["'self'", "https://api.github.com"]
    error_tracking_origin = frontend_error_tracking_origin()
    if error_tracking_origin is not None:
        connect_sources.append(error_tracking_origin)

    return {
        "default-src": ["'self'"],
        "base-uri": ["'self'"],
        "object-src": ["'none'"],
        "frame-ancestors": ["'none'"],
        "form-action": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "connect-src": connect_sources,
        "img-src": ["'self'", "data:", "blob:"],
        "font-src": ["'self'", "data:"],
        "media-src": ["'self'", "data:", "blob:"],
        "worker-src": ["'self'", "blob:"],
        "manifest-src": ["'self'"],
        "frame-src": frame_sources,
    }


def _serialize_policy(directives: dict[str, list[str]]) -> str:
    return "; ".join(f"{name} {' '.join(sources)}" for name, sources in directives.items())


def content_security_policy() -> str:
    """Return the canonical browser policy for API and frontend responses."""
    return _serialize_policy(_content_security_directives())


def api_docs_content_security_policy(path: str) -> str:
    """Return an exact-path development exception for FastAPI's generated docs."""
    directives = _content_security_directives()
    if path == "/docs":
        directives["script-src"] = [
            "'self'",
            "https://cdn.jsdelivr.net",
            "'unsafe-inline'",
        ]
        directives["style-src"] = [
            "'self'",
            "https://cdn.jsdelivr.net",
            "'unsafe-inline'",
        ]
        directives["img-src"].append("https://fastapi.tiangolo.com")
    elif path == "/redoc":
        directives["script-src"] = ["'self'", "https://cdn.jsdelivr.net"]
        directives["style-src"] = [
            "'self'",
            "https://fonts.googleapis.com",
            "'unsafe-inline'",
        ]
        directives["font-src"].append("https://fonts.gstatic.com")
        directives["img-src"].append("https://fastapi.tiangolo.com")
    return _serialize_policy(directives)


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
    response.headers.setdefault("Content-Security-Policy", content_security_policy())
    if hsts_enabled():
        response.headers.setdefault("Strict-Transport-Security", HSTS_VALUE)


def internal_server_error_response() -> Response:
    """Return the generic Starlette 500 response with the application headers."""
    response = PlainTextResponse("Internal Server Error", status_code=500)
    apply_security_headers(response)
    return response
