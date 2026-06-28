from __future__ import annotations

import logging
import os
import secrets
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response as StarletteResponse

from news_dashboard.analytics import (
    MAX_EVENTS_PER_BATCH,
    admin_analytics,
    reading_dna,
    record_events,
)
from news_dashboard.auth import (
    _session_days,
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
    keycloak_registration_url,
    list_users,
    require_admin,
    require_auth,
    update_password,
)
from news_dashboard.body_fetch import fetch_and_cache_body, get_article, prefetch_article_bodies
from news_dashboard.briefings import (
    BriefingAINotConfiguredError,
    BriefingGenerationError,
    chat_with_briefing,
    generate_briefing,
    get_briefing,
    get_latest_briefing,
    list_briefings,
)
from news_dashboard.db import connect, describe_database, init_db, row_to_dict
from news_dashboard.ingest import (
    get_user_summary,
    ingest_all,
    list_articles,
    search_articles,
    send_article_later,
    set_article_starred,
    set_article_status,
    sync_sources,
    transition_article_state,
)
from news_dashboard.ingest_events import stream_ingest_events
from news_dashboard.login_throttle import clear_failures, is_throttled, record_failure
from news_dashboard.run_history import get_ingest_run_sources, list_ingest_runs
from news_dashboard.scheduler import (
    get_interval_minutes,
    get_next_ingest_at,
    is_ingest_interval_enabled,
    is_paused,
    pause_scheduler,
    resume_scheduler,
    set_interval,
    start_scheduler,
    stop_scheduler,
)
from news_dashboard.source_health import (
    generate_subscription_cleanup_suggestions,
    list_source_health,
)
from news_dashboard.stats import (
    article_counts,
    articles_over_time,
    category_mix,
    ingested_vs_handled,
    source_quality,
    sources_volume,
    stats_overview,
    triage_metrics,
)

logger = logging.getLogger(__name__)

_SESSION_COOKIE = "nd_session"
_OAUTH_STATE_COOKIE = "nd_oauth_state"


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


class ShareArticleRequest(BaseModel):
    to_user_id: int
    note: str | None = None


class AddAnnotationRequest(BaseModel):
    highlighted_text: str
    offset_chars: int = 0
    note: str | None = None


class AddMessageRequest(BaseModel):
    message: str


class EnabledUpdate(BaseModel):
    enabled: bool


class CreateSourceRequest(BaseModel):
    url: str
    name: str
    category: str = "tech"
    slug: str | None = None

    def validated_slug(self, name: str) -> str:
        """Return a non-empty slug, normalised from name if not provided."""
        import re

        raw = self.slug or re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
        slug = re.sub(r"-{2,}", "-", raw).strip("-")[:80]
        if not slug:
            raise HTTPException(status_code=400, detail="slug must not be empty")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*[a-z0-9]|[a-z0-9]", slug):
            raise HTTPException(
                status_code=400,
                detail="slug must contain only lowercase letters, digits, and hyphens",
            )
        return slug


class SourceCleanupRequest(BaseModel):
    source_slugs: list[str]


class OnboardingInterestsRequest(BaseModel):
    interests: list[str]
    enabled_source_slugs: list[str] = Field(default_factory=list)
    disabled_source_slugs: list[str] = Field(default_factory=list)
    completed: bool = True


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


class GenerateUserRequest(BaseModel):
    username: str
    email: str | None = None
    is_admin: bool = False


class AnalyticsEvent(BaseModel):
    type: str
    route: str | None = None
    article_id: int | None = None
    feature: str | None = None
    duration_ms: int | None = None


class AnalyticsEventsRequest(BaseModel):
    events: list[AnalyticsEvent] = Field(max_length=MAX_EVENTS_PER_BATCH)


# ── Public auth routes (no session required) ──────────────────────────────────

public_router = APIRouter()


@public_router.get("/api/health")
def health() -> dict[str, Any]:
    init_db()
    return {"status": "ok"}


@public_router.get("/api/live")
def liveness() -> dict[str, Any]:
    return {"status": "ok"}


@public_router.get("/api/ready")
def readiness() -> dict[str, Any]:
    try:
        with connect() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok"}


@public_router.get("/api/auth/config")
def auth_config() -> dict[str, Any]:
    return keycloak_auth_metadata()


@public_router.get("/api/auth/metadata")
def auth_metadata() -> dict[str, Any]:
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


@public_router.get("/auth/register")
def keycloak_register() -> RedirectResponse:
    if not keycloak_config().enabled:
        return RedirectResponse(url="/login")
    state = secrets.token_urlsafe(32)
    redirect = RedirectResponse(url=keycloak_registration_url(state))
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
        max_age=_session_days() * 86400,
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
    if is_throttled(payload.username):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts; try again later",
        )
    user = authenticate(payload.username, payload.password)
    if not user:
        record_failure(payload.username)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    clear_failures(payload.username)
    token = create_session_token(user["id"], bool(user["is_admin"]))
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=_session_days() * 86400,
        path="/",
    )
    return {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])}


@public_router.get("/api/auth/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key=_SESSION_COOKIE, path="/")
    return {"status": "logged_out"}


@public_router.get("/api/articles/{article_id}/read")
def mark_read_via_token(article_id: int, token: Annotated[str, Query()]) -> dict[str, Any]:
    from news_dashboard.digest import verify_read_token

    if not verify_read_token(article_id, token):
        raise HTTPException(status_code=403, detail="invalid or expired token")
    try:
        article = set_article_status(article_id, "read")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return {"status": "marked_read", "article": article}


app.include_router(public_router)


def _embed_article_background(article_id: int) -> None:
    """Background task: generate embedding for a 'done' article, silently skipping on errors."""
    try:
        from news_dashboard.embeddings import ensure_article_embedded

        ensure_article_embedded(article_id)
    except Exception:
        logger.debug("Background embedding skipped for article %d", article_id, exc_info=True)


# ── Public version / changelog endpoints (no auth) ───────────────────────────

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"
_CHANGELOG_FILE = Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def _parse_changelog() -> list[dict[str, object]]:
    try:
        text = _CHANGELOG_FILE.read_text()
    except OSError:
        return []
    entries: list[dict[str, object]] = []
    current_version: str | None = None
    current_items: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_version is not None:
                entries.append({"version": current_version, "items": current_items})
            current_version = line[3:].strip()
            current_items = []
        elif line.startswith("- ") and current_version is not None:
            current_items.append(line[2:].strip())
    if current_version is not None:
        entries.append({"version": current_version, "items": current_items})
    return entries


@app.get("/api/version")
def version_endpoint() -> dict[str, str]:
    """Return the running app version from the VERSION file."""
    try:
        version = _VERSION_FILE.read_text().strip()
    except OSError:
        version = "unknown"
    return {"version": version}


@app.get("/api/changelog")
def changelog_endpoint() -> dict[str, object]:
    """Return changelog entries parsed from CHANGELOG.md."""
    try:
        version = _VERSION_FILE.read_text().strip()
    except OSError:
        version = "unknown"
    return {"version": version, "entries": _parse_changelog()}


# ── Authenticated API router ─────────────────────────────────────────────────

api = APIRouter(dependencies=[Depends(require_auth)])


@api.post("/api/events")
def ingest_events(
    payload: AnalyticsEventsRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Store a batch of client telemetry events for the current user."""
    stored = record_events(current_user["id"], [event.model_dump() for event in payload.events])
    return {"stored": stored}


@api.get("/api/auth/me")
def auth_me(current_user: Annotated[dict[str, Any], Depends(require_auth)]) -> dict[str, Any]:
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "email": current_user.get("email"),
        "is_admin": bool(current_user["is_admin"]),
    }


@api.post("/api/ingest", dependencies=[Depends(require_admin)])
def ingest(background_tasks: BackgroundTasks) -> dict[str, Any]:
    results = ingest_all()
    inserted = sum(v for v in results.values() if v > 0)
    if inserted > 0:
        background_tasks.add_task(prefetch_article_bodies)
    return {"results": results, "inserted": inserted}


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


@api.get("/api/articles/topic-map")
def articles_topic_map(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.insights import InsightsNotConfiguredError, cluster_recent_articles

    try:
        clusters = cluster_recent_articles(user_id=current_user["id"])
    except InsightsNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    return {"clusters": clusters}


@api.get("/api/articles/{article_id}")
def get_article_by_id(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    article = get_article(article_id, user_id=current_user["id"])
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@api.post("/api/articles/{article_id}/body")
def fetch_article_body(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    article = fetch_and_cache_body(article_id, user_id=current_user["id"])
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@api.post("/api/articles/{article_id}/audio")
def article_audio(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> FileResponse:
    from news_dashboard.tts import TTSNotConfiguredError, generate_audio

    article = get_article(article_id, user_id=current_user["id"])
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    try:
        path = generate_audio(article_id, article)
    except TTSNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(path, media_type="audio/mpeg", filename=f"article-{article_id}.mp3")


@api.get("/api/articles/{article_id}/insights")
def article_insights(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.insights import InsightsNotConfiguredError, get_or_generate_insights

    try:
        bullets = get_or_generate_insights(article_id, user_id=current_user["id"])
    except InsightsNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    if not bullets and not get_article(article_id, user_id=current_user["id"]):
        raise HTTPException(status_code=404, detail="article not found")

    return {"bullets": bullets}


@api.get("/api/articles/{article_id}/perspectives")
def article_perspectives(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.perspectives import (
        PerspectivesNotConfiguredError,
        get_or_generate_perspectives,
    )

    try:
        analysis = get_or_generate_perspectives(article_id, user_id=current_user["id"])
    except PerspectivesNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    if analysis is None:
        raise HTTPException(status_code=404, detail="article not found")

    return analysis


@api.patch("/api/articles/{article_id}/status")
def update_status(
    article_id: int,
    payload: StatusUpdate,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    legacy_state_map = {
        "read": "done",
        "skipped": "skipped",
        "archived": "archived",
        "new": "today",
        "saved": "today",
    }
    state = legacy_state_map.get(payload.status)
    if state is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid status: {payload.status!r} (expected one of {sorted(legacy_state_map)})"
            ),
        )

    try:
        article = transition_article_state(article_id, state, user_id=current_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    if payload.status == "saved":
        article = set_article_starred(article_id, True, user_id=current_user["id"])
        if not article:
            raise HTTPException(status_code=404, detail="article not found")
    return article


@api.patch("/api/articles/{article_id}/state")
def update_state(
    article_id: int,
    payload: StateUpdate,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    try:
        article = transition_article_state(article_id, payload.state, user_id=current_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    if payload.state == "done":
        background_tasks.add_task(_embed_article_background, article_id)
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


@api.get("/api/users")
def list_shareable_users(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares import shareable_users

    return {"items": shareable_users(current_user["id"])}


@api.post("/api/articles/{article_id}/share")
def share_article_endpoint(
    article_id: int,
    payload: ShareArticleRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    from news_dashboard.shares import ShareError, share_article

    try:
        share = share_article(
            article_id=article_id,
            from_user_id=current_user["id"],
            to_user_id=payload.to_user_id,
            note=payload.note,
        )
    except ShareError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    article = get_article(article_id, user_id=current_user["id"])
    title = article["title"] if article else "an article"
    background_tasks.add_task(
        _notify_share_recipient,
        to_user_id=payload.to_user_id,
        sender=current_user["username"],
        article_title=title,
    )
    background_tasks.add_task(_generate_share_context_bg, share_id=int(share["id"]))
    return share


def _notify_share_recipient(*, to_user_id: int, sender: str, article_title: str) -> None:
    from news_dashboard.push import send_push_for_user

    send_push_for_user(
        to_user_id,
        f"{sender} shared an article",
        article_title,
    )


def _generate_share_context_bg(*, share_id: int) -> None:
    from news_dashboard.shares import generate_share_context

    generate_share_context(share_id)


@api.get("/api/shares")
def list_shares(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares import list_received_shares, unread_share_count

    return {
        "items": list_received_shares(current_user["id"]),
        "unread": unread_share_count(current_user["id"]),
    }


@api.get("/api/shares/unread_count")
def shares_unread_count(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares import unread_share_count

    return {"unread": unread_share_count(current_user["id"])}


@api.post("/api/shares/{share_id}/read")
def mark_share_read_endpoint(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares import mark_share_read

    return {"ok": mark_share_read(share_id, current_user["id"])}


@api.get("/api/shares/{share_id}")
def get_share_endpoint(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares import get_share

    share = get_share(share_id, current_user["id"])
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return share


@api.get("/api/shares/{share_id}/annotations")
def list_share_annotations(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares import get_share, list_annotations

    if get_share(share_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"items": list_annotations(share_id)}


@api.post("/api/shares/{share_id}/annotations")
def add_share_annotation(
    share_id: int,
    payload: AddAnnotationRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    from news_dashboard.shares import add_annotation, get_share

    if get_share(share_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="Share not found")
    annotation = add_annotation(
        share_id,
        highlighted_text=payload.highlighted_text,
        offset_chars=payload.offset_chars,
        note=payload.note,
    )
    background_tasks.add_task(_generate_share_context_bg, share_id=share_id)
    return annotation


@api.get("/api/shares/{share_id}/messages")
def list_share_messages(
    share_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares import get_share, list_messages

    if get_share(share_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return {"items": list_messages(share_id)}


@api.post("/api/shares/{share_id}/messages")
def add_share_message(
    share_id: int,
    payload: AddMessageRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.shares import add_message, get_share

    if get_share(share_id, current_user["id"]) is None:
        raise HTTPException(status_code=404, detail="Share not found")
    return add_message(share_id, current_user["id"], payload.message)


INTEREST_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "id": "ai",
        "label": "AI",
        "options": (
            {"id": "agents", "label": "Agents"},
            {"id": "model-releases", "label": "Model releases"},
            {"id": "evals", "label": "Evals"},
            {"id": "product-news", "label": "Product news"},
        ),
    },
    {
        "id": "engineering",
        "label": "Engineering",
        "options": (
            {"id": "python", "label": "Python"},
            {"id": "infra", "label": "Infrastructure"},
            {"id": "cloud", "label": "Cloud"},
            {"id": "security", "label": "Security"},
        ),
    },
)


def _interest_options() -> set[str]:
    return {str(option["id"]) for group in INTEREST_GROUPS for option in group["options"]}


def _source_recommendations(user_id: int, interests: list[str]) -> list[dict[str, Any]]:
    from news_dashboard.ingest import sync_sources
    from news_dashboard.sources import DEFAULT_SOURCES

    selected = set(interests)
    sync_sources()
    with connect() as conn:
        rows = conn.execute(
            "SELECT source_slug, enabled FROM user_sources WHERE user_id = %s",
            (user_id,),
        ).fetchall()
    subscriptions = {str(row["source_slug"]): bool(row["enabled"]) for row in rows}

    recommendations: list[dict[str, Any]] = []
    for source in DEFAULT_SOURCES:
        tags = set(source.interest_tags)
        matched = sorted(selected & (tags | {source.category}))
        score = float((len(selected & tags) * 100) + (25 if source.category in selected else 0))
        score += source.priority / 100
        recommended = bool(matched)
        if not selected:
            score = source.priority / 100
            recommended = False
        reason = (
            f"Matches {', '.join(matched)}" if matched else f"Baseline {source.category} source"
        )
        recommendations.append(
            {
                "source_slug": source.slug,
                "source_name": source.name,
                "kind": source.kind,
                "url": source.url,
                "category": source.category,
                "matched_interests": matched,
                "reason": reason,
                "recommended": recommended,
                "subscribed": subscriptions.get(source.slug, False),
                "priority": source.priority,
                "_score": score,
                "_priority": source.priority,
            }
        )

    recommendations.sort(
        key=lambda item: (
            float(item["_score"]),
            bool(item["subscribed"]),
            int(item["_priority"]),
            str(item["source_name"]),
        ),
        reverse=True,
    )
    for item in recommendations:
        item.pop("_score")
        item.pop("_priority")
    return recommendations


@api.get("/api/onboarding/status")
def onboarding_status(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    uid = int(current_user["id"])
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT completed_at FROM user_interest_profiles WHERE user_id = %s",
            (uid,),
        ).fetchone()
    completed = row is not None and row["completed_at"] is not None
    return {"completed": completed}


@api.get("/api/onboarding/interests")
def onboarding_interests(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> list[dict[str, Any]]:
    _ = current_user
    return [
        {"id": option["id"], "label": option["label"], "description": option.get("description", "")}
        for group in INTEREST_GROUPS
        for option in group["options"]
    ]


class OnboardingRecommendationsRequest(BaseModel):
    interest_ids: list[str]


class OnboardingProfileRequest(BaseModel):
    interest_ids: list[str]
    enabled_slugs: list[str] = Field(default_factory=list)


def _frontend_recommendations(user_id: int, interests: list[str]) -> list[dict[str, Any]]:
    """Return source recommendations using the frontend field-name contract (slug, name)."""
    raw = _source_recommendations(user_id, interests)
    return [
        {
            "slug": item["source_slug"],
            "name": item["source_name"],
            "category": item["category"],
            "kind": item["kind"],
            "url": item["url"],
            "matched_interests": item["matched_interests"],
            "reason": item["reason"],
            "recommended": item["recommended"],
            "enabled": 1 if item["subscribed"] else 0,
            "priority": item["priority"],
        }
        for item in raw
    ]


@api.post("/api/onboarding/recommendations")
def onboarding_recommendations(
    payload: OnboardingRecommendationsRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> list[dict[str, Any]]:
    uid = int(current_user["id"])
    init_db()
    return _frontend_recommendations(uid, payload.interest_ids)


@api.post("/api/onboarding/profile")
def save_onboarding_profile(
    payload: OnboardingProfileRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.ingest import sync_sources

    valid_interests = _interest_options()
    interests = list(dict.fromkeys(payload.interest_ids))
    invalid = [i for i in interests if i not in valid_interests]
    if invalid:
        raise HTTPException(status_code=400, detail=f"unknown interests: {', '.join(invalid)}")

    uid = int(current_user["id"])
    enabled_slugs = list(dict.fromkeys(payload.enabled_slugs))
    sync_sources()
    with connect() as conn:
        if enabled_slugs:
            rows = conn.execute(
                "SELECT slug FROM sources WHERE owner_user_id IS NULL AND slug = ANY(%s)",
                (enabled_slugs,),
            ).fetchall()
            allowed = {str(row["slug"]) for row in rows}
            missing = [slug for slug in enabled_slugs if slug not in allowed]
            if missing:
                raise HTTPException(
                    status_code=404, detail=f"unknown global sources: {', '.join(missing)}"
                )

        conn.execute(
            """
            INSERT INTO user_interest_profiles(user_id, interests, completed_at, updated_at)
            VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT(user_id) DO UPDATE SET
              interests = excluded.interests,
              completed_at = NOW(),
              updated_at = NOW()
            """,
            (uid, Jsonb(interests)),
        )
        for slug in enabled_slugs:
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (%s, %s, TRUE)
                ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = TRUE
                """,
                (uid, slug),
            )

    return {"completed": True}


@api.get("/api/onboarding/source-recommendations")
def onboarding_source_recommendations(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    uid = int(current_user["id"])
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT interests FROM user_interest_profiles WHERE user_id = %s",
            (uid,),
        ).fetchone()
    interests = list(row["interests"]) if row else []
    return {"items": _source_recommendations(uid, [str(interest) for interest in interests])}


@api.post("/api/onboarding/interests")
def save_onboarding_interests(
    payload: OnboardingInterestsRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.ingest import sync_sources

    valid_interests = _interest_options()
    interests = list(dict.fromkeys(payload.interests))
    invalid = [interest for interest in interests if interest not in valid_interests]
    if invalid:
        raise HTTPException(status_code=400, detail=f"unknown interests: {', '.join(invalid)}")

    uid = int(current_user["id"])
    requested = list(dict.fromkeys(payload.enabled_source_slugs + payload.disabled_source_slugs))
    sync_sources()
    with connect() as conn:
        if requested:
            rows = conn.execute(
                "SELECT slug FROM sources WHERE owner_user_id IS NULL AND slug = ANY(%s)",
                (requested,),
            ).fetchall()
            allowed = {str(row["slug"]) for row in rows}
            missing = [slug for slug in requested if slug not in allowed]
            if missing:
                detail = f"unknown global sources: {', '.join(missing)}"
                raise HTTPException(status_code=404, detail=detail)

        conn.execute(
            """
            INSERT INTO user_interest_profiles(user_id, interests, completed_at, updated_at)
            VALUES (%s, %s, CASE WHEN %s THEN NOW() ELSE NULL END, NOW())
            ON CONFLICT(user_id) DO UPDATE SET
              interests = excluded.interests,
              completed_at = excluded.completed_at,
              updated_at = NOW()
            """,
            (uid, Jsonb(interests), payload.completed),
        )
        for slug in payload.enabled_source_slugs:
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (%s, %s, TRUE)
                ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = TRUE
                """,
                (uid, slug),
            )
        for slug in payload.disabled_source_slugs:
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (%s, %s, FALSE)
                ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = FALSE
                """,
                (uid, slug),
            )

    return {
        "interests": interests,
        "items": _source_recommendations(uid, interests),
    }


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
              CASE WHEN s.owner_user_id IS NULL THEN COALESCE(us.enabled, true)
                   ELSE (s.enabled IS TRUE) END AS user_enabled
            FROM sources s
            LEFT JOIN user_sources us ON us.source_slug = s.slug AND us.user_id = %s
            WHERE s.owner_user_id IS NULL OR s.owner_user_id = %s
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
    from urllib.parse import urlparse

    uid = current_user["id"]

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name must not be empty")

    parsed = urlparse(payload.url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="url must use http or https scheme")
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="url must include a valid host")

    slug = payload.validated_slug(payload.name)

    init_db()
    with connect() as conn:
        existing = conn.execute("SELECT 1 FROM sources WHERE slug = %s", (slug,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"source slug '{slug}' already exists")
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
            VALUES (%s, %s, %s, %s, 'rss_feed', 0, TRUE, %s)
            """,
            (slug, payload.name.strip(), payload.url, payload.category, uid),
        )
        row = conn.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
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
        row = conn.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="source not found")
        src = row_to_dict(row)
        if src.get("owner_user_id") != uid:
            raise HTTPException(status_code=403, detail="cannot delete a source you don't own")
        conn.execute("DELETE FROM sources WHERE slug = %s", (slug,))
    return {"status": "deleted"}


@api.get("/api/sources/health")
def sources_health() -> dict[str, Any]:
    return {"items": list_source_health()}


@api.get("/api/sources/cleanup-suggestions")
def source_cleanup_suggestions(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": generate_subscription_cleanup_suggestions(int(current_user["id"]))}


@api.post("/api/sources/cleanup")
def source_cleanup(
    payload: SourceCleanupRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    uid = int(current_user["id"])
    requested_slugs = list(dict.fromkeys(payload.source_slugs))
    if not requested_slugs:
        return {"updated": [], "skipped": []}

    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT slug, owner_user_id
            FROM sources
            WHERE slug = ANY(%s)
              AND (owner_user_id IS NULL OR owner_user_id = %s)
            """,
            (requested_slugs, uid),
        ).fetchall()
        allowed = {str(row["slug"]): row_to_dict(row) for row in rows}
        updated: list[str] = []
        for slug in requested_slugs:
            source = allowed.get(slug)
            if source is None:
                continue
            if source.get("owner_user_id") is None:
                conn.execute(
                    """
                    INSERT INTO user_sources(user_id, source_slug, enabled)
                    VALUES (%s, %s, FALSE)
                    ON CONFLICT(user_id, source_slug)
                    DO UPDATE SET enabled = excluded.enabled
                    """,
                    (uid, slug),
                )
            else:
                conn.execute(
                    "UPDATE sources SET enabled = FALSE WHERE slug = %s AND owner_user_id = %s",
                    (slug, uid),
                )
            updated.append(slug)

    return {
        "updated": updated,
        "skipped": [slug for slug in requested_slugs if slug not in updated],
    }


# ── Personalization nudges ────────────────────────────────────────────────────


class NudgeActionRequest(BaseModel):
    nudge_id: str


class NudgeDismissRequest(BaseModel):
    nudge_id: str
    cooldown_days: int = 7


@api.get("/api/personalization/nudges")
def get_personalization_nudges(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.personalization_nudges import generate_nudges

    return {"items": generate_nudges(int(current_user["id"]))}


@api.post("/api/personalization/nudges/apply")
def apply_personalization_nudge(
    payload: NudgeActionRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.personalization_nudges import apply_nudge

    return apply_nudge(int(current_user["id"]), payload.nudge_id)


@api.post("/api/personalization/nudges/dismiss")
def dismiss_personalization_nudge(
    payload: NudgeDismissRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.personalization_nudges import dismiss_nudge

    return dismiss_nudge(
        int(current_user["id"]),
        payload.nudge_id,
        cooldown_days=payload.cooldown_days,
    )


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
        row = conn.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="source not found")
        src = row_to_dict(row)
        if src.get("owner_user_id") is None:
            # Global source — write to user_sources subscription table
            conn.execute(
                """
                INSERT INTO user_sources(user_id, source_slug, enabled)
                VALUES (%s, %s, %s)
                ON CONFLICT(user_id, source_slug) DO UPDATE SET enabled = excluded.enabled
                """,
                (uid, slug, bool(payload.enabled)),
            )
        else:
            # Private source — only owner can change
            if src.get("owner_user_id") != uid:
                raise HTTPException(status_code=403, detail="cannot modify a source you don't own")
            conn.execute(
                "UPDATE sources SET enabled = %s WHERE slug = %s",
                (bool(payload.enabled), slug),
            )
        row = conn.execute("SELECT * FROM sources WHERE slug = %s", (slug,)).fetchone()
    return {**row_to_dict(row), "subscribed": payload.enabled}


@api.get("/api/scheduler/status")
def scheduler_status() -> dict[str, Any]:
    interval_enabled = is_ingest_interval_enabled()
    next_run = get_next_ingest_at()
    paused = is_paused() if interval_enabled else False
    return {
        "interval_minutes": get_interval_minutes(),
        "paused": paused,
        "next_run_at": next_run,
        "interval_ingest_enabled": interval_enabled,
        "ingest_authority": "in_process" if interval_enabled else "external",
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


@api.get("/api/health/details", dependencies=_admin_dep)
def health_details() -> dict[str, Any]:
    init_db()
    return {
        "status": "ok",
        "database": describe_database(),
        "next_ingest_at": get_next_ingest_at(),
    }


@api.get("/api/recommendations/health", dependencies=_admin_dep)
def recommendations_health_endpoint() -> dict[str, Any]:
    from news_dashboard.recommendation_jobs import recommendation_health

    return recommendation_health()


@api.post("/api/recommendations/recalculate", dependencies=_admin_dep)
def recommendations_recalculate_endpoint() -> dict[str, Any]:
    from news_dashboard.recommendation_jobs import recalculate_stale_recommendations

    return recalculate_stale_recommendations().as_dict()


@api.post("/api/recommendations/recalculate-mine")
def recommendations_recalculate_mine_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, int]:
    """Recompute the calling user's own recommendation scores on demand.

    Lets any authenticated user personalize their feed from the UI without the
    admin-only stale sweep above. Returns the number of articles scored so the
    client can tell the user whether personalization has anything to learn from
    yet (zero means no interaction history exists).
    """
    from news_dashboard.recommendations import recompute_user_recommendations

    scored = recompute_user_recommendations(current_user["id"])
    return {"scored": scored}


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


@api.post("/api/briefings/{briefing_id}/podcast")
def generate_podcast_endpoint(
    briefing_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, str]:
    from news_dashboard.briefings import update_briefing_script
    from news_dashboard.tts import (
        TTSNotConfiguredError,
        _podcast_audio_path,
        generate_podcast_audio,
        generate_podcast_script,
    )

    briefing = get_briefing(briefing_id, user_id=current_user["id"])
    if not briefing:
        raise HTTPException(status_code=404, detail="briefing not found")

    audio_path = _podcast_audio_path(briefing_id)
    if not audio_path.exists():
        script = briefing.get("script")
        if not script:
            content_dict = {
                "title": briefing.get("title", ""),
                "summary": briefing.get("summary", ""),
                "sections": briefing.get("content", {}).get("sections", []),
            }
            try:
                script = generate_podcast_script(content_dict)
                update_briefing_script(briefing_id, script)
            except TTSNotConfiguredError as exc:
                raise HTTPException(status_code=501, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"Failed to generate podcast script: {exc}"
                ) from exc

        try:
            generate_podcast_audio(briefing_id, script)
        except TTSNotConfiguredError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"url": f"/api/briefings/{briefing_id}/podcast"}


@api.get("/api/briefings/{briefing_id}/podcast")
def get_podcast_audio_endpoint(
    briefing_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> FileResponse:
    from news_dashboard.tts import _podcast_audio_path

    briefing = get_briefing(briefing_id, user_id=current_user["id"])
    if not briefing:
        raise HTTPException(status_code=404, detail="briefing not found")

    audio_path = _podcast_audio_path(briefing_id)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="podcast audio file not found")

    return FileResponse(audio_path, media_type="audio/mpeg", filename=f"podcast-{briefing_id}.mp3")


class BriefingCreateRequest(BaseModel):
    focus_prompt: str | None = None


@api.post("/api/briefings")
def briefings_create(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: BriefingCreateRequest | None = None,
) -> dict[str, Any]:
    try:
        focus = payload.focus_prompt if payload is not None else None
        return generate_briefing(user_id=current_user["id"], focus_prompt=focus)
    except BriefingAINotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BriefingGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class BriefingChatMessage(BaseModel):
    role: str
    content: str


class BriefingChatRequest(BaseModel):
    message: str
    history: list[BriefingChatMessage] = []


@api.post("/api/briefings/{briefing_id}/chat")
def briefings_chat(
    briefing_id: int,
    body: BriefingChatRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        reply = chat_with_briefing(
            briefing_id,
            body.message,
            [{"role": m.role, "content": m.content} for m in body.history],
            user_id=current_user["id"],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="briefing not found") from exc
    except BriefingAINotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"reply": reply}


# ── Notification settings & push subscriptions ───────────────────────────────

_BRIEFING_TIME_RE = __import__("re").compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class NotificationSettingsUpdate(BaseModel):
    briefing_time: str | None = None
    push_enabled: bool | None = None


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class RecommendationPreferencesUpdate(BaseModel):
    category_weights: dict[str, float] | None = None
    novelty_weight: float | None = None


def _preference_payload(preferences: Any) -> dict[str, Any]:
    return {
        "category_weights": preferences.category_weights,
        "novelty_weight": preferences.novelty_weight,
    }


@api.get("/api/users/me/reading-dna")
def reading_dna_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    return reading_dna(current_user["id"], days=days)


@api.get("/api/users/me/recommendation-preferences")
def get_recommendation_preferences_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.recommendations import get_recommendation_preferences

    return _preference_payload(get_recommendation_preferences(current_user["id"]))


@api.patch("/api/users/me/recommendation-preferences")
def update_recommendation_preferences_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: RecommendationPreferencesUpdate,
) -> dict[str, Any]:
    from news_dashboard.recommendations import (
        recompute_user_recommendations,
        save_recommendation_preferences,
    )

    preferences = save_recommendation_preferences(
        current_user["id"],
        category_weights=payload.category_weights,
        novelty_weight=payload.novelty_weight,
    )
    scored = recompute_user_recommendations(current_user["id"])
    return {**_preference_payload(preferences), "recomputed": scored}


@api.get("/api/settings/notifications")
def get_notification_settings(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.push import get_vapid_public_key

    uid = current_user["id"]
    with connect() as conn:
        row = conn.execute(
            "SELECT briefing_time, briefing_push_enabled FROM users WHERE id = %s",
            (uid,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    return {
        "briefing_time": row["briefing_time"] or "09:00",
        "push_enabled": bool(row["briefing_push_enabled"]),
        "vapid_public_key": get_vapid_public_key(),
    }


@api.put("/api/settings/notifications")
def update_notification_settings(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: NotificationSettingsUpdate,
) -> dict[str, Any]:
    uid = current_user["id"]
    updates: dict[str, Any] = {}
    if payload.briefing_time is not None:
        if not _BRIEFING_TIME_RE.match(payload.briefing_time):
            raise HTTPException(status_code=422, detail="briefing_time must be HH:MM (00:00-23:59)")
        updates["briefing_time"] = payload.briefing_time
    if payload.push_enabled is not None:
        updates["briefing_push_enabled"] = payload.push_enabled
    if updates:
        set_clauses = ", ".join(f"{k} = %s" for k in updates)
        with connect() as conn:
            conn.execute(
                f"UPDATE users SET {set_clauses} WHERE id = %s",
                [*updates.values(), uid],
            )
    with connect() as conn:
        row = conn.execute(
            "SELECT briefing_time, briefing_push_enabled FROM users WHERE id = %s",
            (uid,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    return {
        "briefing_time": row["briefing_time"] or "09:00",
        "push_enabled": bool(row["briefing_push_enabled"]),
    }


@api.post("/api/notifications/subscribe")
def push_subscribe(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: PushSubscribeRequest,
) -> dict[str, Any]:
    from news_dashboard.push import save_push_subscription

    save_push_subscription(
        current_user["id"],
        payload.endpoint,
        payload.p256dh,
        payload.auth,
    )
    return {"subscribed": True}


@api.delete("/api/notifications/subscribe")
def push_unsubscribe(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.push import delete_push_subscriptions

    delete_push_subscriptions(current_user["id"])
    return {"unsubscribed": True}


class AskRequest(BaseModel):
    query: str
    include_all: bool = False


@api.post("/api/ask")
def ask_ai(
    payload: AskRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.embeddings import ask

    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query must not be empty")
    try:
        return ask(q, include_all=payload.include_all, user_id=current_user["id"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class FeedbackRequest(BaseModel):
    trace_id: str
    helpful: bool
    comment: str | None = None


@api.post("/api/feedback")
def submit_feedback(
    payload: FeedbackRequest,
    _current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Record a user's thumbs up/down on an AI answer as a Langfuse score.

    The Langfuse keys stay server-side: the frontend posts the ``trace_id`` it
    received from ``/api/ask`` plus a boolean, and we attach a ``user-thumbs``
    BOOLEAN score to that trace. A no-op (``recorded: False``) when Langfuse is
    disabled, so feedback never errors for the user.
    """
    from news_dashboard.ai_client import create_score

    comment = (payload.comment or "").strip() or None
    recorded = create_score(
        payload.trace_id,
        name="user-thumbs",
        value=1 if payload.helpful else 0,
        data_type="BOOLEAN",
        comment=comment,
    )
    return {"recorded": recorded}


@api.get("/api/summary")
def summary(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return get_user_summary(user_id=current_user["id"])


# ── Reading Goals & Quizzes ───────────────────────────────────────────────────


class GoalCreateRequest(BaseModel):
    description: str
    keywords: str = ""


class QuizSubmitRequest(BaseModel):
    answers: list[int]


@api.post("/api/goals")
def create_goal_endpoint(
    payload: GoalCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.quiz import create_goal

    description = payload.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="description must not be empty")
    return create_goal(current_user["id"], description, payload.keywords)


@api.get("/api/goals")
def list_goals_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.quiz import list_goals

    return {"items": list_goals(current_user["id"])}


@api.delete("/api/goals/{goal_id}")
def delete_goal_endpoint(
    goal_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.quiz import delete_goal

    if not delete_goal(goal_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="goal not found")
    return {"deleted": True}


@api.get("/api/quizzes/candidates")
def get_quiz_candidates_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.quiz import get_quiz_candidate_articles

    candidates = get_quiz_candidate_articles(current_user["id"])
    return {"candidates": candidates}


@api.get("/api/quizzes/latest")
def get_latest_quiz_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.quiz import get_latest_quiz

    quiz = get_latest_quiz(current_user["id"])
    if not quiz:
        raise HTTPException(status_code=404, detail="no quiz available")
    return quiz


@api.get("/api/quizzes")
def list_quizzes_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    from news_dashboard.quiz import list_quizzes

    return {"items": list_quizzes(current_user["id"], limit=limit, offset=offset)}


@api.post("/api/quizzes/generate")
def generate_quiz_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.quiz import generate_weekly_quiz

    try:
        quiz = generate_weekly_quiz(current_user["id"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not quiz:
        raise HTTPException(status_code=404, detail="no eligible articles to quiz on")
    return quiz


@api.post("/api/quizzes/{quiz_id}/submit")
def submit_quiz_endpoint(
    quiz_id: int,
    payload: QuizSubmitRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.quiz import submit_quiz

    try:
        return submit_quiz(quiz_id, current_user["id"], payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Admin user-management routes ─────────────────────────────────────────────

admin = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


@admin.get("/analytics")
def admin_get_analytics(days: Annotated[int, Query(ge=1, le=365)] = 30) -> dict[str, Any]:
    return admin_analytics(days=days)


@admin.get("/ai/metrics")
def admin_ai_metrics(days: Annotated[int, Query(ge=1, le=365)] = 30) -> dict[str, Any]:
    """Aggregate AI usage/cost/feedback metrics from Langfuse for admins.

    Returns ``{"enabled": False}`` when Langfuse tracing is not configured.
    """
    from news_dashboard.ai_client import fetch_metrics

    return fetch_metrics(days=days)


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


@admin.post("/users/generate")
async def admin_generate_user(payload: GenerateUserRequest) -> dict[str, Any]:
    """Create a user with a server-generated password and return the credentials.

    The plaintext password is returned exactly once here so the admin can hand it
    to the new user; it is never stored or retrievable afterwards.

    When Keycloak SSO is enabled, local password login is disabled, so the user
    must be created in Keycloak (with a one-time temporary password) for the
    credentials to actually work. Otherwise the user is created in the local
    ``users`` table.
    """
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="username is required")
    password = secrets.token_urlsafe(12)

    if keycloak_config().enabled:
        from news_dashboard.keycloak_admin import create_keycloak_user

        result = await create_keycloak_user(username, password, email=payload.email)
        return {**result, "password": password, "provider": "keycloak"}

    try:
        user = create_user(
            username,
            password,
            email=payload.email,
            is_admin=payload.is_admin,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {**user, "password": password, "provider": "password", "temporary": False}


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
