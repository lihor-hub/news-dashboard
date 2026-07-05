"""HTTP routes for thumbs up/down feedback on briefings and recommendations.

The router carries no blanket auth dependency of its own; it is mounted on
``main``'s authenticated ``api`` router, which applies ``require_auth`` and
blocks guest/demo writes.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from news_dashboard.ai_feedback import service
from news_dashboard.ai_feedback.models import AiFeedbackRequest, SubjectType
from news_dashboard.auth import require_auth

router = APIRouter()


def _validate_subject_type(subject_type: str) -> SubjectType:
    if subject_type == "briefing":
        return "briefing"
    if subject_type == "recommendation":
        return "recommendation"
    raise HTTPException(status_code=400, detail="invalid subject_type")


@router.post("/api/ai-feedback")
def record_ai_feedback_endpoint(
    payload: AiFeedbackRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    comment = (payload.comment or "").strip() or None
    return service.record_feedback(
        current_user["id"],
        payload.subject_type,
        payload.subject_id,
        payload.verdict,
        article_id=payload.article_id,
        comment=comment,
    )


@router.delete("/api/ai-feedback")
def delete_ai_feedback_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    subject_type: str,
    subject_id: int,
    article_id: int | None = None,
) -> dict[str, Any]:
    deleted = service.delete_feedback(
        current_user["id"],
        _validate_subject_type(subject_type),
        subject_id,
        article_id=article_id,
    )
    return {"deleted": deleted}


@router.get("/api/ai-feedback")
def list_ai_feedback_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    subject_type: str,
    subject_ids: Annotated[str, Query(description="Comma-separated subject ids")],
) -> dict[str, Any]:
    ids = [int(part) for part in subject_ids.split(",") if part.strip()]
    feedback_map = service.get_feedback_map(
        current_user["id"],
        _validate_subject_type(subject_type),
        ids,
    )
    return {"items": feedback_map}
