"""HTTP routes for Learn from Link lessons."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from news_dashboard.auth import require_auth
from news_dashboard.learn_from_link import service
from news_dashboard.learn_from_link.models import LessonCreateRequest

router = APIRouter()


@router.post("/api/learn/lessons", status_code=201)
def create_lesson_endpoint(
    payload: LessonCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.create_lesson(
            current_user["id"],
            payload.url,
        )
    except service.LessonUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/learn/lessons/{lesson_id}")
def get_lesson_endpoint(
    lesson_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    lesson = service.get_lesson(lesson_id, current_user["id"])
    if lesson is None:
        raise HTTPException(status_code=404, detail="lesson not found")
    return lesson
