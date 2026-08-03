from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

from news_dashboard.mcp.service import KNOWN_SCOPES

MAX_RESULT_LIMIT = 25
MAX_FILTER_VALUES = 50
MAX_FILTER_VALUE_LENGTH = 120

FilterValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_FILTER_VALUE_LENGTH),
]
FilterValues = Annotated[list[FilterValue], Field(max_length=MAX_FILTER_VALUES)]


class TokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] | None = None

    @field_validator("scopes")
    @classmethod
    def _validate_scopes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if not value:
            message = "scopes must not be empty"
            raise ValueError(message)
        unknown = sorted(set(value) - KNOWN_SCOPES)
        if unknown:
            message = f"unknown scopes: {', '.join(unknown)}"
            raise ValueError(message)
        return value
