from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response as StarletteResponse

from news_dashboard.auth import (
    get_user_by_id,
    init_auth,
    require_admin,
    require_auth,
    verify_session_token,
)
from news_dashboard.auth_routes.router import SESSION_COOKIE as _SESSION_COOKIE
from news_dashboard.auth_routes.router import public_router as auth_public_router
from news_dashboard.auth_routes.router import router as auth_router
from news_dashboard.db import close_connection_pool, open_connection_pool
from news_dashboard.error_tracking import init_error_tracking
from news_dashboard.ingest.service import (
    sync_sources,
)
from news_dashboard.scheduler.service import (
    start_scheduler,
    stop_scheduler,
)

logger = logging.getLogger(__name__)

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def _read_app_version() -> str:
    """Return the running app version from the VERSION file baked into the image."""
    try:
        return _VERSION_FILE.read_text().strip()
    except OSError:
        return "unknown"


class SPAStaticFiles(StaticFiles):
    """Serve index.html for client-side routes while preserving API/static 404s."""

    async def get_response(self, path: str, scope: MutableMapping[str, Any]) -> StarletteResponse:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            is_client_route = scope.get("method") == "GET" and not path.startswith("api/")
            is_asset = path.startswith("assets/") or "." in Path(path).name
            if exc.status_code != 404 or not is_client_route or is_asset:
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_error_tracking()
    open_connection_pool()
    init_auth()
    sync_sources()
    # Seed demo data when DEMO_MODE is enabled.
    if os.getenv("DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on"):
        from news_dashboard.demo import seed_demo

        seed_demo()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        close_connection_pool()


app = FastAPI(title="News Dashboard", version=_read_app_version(), lifespan=lifespan)
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env.strip()
    else ["http://localhost:5173", "http://127.0.0.1:5173"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ── API docs exposure toggle ────────────────────────────────────────────────


@app.middleware("http")
async def gate_api_docs(request: Request, call_next: Any) -> Any:
    """Hide the interactive API docs unless explicitly enabled.

    ``/docs``, ``/redoc``, and ``/openapi.json`` expose the full API surface,
    so they're 404'd for anonymous visitors unless ENABLE_API_DOCS is set.
    """
    from news_dashboard.api_docs import DOCS_PATHS, api_docs_enabled

    if request.url.path in DOCS_PATHS and not api_docs_enabled():
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return await call_next(request)


# ── Optional Prometheus metrics ─────────────────────────────────────────────


@app.middleware("http")
async def record_request_metrics(request: Request, call_next: Any) -> Any:
    """Record request count/latency, labeled by method and route template.

    Uses the matched route's path template (e.g. ``/api/articles/{id}``)
    rather than the raw URL so dynamic path segments never appear in labels.
    A no-op unless METRICS_ENABLED is set, to avoid the timing/label overhead
    for self-hosters who don't scrape metrics.
    """
    from news_dashboard.metrics import (
        http_request_duration_seconds,
        http_requests_total,
        metrics_enabled,
    )

    if not metrics_enabled():
        return await call_next(request)

    started = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - started
    route = request.scope.get("route")
    path = route.path if route is not None else request.url.path
    labels = {"method": request.method, "path": path}
    http_requests_total.labels(status=str(response.status_code), **labels).inc()
    http_request_duration_seconds.labels(**labels).observe(duration)
    return response


# ── Demo mode: reject guest writes ──────────────────────────────────────────

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Public POST routes that a guest must still reach (login, OTP).
_PUBLIC_UNSAFE_PREFIXES = (
    "/api/auth/login",
    "/api/auth/otp/",
    "/auth/",
)


@app.middleware("http")
async def reject_guest_writes(request: Request, call_next: Any) -> Any:
    """Block unsafe-method requests from guest (demo) accounts.

    Safe methods (GET, HEAD, OPTIONS) always pass through. Public auth
    routes (login, OTP, Keycloak callback) are also exempt so that a guest
    can still obtain a session cookie. Every other POST/PUT/PATCH/DELETE
    that requires auth is rejected with 403 when the session belongs to a
    guest user.
    """
    if request.method not in _UNSAFE_METHODS:
        return await call_next(request)

    # Allow public auth routes.
    path = request.url.path
    if any(path.startswith(prefix) for prefix in _PUBLIC_UNSAFE_PREFIXES):
        return await call_next(request)

    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        # Not authenticated — let the normal 401 flow handle it.
        return await call_next(request)

    payload = verify_session_token(token)
    if not payload:
        return await call_next(request)

    user = get_user_by_id(payload["user_id"])
    if user and user.get("is_guest"):
        return JSONResponse(
            status_code=403,
            content={"detail": "Guest accounts cannot modify data"},
        )

    return await call_next(request)


# ── CSRF/origin guard for cookie-authenticated mutations ────────────────────


def _request_origin(request: Request) -> str | None:
    """Return the request's Origin, falling back to the Referer's origin."""
    origin = request.headers.get("origin")
    if origin:
        return origin
    referer = request.headers.get("referer")
    if referer:
        parts = urlsplit(referer)
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}"
    return None


def _origin_from_url(value: str | None) -> str | None:
    """Return scheme://host[:port] for an absolute URL config value."""
    if not value:
        return None
    parts = urlsplit(value.strip())
    if parts.scheme and parts.netloc:
        return f"{parts.scheme}://{parts.netloc}"
    return None


def _request_base_origin(request: Request) -> str:
    """Return the externally visible request origin when proxy headers exist."""
    forwarded_host = request.headers.get("x-forwarded-host")
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_host and forwarded_proto:
        host = forwarded_host.split(",", maxsplit=1)[0].strip()
        proto = forwarded_proto.split(",", maxsplit=1)[0].strip()
        if host and proto:
            return f"{proto}://{host}"
    return f"{request.url.scheme}://{request.url.netloc}"


def _allowed_csrf_origins(request: Request) -> set[str]:
    """Return origins allowed to perform cookie-authenticated mutations."""
    origins = {*_cors_origins, _request_base_origin(request)}
    public_base_origin = _origin_from_url(os.getenv("NEWS_DASHBOARD_BASE_URL"))
    if public_base_origin is not None:
        origins.add(public_base_origin)
    return origins


@app.middleware("http")
async def enforce_csrf_origin(request: Request, call_next: Any) -> Any:
    """Reject cross-origin unsafe requests carrying the session cookie.

    ``nd_session`` is already ``SameSite=Strict``, which blocks most
    cross-site delivery, but that's a browser-side guarantee. This fails
    closed at the server boundary too, in case a same-site sibling origin,
    reverse-proxy change, or future cookie setting loosens it. The guard
    only fires for unsafe methods on requests that already carry the
    session cookie, so unauthenticated flows (login, OTP, Keycloak
    callback) and safe methods are unaffected. It's a no-op when neither
    ``Origin`` nor ``Referer`` is present, since non-browser clients
    (curl, mobile apps) don't send them.
    """
    if request.method not in _UNSAFE_METHODS:
        return await call_next(request)

    path = request.url.path
    if any(path.startswith(prefix) for prefix in _PUBLIC_UNSAFE_PREFIXES):
        return await call_next(request)

    if not request.cookies.get(_SESSION_COOKIE):
        return await call_next(request)

    origin = _request_origin(request)
    if origin is not None and origin not in _allowed_csrf_origins(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "Cross-origin request rejected"},
        )

    return await call_next(request)


# ── Baseline browser security headers ───────────────────────────────────────


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Any) -> Any:
    """Attach conservative security headers to every response.

    Applies to API and static frontend responses alike, so the app carries
    this baseline itself regardless of whether it's fronted by the Caddy
    deployment in ``deploy/Caddyfile`` or run directly (Docker/Compose).
    """
    from news_dashboard.security_headers import apply_security_headers

    response = await call_next(request)
    apply_security_headers(response)
    return response


# ── AI-facing payload limits ─────────────────────────────────────────────────
# Bounds for user-supplied text that reaches retrieval, prompt construction, or
# storage, so a malformed client can't send oversized LLM requests or noisy
# Langfuse traces.


# ── Pydantic models ──────────────────────────────────────────────────────────


# ── OPML helpers ──────────────────────────────────────────────────────────────


# ── Public auth routes (no session required) ──────────────────────────────────

public_router = APIRouter()


public_router.include_router(auth_public_router)


# `public_router` is included further down (see `app.include_router(public_router)`
# near the bottom of this module), after every route that mounts on it — including
# the token-authenticated podcast routes defined later — has been registered.


# ── Authenticated API router ─────────────────────────────────────────────────

api = APIRouter(dependencies=[Depends(require_auth)])


api.include_router(auth_router)


_PREVIEW_MAX_ITEMS = 5


# OPML files are plain text and rarely exceed a few hundred KB even with
# thousands of outlines; 5 MiB and 1000 outlines leave headroom while bounding
# memory use and per-request import time for oversized or hostile uploads.


# ── AI watchlists ──────────────────────────────────────────────────────────────


_admin_dep = [Depends(require_admin)]


# ── Notification settings & push subscriptions ───────────────────────────────

_BRIEFING_TIME_RE = __import__("re").compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_NOTIFICATION_COLS = (
    "briefing_time, briefing_push_enabled, briefing_timezone, recap_enabled, recap_day, "
    "briefing_include_reading_list, briefing_reading_list_limit"
)
_RECAP_DAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})
_READING_LIST_LIMIT_MAX = 20


# Archives are JSON text; 20 MiB covers even large multi-year histories while
# bounding memory use and per-request import time for oversized uploads.


# ── Tags & Collections ────────────────────────────────────────────────────────


# ── Reading Goals & Quizzes ───────────────────────────────────────────────────


# Reading Goals + weekly quiz routes now live in the ``quizzes`` feature module
# (news_dashboard/quizzes/{router,service,models}.py); its router is mounted on
# ``api`` below. See docs/adr for the feature-module layout.


# ── Admin user-management routes ─────────────────────────────────────────────

admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


from news_dashboard.admin_routes.router import router as admin_routes_router  # noqa: E402

# Feature-module routers mount onto ``api`` so they inherit its ``require_auth``
# gate. Add each new domain's router here as it is extracted from main.py.
from news_dashboard.ai_feedback.router import router as ai_feedback_router  # noqa: E402
from news_dashboard.ai_memory.router import router as ai_memory_router  # noqa: E402
from news_dashboard.ai_stats.router import router as ai_stats_router  # noqa: E402
from news_dashboard.articles.router import public_router as articles_public_router  # noqa: E402
from news_dashboard.articles.router import router as articles_router  # noqa: E402
from news_dashboard.assistant.router import router as assistant_router  # noqa: E402
from news_dashboard.briefings.router import public_router as briefings_public_router  # noqa: E402
from news_dashboard.briefings.router import router as briefings_router  # noqa: E402
from news_dashboard.events.router import router as events_router  # noqa: E402
from news_dashboard.greader import public_greader_router  # noqa: E402
from news_dashboard.greader import router as greader_router  # noqa: E402
from news_dashboard.ingest.router import router as ingest_router  # noqa: E402
from news_dashboard.learn_from_link.router import router as learn_from_link_router  # noqa: E402
from news_dashboard.lesson_recaps.router import router as lesson_recaps_router  # noqa: E402
from news_dashboard.mcp.router import public_mcp_router  # noqa: E402
from news_dashboard.mcp.router import router as mcp_router  # noqa: E402
from news_dashboard.onboarding.router import router as onboarding_router  # noqa: E402
from news_dashboard.personalization.router import router as personalization_router  # noqa: E402
from news_dashboard.quizzes.router import router as quizzes_router  # noqa: E402
from news_dashboard.reading_list.router import router as reading_list_router  # noqa: E402
from news_dashboard.reading_progress.router import router as reading_progress_router  # noqa: E402
from news_dashboard.recaps.router import router as recaps_router  # noqa: E402
from news_dashboard.recommendations_routes.router import router as recs_router  # noqa: E402
from news_dashboard.saved_searches.router import router as saved_searches_router  # noqa: E402
from news_dashboard.scheduler.router import router as scheduler_router  # noqa: E402
from news_dashboard.shares.router import router as shares_router  # noqa: E402
from news_dashboard.sources.router import router as sources_router  # noqa: E402
from news_dashboard.stats.router import router as stats_router  # noqa: E402
from news_dashboard.system.router import router as system_router  # noqa: E402
from news_dashboard.tags_routes.router import router as tags_router  # noqa: E402
from news_dashboard.user_settings.router import router as user_settings_router  # noqa: E402
from news_dashboard.watchlists.router import router as watchlists_router  # noqa: E402

api.include_router(articles_router)
api.include_router(assistant_router)
api.include_router(briefings_router)
api.include_router(events_router)
api.include_router(ingest_router)
api.include_router(scheduler_router)
api.include_router(shares_router)
api.include_router(sources_router)
api.include_router(stats_router)
api.include_router(tags_router)
api.include_router(user_settings_router)
api.include_router(watchlists_router)

api.include_router(ai_feedback_router)
api.include_router(ai_stats_router)
api.include_router(ai_memory_router)
api.include_router(greader_router)
api.include_router(learn_from_link_router)
api.include_router(lesson_recaps_router)
api.include_router(mcp_router)
api.include_router(onboarding_router)
api.include_router(personalization_router)
api.include_router(quizzes_router)
api.include_router(reading_list_router)
api.include_router(reading_progress_router)
api.include_router(recaps_router)
api.include_router(recs_router)
api.include_router(saved_searches_router)

public_router.include_router(articles_public_router)
public_router.include_router(briefings_public_router)
admin.include_router(admin_routes_router)

app.include_router(public_router)
app.include_router(api)
app.include_router(admin)
# MCP tool-calling and GReader-sync endpoints authenticate via bearer token,
# not the session cookie, so they mount directly on the app rather than the
# `api` router.
app.include_router(public_mcp_router)
app.include_router(public_greader_router)
# System/health endpoints are unauthenticated, so mount directly on the app
# rather than the `api` router.
app.include_router(system_router)


# ── SPA static files ─────────────────────────────────────────────────────────

static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="static")
