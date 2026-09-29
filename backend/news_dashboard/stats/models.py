"""Request models for the stats domain."""

from __future__ import annotations

from enum import StrEnum


class DatasetRange(StrEnum):
    """Supported time windows for dataset growth statistics."""

    THIRTY_DAYS = "30d"
    NINETY_DAYS = "90d"
    ONE_YEAR = "1y"
    ALL = "all"
