"""HTTP routes for the reading list.

The router carries no blanket auth dependency of its own; it is mounted on
``main``'s authenticated ``api`` router, which applies ``require_auth``. Each
handler still depends on ``require_auth`` to receive the current user.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)

from news_dashboard.auth import require_auth
from news_dashboard.reading_list import service
from news_dashboard.reading_list.importers import (
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ITEMS,
    PARSERS,
    ImportParseError,
)
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


@router.post("/api/reading-list/import")
async def import_reading_list_endpoint(
    request: Request,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    file: Annotated[UploadFile, File()],
    source: Annotated[str, Form()],
) -> dict[str, Any]:
    """Import saved articles from a Pocket, Instapaper, or Omnivore export."""
    parser = PARSERS.get(source.strip().lower())
    if parser is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported import source {source!r}; expected one of {sorted(PARSERS)}",
        )

    declared_length = request.headers.get("content-length")
    if (
        declared_length is not None
        and declared_length.isdigit()
        and int(declared_length) > MAX_IMPORT_BYTES
    ):
        raise HTTPException(
            status_code=413,
            detail=f"Import file exceeds the {MAX_IMPORT_BYTES}-byte limit",
        )

    contents = await file.read(MAX_IMPORT_BYTES + 1)
    if len(contents) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Import file exceeds the {MAX_IMPORT_BYTES}-byte limit",
        )

    try:
        items = parser(contents)
    except ImportParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = service.import_items(current_user["id"], items, max_items=MAX_IMPORT_ITEMS)
    except service.ImportTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return result


@router.get("/api/reading-list")
def list_reading_list_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    status: Annotated[str | None, Query(pattern="^(unread|done|archived)$")] = None,
    q: Annotated[str | None, Query(max_length=300)] = None,
    kind: Annotated[str | None, Query(pattern="^(article|video|channel|link)$")] = None,
) -> dict[str, Any]:
    return {"items": service.list_items(current_user["id"], status, q=q, kind=kind)}


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
