from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response as StarletteResponse

from .auth import (
    authenticate,
    create_session_token,
    create_user,
    delete_user,
    exchange_keycloak_code,
    get_user_by_id,
    init_auth,
    keycloak_auth_metadata,
    keycloak_authorization_url,
    keycloak_config,
    keycloak_logout_url,
    list_users,
    require_admin,
    require_auth,
    update_password,
)
from .body_fetch import fetch_and_cache_body, get_article
from .briefings import (
    BriefingAINotConfiguredError,
    BriefingGenerationError,
    generate_briefing,
    get_briefing,
    get_latest_briefing,
    list_briefings,
)
from .db import connect, describe_database, init_db, row_to_dict
from .ingest import (
    ingest_all,
    list_articles,
    search_articles,
    send_article_later,
    set_article_starred,
    set_article_status,
    sync_sources,
    transition_article_state,
)
from .ingest_events import stream_ingest_events
from .run_history import get_ingest_run_sources, list_ingest_runs
from .scheduler import (
    get_interval_minutes,
    get_next_ingest_at,
    is_paused,
    pause_scheduler,
    resume_scheduler,
    set_interval,
    start_scheduler,
    stop_scheduler,
)
from .source_health import list_source_health
from .stats import (
    article_counts,
    articles_over_time,
    category_mix,
    ingested_vs_handled,
    source_quality,
    sources_volume,
    stats_overview,
    triage_metrics,
)

_SESSION_COOKIE = "nd_session"
_OAUTH_STATE_COOKIE = "nd_oauth_state"
_SESSION_DAYS = 30


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
    init_auth()
    sync_sources()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="News Dashboard", version="0.4.0", lifespan=lifespan)
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

# ── Pydantic models ──────────────────────────────────────────────────────────


class StatusUpdate(BaseModel):
    status: str


class StateUpdate(BaseModel):
    state: str


class StarUpdate(BaseModel):
    starred: bool


class LaterUpdate(BaseModel):
    days: int = 1


class EnabledUpdate(BaseModel):
    enabled: bool


class CreateSourceRequest(BaseModel):
    url: str
    name: str
    category: str = "tech"
    slug: str | None = None


class IntervalUpdate(BaseModel):
    minutes: int


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: str | None = None
    is_admin: bool = False


class UpdatePasswordRequest(BaseModel):
    password: str


# ── Public auth routes (no session required) ──────────────────────────────────

public_router = APIRouter()


@public_router.get("/api/health")
def health() -> dict[str, Any]:
    init_db()
    return {
        "status": "ok",
        "database": describe_database(),
        "next_ingest_at": get_next_ingest_at(),
    }


@public_router.get("/api/auth/config")
def auth_config() -> dict[str, Any]:
    return keycloak_auth_metadata()


@public_router.get("/auth/login")
def keycloak_login() -> RedirectResponse:
    if not keycloak_config().enabled:
        return RedirectResponse(url="/login")
    state = secrets.token_urlsafe(32)
    redirect = RedirectResponse(url=keycloak_authorization_url(state))
    redirect.set_cookie(
        key=_OAUTH_STATE_COOKIE,
        value=state,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=600,
        path="/auth/callback",
    )
    return redirect


@public_router.get("/auth/callback")
async def keycloak_callback(request: Request) -> RedirectResponse:
    expected_state = request.cookies.get(_OAUTH_STATE_COOKIE)
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not expected_state or not state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=400, detail="Invalid Keycloak OAuth state")
    if not code:
        raise HTTPException(status_code=400, detail="Missing Keycloak OAuth code")

    user = await exchange_keycloak_code(code)
    token = create_session_token(user["id"], bool(user["is_admin"]))
    redirect = RedirectResponse(url="/")
    redirect.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_SESSION_DAYS * 86400,
        path="/",
    )
    redirect.delete_cookie(key=_OAUTH_STATE_COOKIE, path="/auth/callback")
    return redirect


@public_router.get("/auth/logout")
def keycloak_logout() -> RedirectResponse:
    redirect = RedirectResponse(url=keycloak_logout_url())
    redirect.delete_cookie(key=_SESSION_COOKIE, path="/")
    return redirect


@public_router.post("/api/auth/login")
def login(payload: LoginRequest, response: Response) -> dict[str, Any]:
    if keycloak_config().enabled:
        raise HTTPException(status_code=409, detail="Password login is disabled; use Keycloak")
    user = authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_session_token(user["id"], bool(user["is_admin"]))
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_SESSION_DAYS * 86400,
        path="/",
    )
    return {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])}


@public_router.get("/api/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key=_SESSION_COOKIE, path="/")
    return {"status": "logged_out"}


app.include_router(public_router)

# ── Authenticated API router ─────────────────────────────────────────────────

api = APIRouter(dependencies=[Depends(require_auth)])


@api.get("/api/auth/me")
def auth_me(current_user: Annotated[dict[str, Any], Depends(require_auth)]) -> dict[str, Any]:
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user.get("email"),
        "is_admin": bool(current_user["is_admin"]),
    }


@api.post("/api/ingest")
def ingest() -> dict[str, Any]:
    results = ingest_all()
    return {"results": results, "inserted": sum(v for v in results.values() if v > 0)}


@api.get("/api/ingest/stream")
def ingest_stream() -> StreamingResponse:
    return StreamingResponse(stream_ingest_events(), media_type="text/event-stream")


@api.get("/api/articles")
def articles(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    status: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    starred: Annotated[bool | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return {
        "items": list_articles(
            status=status,
            state=state,
            starred=starred,
            category=category,
            limit=limit,
            offset=offset,
            user_id=current_user["id"],
        )
    }


@api.get("/api/search")
def search(  # noqa: PLR0913
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    q: Annotated[str, Query(description="Space-separated search terms")] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    states: Annotated[list[str] | None, Query()] = None,
    categories: Annotated[list[str] | None, Query()] = None,
    sources: Annotated[list[str] | None, Query()] = None,
    starred_only: Annotated[bool, Query()] = False,
    include_archived: Annotated[bool, Query()] = False,
    date_range: Annotated[str, Query()] = "all",
) -> dict[str, Any]:
    return {
        "items": search_articles(
            q=q.strip(),
            limit=limit,
            states=states,
            categories=categories,
            sources=sources,
            starred_only=starred_only,
            include_archived=include_archived,
            date_range=date_range,
            user_id=current_user["id"],
        )
    }


@api.get("/api/articles/{article_id}")
def get_article_by_id(article_id: int) -> dict[str, Any]:
    article = get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@api.post("/api/articles/{article_id}/body")
def fetch_article_body(article_id: int) -> dict[str, Any]:
    article = fetch_and_cache_body(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@api.patch("/api/articles/{article_id}/status")
def update_status(article_id: int, payload: StatusUpdate) -> dict[str, Any]:
    try:
        article = set_article_status(article_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@api.patch("/api/articles/{article_id}/state")
def update_state(
    article_id: int,
    payload: StateUpdate,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        article = transition_article_state(article_id, payload.state, user_id=current_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@api.patch("/api/articles/{article_id}/star")
def update_star(
    article_id: int,
    payload: StarUpdate,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    article = set_article_starred(article_id, payload.starred, user_id=current_user["id"])
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@api.patch("/api/articles/{article_id}/later")
def snooze_later(
    article_id: int,
    payload: LaterUpdate,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        article = send_article_later(article_id, payload.days, user_id=current_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@api.get("/api/articles/{article_id}/read")
def mark_read_via_token(article_id: int, token: Annotated[str, Query()]) -> dict[str, Any]:
    from .digest import verify_read_token

    if not verify_read_token(article_id, token):
        raise HTTPException(status_code=403, detail="invalid or expired token")
    try:
        article = set_article_status(article_id, "read")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return {"status": "marked_read", "article": article}


@api.get("/api/sources")
def sources(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    init_db()
    uid = current_user["id"]
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT s.*,
              CASE WHEN s.owner_user_id IS NULL THEN COALESCE(us.enabled, 1)
                   ELSE s.enabled END AS user_enabled
            FROM sources s
            LEFT JOIN user_sources us ON us.source_slug = s.slug AND us.user_id = ?
            WHERE s.owner_user_id IS NULL OR s.owner_user_id = ?
            ORDER BY s.category, s.priority DESC, s.name
            """,
            (uid, uid),
        ).fetchall()
        items = []
        for row in rows:
            d = row_to_dict(row)
            d["subscribed"] = bool(d.pop("user_enabled", 1))
            items.append(d)
        return {"items": items}


@api.post("/api/sources")
def create_source(
    payload: CreateSourceRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Create a private custom source owned by the current user."""
    import re

    uid = current_user["id"]
    slug = payload.slug or re.sub(r"[^a-z0-9-]", "-", payload.name.lower()).strip("-")
    init_db()
    with connect() as conn:
        existing = conn.execute("SELECT 1 FROM sources WHERE slug = ?", (slug,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"source slug {slug!r} already exists")
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
            VALUES (?, ?, ?, ?, 'rss_feed', 0, 1, ?)
            """,
            (slug, payload.name, payload.url, payload.category, uid),
        )
        row = conn.execute("SELECT * FROM sources WHERE slug = ?", (slug,)).fetchone()
    return row_to_dict(row)


@api.delete("/api/sources/{slug}")
def delete_source(
    slug: str,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Delete a private source. Only the owner can delete their own sources."""
    uid = current_user["id"]
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM sources WHERE slug = ?", (slug,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="source not found")
        src = row_to_dict(row)
        if src.get("owner_user_id") != uid:
            raise HTTPException(status_code=403, detail="cannot delete a source you don't own")
        conn.execute("DELETE FROM sources WHERE slug = ?", (slug,))
    return {"status": "deleted"}


@api.get("/api/sources/health")
def sources_health() -> dict[str, Any]:
    return {"items": list_source_health()}


@api.patch("/api/sources/{slug}/enabled")
def set_source_enabled(
    slug: str,
    payload: EnabledUpdate,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """For global sources: set per-user subscription. For private sources: set enabled flag."""
    uid = current_user["id"]
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM sources WHERE slug = ?", (slug,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="source not found")
        src = row_to_dict(row)
        if src.get("owner_user_id") is None:
            # Global source — write to user_sources subscription table
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = excluded.enabled
                """,
                (uid, slug, 1 if payload.enabled else 0),
            )
        else:
            # Private source — only owner can change
            if src.get("owner_user_id") != uid:
                raise HTTPException(status_code=403, detail="cannot modify a source you don't own")
            conn.execute(
                "UPDATE sources SET enabled = ? WHERE slug = ?",
                (1 if payload.enabled else 0, slug),
            )
        row = conn.execute("SELECT * FROM sources WHERE slug = ?", (slug,)).fetchone()
    return {**row_to_dict(row), "subscribed": payload.enabled}


@api.get("/api/scheduler/status")
def scheduler_status() -> dict[str, Any]:
    next_run = get_next_ingest_at()
    paused = is_paused()
    return {
        "interval_minutes": get_interval_minutes(),
        "paused": paused,
        "next_run_at": next_run,
    }


_admin_dep = [Depends(require_admin)]


@api.post("/api/scheduler/interval", dependencies=_admin_dep)
def scheduler_set_interval(payload: IntervalUpdate) -> dict[str, Any]:
    if payload.minutes < 1:
        raise HTTPException(status_code=400, detail="minutes must be >= 1")
    set_interval(payload.minutes)
    return {"interval_minutes": payload.minutes, "next_run_at": get_next_ingest_at()}


@api.post("/api/scheduler/pause", dependencies=_admin_dep)
def scheduler_pause() -> dict[str, Any]:
    pause_scheduler()
    return {"paused": True}


@api.post("/api/scheduler/resume", dependencies=_admin_dep)
def scheduler_resume() -> dict[str, Any]:
    resume_scheduler()
    return {"paused": False, "next_run_at": get_next_ingest_at()}


@api.get("/api/ingest/runs", dependencies=_admin_dep)
def ingest_runs(
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    return list_ingest_runs(from_=from_, to=to, page=page, per_page=per_page)


@api.get("/api/ingest/runs/{run_id}", dependencies=_admin_dep)
def ingest_run_sources(run_id: int) -> dict[str, Any]:
    run_sources = get_ingest_run_sources(run_id)
    if run_sources is None:
        raise HTTPException(status_code=404, detail="ingest run not found")
    return {"items": run_sources}


@api.get("/api/stats/overview", dependencies=_admin_dep)
def stats_overview_endpoint(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return stats_overview(from_, to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api.get("/api/stats/articles-over-time", dependencies=_admin_dep)
def stats_articles_over_time_endpoint(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return {"items": articles_over_time(from_, to)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api.get("/api/stats/sources-volume", dependencies=_admin_dep)
def stats_sources_volume_endpoint(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return {"items": sources_volume(from_, to)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@api.get("/api/stats/article-counts", dependencies=_admin_dep)
def stats_article_counts_endpoint() -> dict[str, Any]:
    return article_counts()


@api.get("/api/stats/triage-metrics", dependencies=_admin_dep)
def stats_triage_metrics_endpoint() -> dict[str, Any]:
    return triage_metrics()


@api.get("/api/stats/source-quality", dependencies=_admin_dep)
def stats_source_quality_endpoint() -> dict[str, Any]:
    return {"items": source_quality()}


@api.get("/api/stats/category-mix", dependencies=_admin_dep)
def stats_category_mix_endpoint() -> dict[str, Any]:
    return {"items": category_mix()}


@api.get("/api/stats/ingested-vs-handled", dependencies=_admin_dep)
def stats_ingested_vs_handled_endpoint() -> dict[str, Any]:
    return {"items": ingested_vs_handled()}


@api.get("/api/briefings/latest")
def briefings_latest(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    briefing = get_latest_briefing(user_id=current_user["id"])
    if briefing is None:
        return {"status": "empty"}
    return briefing


@api.get("/api/briefings")
def briefings_list(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return {"items": list_briefings(limit=limit, offset=offset, user_id=current_user["id"])}


@api.get("/api/briefings/{briefing_id}")
def briefings_detail(
    briefing_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    briefing = get_briefing(briefing_id, user_id=current_user["id"])
    if briefing is None:
        raise HTTPException(status_code=404, detail="briefing not found")
    return briefing


@api.post("/api/briefings")
def briefings_create(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return generate_briefing(user_id=current_user["id"])
    except BriefingAINotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BriefingGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class AskRequest(BaseModel):
    query: str
    include_all: bool = False


@api.post("/api/ask")
def ask_ai(payload: AskRequest) -> dict[str, Any]:
    from .embeddings import ask

    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query must not be empty")
    try:
        return ask(q, include_all=payload.include_all)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@api.get("/api/summary")
def summary() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM articles GROUP BY status"
        ).fetchall()
        category_rows = conn.execute(
            "SELECT category, COUNT(*) AS count FROM articles GROUP BY category"
        ).fetchall()
    return {
        "byStatus": {row["status"]: row["count"] for row in status_rows},
        "byCategory": {row["category"]: row["count"] for row in category_rows},
    }


# ── Admin user-management routes ─────────────────────────────────────────────

admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


@admin.get("/users")
def admin_list_users() -> dict[str, Any]:
    return {"items": list_users()}


@admin.post("/users")
def admin_create_user(payload: CreateUserRequest) -> dict[str, Any]:
    try:
        return create_user(
            payload.username,
            payload.password,
            email=payload.email,
            is_admin=payload.is_admin,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@admin.get("/users/{user_id}")
def admin_get_user(user_id: int) -> dict[str, Any]:
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@admin.patch("/users/{user_id}/password")
def admin_update_password(user_id: int, payload: UpdatePasswordRequest) -> dict[str, Any]:
    if not update_password(user_id, payload.password):
        raise HTTPException(status_code=404, detail="user not found")
    return {"status": "updated"}


@admin.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="cannot delete your own account")
    if not delete_user(user_id):
        raise HTTPException(status_code=404, detail="user not found")
    return {"status": "deleted"}


app.include_router(api)
app.include_router(admin)


# ── SPA static files ─────────────────────────────────────────────────────────

static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="static")
