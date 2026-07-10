"""Business logic for client analytics events."""

from __future__ import annotations

from typing import Any

from news_dashboard.analytics import record_events


def store_events(user_id: int, events: list[dict[str, Any]]) -> int:
    """Persist a validated analytics-event batch for one user."""
    return record_events(user_id, events)
