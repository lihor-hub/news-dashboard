"""HTTP routes for reusable saved search views."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from news_dashboard.auth import require_auth
from news_dashboard.saved_searches import service
from news_dashboard.saved_searches.models import (
    SavedSearchCreateRequest,
    SavedSearchUpdateRequest,
)

router = APIRouter()


@router.get("/api/search/saved")
def list_saved_searches_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_saved_searches(current_user["id"])}


@router.post("/api/search/saved")
def create_saved_search_endpoint(
    payload: SavedSearchCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name must not be empty")
    return service.create_saved_search(current_user["id"], payload.name, payload.filters)


@router.patch("/api/search/saved/{search_id}")
def update_saved_search_endpoint(
    search_id: int,
    payload: SavedSearchUpdateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if payload.name is not None and not payload.name.strip():
        raise HTTPException(status_code=400, detail="name must not be empty")
    saved = service.update_saved_search(
        search_id,
        current_user["id"],
        name=payload.name,
        filters=payload.filters,
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="saved search not found")
    return saved


@router.delete("/api/search/saved/{search_id}")
def delete_saved_search_endpoint(
    search_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, bool]:
    if not service.delete_saved_search(search_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="saved search not found")
    return {"deleted": True}
