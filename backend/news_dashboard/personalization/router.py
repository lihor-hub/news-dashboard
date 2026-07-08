"""HTTP routes for personalization nudges."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from news_dashboard.auth import require_auth
from news_dashboard.personalization import service
from news_dashboard.personalization.models import NudgeActionRequest, NudgeDismissRequest

router = APIRouter()


@router.get("/api/personalization/nudges")
def get_personalization_nudges(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.generate_nudges(int(current_user["id"]))}


@router.post("/api/personalization/nudges/apply")
def apply_personalization_nudge(
    payload: NudgeActionRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return service.apply_nudge(int(current_user["id"]), payload.nudge_id)


@router.post("/api/personalization/nudges/dismiss")
def dismiss_personalization_nudge(
    payload: NudgeDismissRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return service.dismiss_nudge(
        int(current_user["id"]),
        payload.nudge_id,
        cooldown_days=payload.cooldown_days,
    )
