"""HTTP routes for the reading list.

The router carries no blanket auth dependency of its own; it is mounted on
``main``'s authenticated ``api`` router, which applies ``require_auth``. Each
handler still depends on ``require_auth`` to receive the current user.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response

from news_dashboard.auth import require_auth
from news_dashboard.reading_list import service
from news_dashboard.reading_list.models import (
    ReadingListAddRequest,
    ReadingListReorderRequest,
    ReadingListUpdateRequest,
)

router = APIRouter()


@router.post("/api/reading-list", status_code=201)
def add_reading_list_item_endpoint(
    payload: ReadingListAddRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        item = service.add_item(current_user["id"], payload.url, payload.note)
    except service.InvalidReadingListUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item.pop("created", False):
        background_tasks.add_task(service.fetch_metadata_for_item, item["id"])
    else:
        response.status_code = 200
    return item


@router.get("/api/reading-list")
def list_reading_list_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    status: Annotated[str | None, Query(pattern="^(unread|done|archived)$")] = None,
) -> dict[str, Any]:
    return {"items": service.list_items(current_user["id"], status)}


@router.post("/api/reading-list/reorder")
def reorder_reading_list_endpoint(
    payload: ReadingListReorderRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.reorder_items(current_user["id"], payload.ordered_ids)}


@router.patch("/api/reading-list/{item_id}")
def update_reading_list_item_endpoint(
    item_id: int,
    payload: ReadingListUpdateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    item = service.update_item(
        current_user["id"], item_id, status=payload.status, note=payload.note
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Reading list item not found")
    return item


@router.delete("/api/reading-list/{item_id}")
def delete_reading_list_item_endpoint(
    item_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if not service.delete_item(current_user["id"], item_id):
        raise HTTPException(status_code=404, detail="Reading list item not found")
    return {"deleted": True}
