"""HTTP routes for reading streaks and achievements."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from news_dashboard.auth import require_auth
from news_dashboard.reading_progress import service
from news_dashboard.reading_progress.models import AchievementsResponse, ReadingStreakResponse

router = APIRouter()


@router.get("/api/users/me/streak", response_model=ReadingStreakResponse)
def get_streak_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return service.get_streak(current_user["id"])


@router.get("/api/users/me/achievements", response_model=AchievementsResponse)
def list_achievements_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_achievements(current_user["id"])}
