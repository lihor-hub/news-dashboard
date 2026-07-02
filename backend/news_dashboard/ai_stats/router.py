"""HTTP routes for AI statistics over the news corpus.

The router carries no blanket auth dependency of its own; it is mounted on
``main``'s authenticated ``api`` router, which applies ``require_auth``. Each
handler still depends on ``require_auth`` to receive the current user.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from news_dashboard.ai_stats import service
from news_dashboard.auth import require_auth

router = APIRouter()


@router.get("/api/ai-stats/word-cloud")
def word_cloud_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    days: Annotated[int, Query(ge=1, le=30)] = 7,
) -> dict[str, Any]:
    return service.word_cloud(user_id=current_user["id"], days=days)


@router.get("/api/ai-stats/embedding-map")
def embedding_map_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    days: Annotated[int, Query(ge=1, le=30)] = 7,
) -> dict[str, Any]:
    return service.embedding_map(user_id=current_user["id"], days=days)
