"""HTTP routes for Reading Goals and weekly quizzes.

The router carries no blanket auth dependency of its own; it is mounted on
``main``'s authenticated ``api`` router, which applies ``require_auth``. Each
handler still depends on ``require_auth`` to receive the current user.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from news_dashboard.auth import require_auth
from news_dashboard.quizzes import service
from news_dashboard.quizzes.models import GoalCreateRequest, QuizSubmitRequest

router = APIRouter()


@router.post("/api/goals")
def create_goal_endpoint(
    payload: GoalCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    description = payload.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="description must not be empty")
    return service.create_goal(current_user["id"], description, payload.keywords)


@router.get("/api/goals")
def list_goals_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_goals(current_user["id"])}


@router.delete("/api/goals/{goal_id}")
def delete_goal_endpoint(
    goal_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if not service.delete_goal(goal_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="goal not found")
    return {"deleted": True}


@router.get("/api/quizzes/candidates")
def get_quiz_candidates_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    candidates = service.get_quiz_candidate_articles(current_user["id"])
    return {"candidates": candidates}


@router.get("/api/quizzes/latest")
def get_latest_quiz_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    quiz = service.get_latest_quiz(current_user["id"])
    if not quiz:
        raise HTTPException(status_code=404, detail="no quiz available")
    return quiz


@router.get("/api/quizzes")
def list_quizzes_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return {"items": service.list_quizzes(current_user["id"], limit=limit, offset=offset)}


@router.post("/api/quizzes/generate")
def generate_quiz_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        quiz = service.generate_weekly_quiz(current_user["id"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if not quiz:
        raise HTTPException(status_code=404, detail="no eligible articles to quiz on")
    return quiz


@router.post("/api/quizzes/{quiz_id}/submit")
def submit_quiz_endpoint(
    quiz_id: int,
    payload: QuizSubmitRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.submit_quiz(quiz_id, current_user["id"], payload.answers)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
