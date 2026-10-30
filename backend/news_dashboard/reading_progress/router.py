"""HTTP routes for reading streaks and achievements."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from news_dashboard.auth import require_auth
from news_dashboard.reading_progress import daily, rewards, service
from news_dashboard.reading_progress.models import AchievementsResponse, ReadingStreakResponse

router = APIRouter()

CurrentUser = Annotated[dict[str, Any], Depends(require_auth)]


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WelcomeClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_visit_date: date


class PresentationClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_visit_date: date | None
    historical_group_id: UUID | None = None


@router.get("/api/users/me/daily-streak")
def get_daily_streak(current_user: CurrentUser) -> dict[str, Any]:
    return daily.get_daily_streak(current_user["id"])


@router.post("/api/users/me/daily-visit")
def record_daily_visit(_body: EmptyRequest, current_user: CurrentUser) -> dict[str, Any]:
    return daily.record_visit(current_user["id"])


@router.get("/api/users/me/progress-preferences")
def get_progress_preferences(current_user: CurrentUser) -> dict[str, Any]:
    return daily.get_preferences(current_user["id"])


@router.patch("/api/users/me/progress-preferences")
def patch_progress_preferences(
    body: daily.ProgressPreferencesPatch, current_user: CurrentUser
) -> dict[str, Any]:
    return daily.save_preferences(current_user["id"], body)


@router.post("/api/users/me/presentation/claim")
def claim_presentation(body: PresentationClaim, current_user: CurrentUser) -> dict[str, Any]:
    return daily.claim_presentation(
        current_user["id"], body.expected_visit_date, body.historical_group_id
    )


@router.post("/api/users/me/daily-welcome/claim")
def claim_welcome(body: WelcomeClaim, current_user: CurrentUser) -> dict[str, Any]:
    return daily.claim_presentation(current_user["id"], body.expected_visit_date)


@router.get("/api/users/me/progress-rewards")
def progress_rewards(current_user: CurrentUser) -> dict[str, Any]:
    return rewards.daily_collection(current_user["id"])


@router.post("/api/users/me/reward-events/{group_id}/claim")
def claim_reward(group_id: UUID, _body: EmptyRequest, current_user: CurrentUser) -> dict[str, Any]:
    return rewards.claim_reward(current_user["id"], group_id)


@router.post("/api/users/me/reward-events/{group_id}/ack")
def acknowledge_reward(
    group_id: UUID, _body: EmptyRequest, current_user: CurrentUser
) -> dict[str, Any]:
    return rewards.claim_reward(current_user["id"], group_id, acknowledge=True)


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
