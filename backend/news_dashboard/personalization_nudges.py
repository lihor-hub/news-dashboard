"""Compatibility exports for personalization nudge helpers."""

from __future__ import annotations

from news_dashboard.personalization.service import apply_nudge, dismiss_nudge, generate_nudges

__all__ = ["apply_nudge", "dismiss_nudge", "generate_nudges"]
