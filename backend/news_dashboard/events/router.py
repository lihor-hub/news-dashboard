"""HTTP routes for the events domain."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
)

from news_dashboard.auth import (
    require_auth,
)
from news_dashboard.events import service
from news_dashboard.events.models import (
    AnalyticsEventsRequest,
)

router = APIRouter()


@router.post("/api/events")
def ingest_events(
    payload: AnalyticsEventsRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    """Store a batch of client telemetry events for the current user."""
    stored = service.store_events(
        current_user["id"], [event.model_dump() for event in payload.events]
    )
    return {"stored": stored}
