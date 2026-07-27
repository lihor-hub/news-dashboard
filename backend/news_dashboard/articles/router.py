"""HTTP routes for the articles domain."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
)
from fastapi.responses import FileResponse

from news_dashboard.articles import service
from news_dashboard.articles.models import (
    LaterUpdate,
    SaveSharedUrlRequest,
    StarUpdate,
    StateUpdate,
    StatusUpdate,
)
from news_dashboard.auth import (
    require_auth,
)
from news_dashboard.body_fetch import fetch_and_cache_body, get_article
from news_dashboard.ingest.service import (
    list_articles,
    search_articles_page,
    send_article_later,
    set_article_starred,
    transition_article_state,
)
from news_dashboard.shares.models import AddAnnotationRequest
from news_dashboard.url_safety import UnsafeUrlError

router = APIRouter()
public_router = APIRouter()


@public_router.get("/api/articles/{article_id}/read")
def mark_read_via_token(article_id: int, token: Annotated[str, Query()]) -> dict[str, Any]:
    from news_dashboard.digest import verify_read_token

    user_id = verify_read_token(article_id, token)
    if user_id is None:
        raise HTTPException(status_code=403, detail="invalid or expired token")
    try:
        article = transition_article_state(article_id, "done", user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return {"status": "marked_read", "article": article}


@router.get("/api/articles")
def articles(  # noqa: PLR0913, PLR0917
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    status: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    starred: Annotated[bool | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    tag_id: Annotated[int | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items = list_articles(
        status=status,
        state=state,
        starred=starred,
        category=category,
        tag_id=tag_id,
        limit=limit + 1,
        offset=offset,
        user_id=current_user["id"],
    )
    return {
        "items": items[:limit],
        "limit": limit,
        "offset": offset,
        "has_more": len(items) > limit,
    }


@router.get("/api/search")
def search(  # noqa: PLR0913, PLR0917
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    q: Annotated[str, Query(description="Space-separated search terms")] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    states: Annotated[list[str] | None, Query()] = None,
    categories: Annotated[list[str] | None, Query()] = None,
    sources: Annotated[list[str] | None, Query()] = None,
    starred_only: Annotated[bool, Query()] = False,
    include_archived: Annotated[bool, Query()] = False,
    date_range: Annotated[str, Query()] = "all",
    tag_id: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    return search_articles_page(
        q=q.strip(),
        limit=limit,
        offset=offset,
        states=states,
        categories=categories,
        sources=sources,
        starred_only=starred_only,
        include_archived=include_archived,
        date_range=date_range,
        user_id=current_user["id"],
        tag_id=tag_id,
    )


@router.get("/api/articles/topic-map")
def articles_topic_map(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.insights import InsightsNotConfiguredError, cluster_recent_articles

    try:
        clusters = cluster_recent_articles(user_id=current_user["id"])
    except InsightsNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    return {"clusters": clusters}


@router.get("/api/articles/{article_id}")
def get_article_by_id(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    article = get_article(article_id, user_id=current_user["id"])
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@router.post("/api/articles/save-url")
def save_shared_url(
    payload: SaveSharedUrlRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.save_shared_url(
            current_user["id"], url=payload.url, title=payload.title, text=payload.text
        )
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/articles/{article_id}/body")
@router.post("/api/articles/{article_id}/body")
def fetch_article_body(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    article = fetch_and_cache_body(article_id, user_id=current_user["id"])
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@router.post("/api/articles/{article_id}/audio")
def article_audio(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> FileResponse:
    from news_dashboard.tts import TTSNotConfiguredError, article_audio_path, generate_audio

    article = get_article(article_id, user_id=current_user["id"])
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    canonical_article_id = int(article["id"])
    try:
        generate_audio(canonical_article_id, article)
    except TTSNotConfiguredError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(
        article_audio_path(canonical_article_id),
        media_type="audio/mpeg",
        filename=f"article-{canonical_article_id}.mp3",
    )


@router.get("/api/articles/{article_id}/highlights")
def list_article_highlights(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.personal_highlights import list_highlights

    highlights = list_highlights(article_id, current_user["id"])
    if highlights is None:
        raise HTTPException(status_code=404, detail="article not found")
    return {"items": highlights}


@router.post("/api/articles/{article_id}/highlights")
def add_article_highlight(
    article_id: int,
    payload: AddAnnotationRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.personal_highlights import add_highlight

    highlight = add_highlight(
        article_id,
        current_user["id"],
        highlighted_text=payload.highlighted_text,
        offset_chars=payload.offset_chars,
        note=payload.note,
    )
    if highlight is None:
        raise HTTPException(status_code=404, detail="article not found")
    return highlight


@router.delete("/api/articles/{article_id}/highlights/{highlight_id}")
def delete_article_highlight(
    article_id: int,
    highlight_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, bool]:
    from news_dashboard.personal_highlights import delete_highlight

    deleted = delete_highlight(article_id, current_user["id"], highlight_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="article not found")
    return {"ok": deleted}


@router.get("/api/articles/{article_id}/insights")
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


@router.get("/api/articles/{article_id}/perspectives")
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


@router.patch("/api/articles/{article_id}/status")
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


@router.patch("/api/articles/{article_id}/state")
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
        background_tasks.add_task(service.embed_article_background, article_id)
    return article


@router.patch("/api/articles/{article_id}/star")
def update_star(
    article_id: int,
    payload: StarUpdate,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    article = set_article_starred(article_id, payload.starred, user_id=current_user["id"])
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@router.patch("/api/articles/{article_id}/later")
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
