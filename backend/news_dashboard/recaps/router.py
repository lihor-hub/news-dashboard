"""HTTP routes for weekly reading recaps.

Mounted on ``main``'s authenticated ``api`` router, which applies
``require_auth``; handlers still depend on it to receive the current user.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from news_dashboard.auth import require_auth
from news_dashboard.recaps import service

router = APIRouter()


@router.get("/api/recaps")
def list_recaps_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    limit: Annotated[int, Query(ge=1, le=52)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return {"items": service.list_recaps(current_user["id"], limit=limit, offset=offset)}


@router.get("/api/recaps/latest")
def get_latest_recap_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    recap = service.get_latest_recap(current_user["id"])
    if not recap:
        raise HTTPException(status_code=404, detail="no recap available")
    return recap
