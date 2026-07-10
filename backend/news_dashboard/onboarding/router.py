"""HTTP routes for new-user onboarding.

The router carries no blanket auth dependency of its own; it is mounted on
``main``'s authenticated ``api`` router, which applies ``require_auth``. Each
handler still depends on ``require_auth`` to receive the current user.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from news_dashboard.auth import require_auth
from news_dashboard.db import init_db
from news_dashboard.onboarding import service
from news_dashboard.onboarding.models import (
    OnboardingInterestsRequest,
    OnboardingProfileRequest,
    OnboardingRecommendationsRequest,
)

router = APIRouter()


@router.get("/api/onboarding/status")
def onboarding_status(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    init_db()
    return {"completed": service.get_status(int(current_user["id"]))}


@router.get("/api/onboarding/interests")
def onboarding_interests(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> list[dict[str, Any]]:
    _ = current_user
    return [
        {"id": option["id"], "label": option["label"], "description": option.get("description", "")}
        for group in service.INTEREST_GROUPS
        for option in group["options"]
    ]


@router.post("/api/onboarding/recommendations")
def onboarding_recommendations(
    payload: OnboardingRecommendationsRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> list[dict[str, Any]]:
    init_db()
    return service.frontend_recommendations(int(current_user["id"]), payload.interest_ids)


@router.post("/api/onboarding/profile")
def save_onboarding_profile(
    payload: OnboardingProfileRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    valid_interests = service.interest_options()
    interests = list(dict.fromkeys(payload.interest_ids))
    invalid = [i for i in interests if i not in valid_interests]
    if invalid:
        raise HTTPException(status_code=400, detail=f"unknown interests: {', '.join(invalid)}")

    enabled_slugs = list(dict.fromkeys(payload.enabled_slugs))
    try:
        service.save_profile(int(current_user["id"]), interests, enabled_slugs)
    except service.UnknownGlobalSourcesError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"completed": True}


@router.get("/api/onboarding/source-recommendations")
def onboarding_source_recommendations(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    init_db()
    uid = int(current_user["id"])
    interests = service.get_interests(uid)
    return {"items": service.source_recommendations(uid, interests)}


@router.post("/api/onboarding/interests")
def save_onboarding_interests(
    payload: OnboardingInterestsRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    valid_interests = service.interest_options()
    interests = list(dict.fromkeys(payload.interests))
    invalid = [interest for interest in interests if interest not in valid_interests]
    if invalid:
        raise HTTPException(status_code=400, detail=f"unknown interests: {', '.join(invalid)}")

    uid = int(current_user["id"])
    try:
        service.save_interests(
            uid,
            interests,
            payload.enabled_source_slugs,
            payload.disabled_source_slugs,
            payload.completed,
        )
    except service.UnknownGlobalSourcesError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "interests": interests,
        "items": service.source_recommendations(uid, interests),
    }
