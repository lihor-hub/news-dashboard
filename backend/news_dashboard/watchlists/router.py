"""HTTP routes for the watchlists domain."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from news_dashboard.auth import (
    require_auth,
)
from news_dashboard.watchlists import service
from news_dashboard.watchlists.models import (
    WatchlistCreateRequest,
    WatchlistPreviewRequest,
    WatchlistUpdateRequest,
)

router = APIRouter()


@router.get("/api/watchlists")
def list_watchlists_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_watchlists(int(current_user["id"]))}


@router.post("/api/watchlists")
def create_watchlist_endpoint(
    payload: WatchlistCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.create_watchlist(
            int(current_user["id"]),
            payload.label,
            payload.query,
            threshold=payload.threshold,
            enabled=payload.enabled,
            notify_push=payload.notify_push,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/api/watchlists/{watchlist_id}")
def update_watchlist_endpoint(
    watchlist_id: int,
    payload: WatchlistUpdateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.update_watchlist(
            int(current_user["id"]),
            watchlist_id,
            **payload.model_dump(exclude_unset=True),
        )
    except service.WatchlistNotFoundError as exc:
        raise HTTPException(status_code=404, detail="watchlist not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/watchlists/{watchlist_id}")
def delete_watchlist_endpoint(
    watchlist_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if not service.delete_watchlist(int(current_user["id"]), watchlist_id):
        raise HTTPException(status_code=404, detail="watchlist not found")
    return {"deleted": True}


@router.post("/api/watchlists/preview")
def preview_watchlist_endpoint(
    payload: WatchlistPreviewRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    matches = service.preview_matches(
        int(current_user["id"]), payload.query, threshold=payload.threshold
    )
    return {"items": matches}


@router.get("/api/watchlists/nudges")
def list_watchlist_nudges_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_nudges(int(current_user["id"]))}
