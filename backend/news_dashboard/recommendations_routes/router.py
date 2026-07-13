"""HTTP routes for recommendation health/recalculation.

The router carries no blanket auth dependency of its own; it is mounted on
``main``'s authenticated ``api`` router, which applies ``require_auth``. The
admin-only endpoints additionally depend on ``require_admin``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from news_dashboard.auth import require_admin, require_auth

router = APIRouter()

_admin_dep = [Depends(require_admin)]


@router.get("/recommendations/health", dependencies=_admin_dep)
def recommendations_health_endpoint() -> dict[str, Any]:
    from news_dashboard.recommendation_jobs import recommendation_health

    return recommendation_health()


@router.post("/recommendations/recalculate", dependencies=_admin_dep)
def recommendations_recalculate_endpoint() -> dict[str, Any]:
    from news_dashboard.recommendation_jobs import recalculate_stale_recommendations

    return recalculate_stale_recommendations().as_dict()


@router.post("/recommendations/recalculate-mine")
def recommendations_recalculate_mine_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, int]:
    """Recompute the calling user's own recommendation scores on demand.

    Lets any authenticated user personalize their feed from the UI without the
    admin-only stale sweep above. Returns the number of articles scored so the
    client can tell the user whether personalization has anything to learn from
    yet (zero means no interaction history exists).
    """
    from news_dashboard.recommendations import recompute_user_recommendations

    scored = recompute_user_recommendations(current_user["id"])
    return {"scored": scored}
