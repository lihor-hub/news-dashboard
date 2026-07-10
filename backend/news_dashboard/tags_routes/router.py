"""HTTP routes for the tags routes domain."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from psycopg.errors import UniqueViolation

from news_dashboard.auth import (
    require_auth,
)
from news_dashboard.tags_routes import service
from news_dashboard.tags_routes.models import (
    ArticleTagRequest,
    TagCreateRequest,
    TagRenameRequest,
)

router = APIRouter()


@router.post("/api/tags")
def create_tag_endpoint(
    payload: TagCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    try:
        return service.create_tag(current_user["id"], name, payload.color)
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="tag already exists") from exc


@router.get("/api/tags")
def list_tags_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_tags(current_user["id"])}


@router.patch("/api/tags/{tag_id}")
def rename_tag_endpoint(
    tag_id: int,
    payload: TagRenameRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    try:
        tag = service.rename_tag(tag_id, current_user["id"], name)
    except UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="tag already exists") from exc
    if not tag:
        raise HTTPException(status_code=404, detail="tag not found")
    return tag


@router.delete("/api/tags/{tag_id}")
def delete_tag_endpoint(
    tag_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if not service.delete_tag(tag_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="tag not found")
    return {"deleted": True}


@router.get("/api/tags/{tag_id}/articles")
def list_articles_by_tag_endpoint(
    tag_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    items = service.list_articles(
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


@router.get("/api/articles/{article_id}/tags")
def list_article_tags_endpoint(
    article_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_tags_for_article(current_user["id"], article_id)}


@router.post("/api/articles/{article_id}/tags")
def add_article_tag_endpoint(
    article_id: int,
    payload: ArticleTagRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if not service.get_article(article_id, user_id=current_user["id"]):
        raise HTTPException(status_code=404, detail="article not found")
    if not service.add_tag_to_article(current_user["id"], article_id, payload.tag_id):
        raise HTTPException(status_code=404, detail="tag not found")
    return {"added": True}


@router.delete("/api/articles/{article_id}/tags/{tag_id}")
def remove_article_tag_endpoint(
    article_id: int,
    tag_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if not service.remove_tag_from_article(current_user["id"], article_id, tag_id):
        raise HTTPException(status_code=404, detail="article tag not found")
    return {"removed": True}
