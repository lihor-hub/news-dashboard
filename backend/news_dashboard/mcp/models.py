from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

from news_dashboard.mcp.service import KNOWN_SCOPES

MAX_QUERY_LENGTH = 2_000
MAX_RESULT_LIMIT = 25
MAX_FILTER_VALUES = 50
MAX_FILTER_VALUE_LENGTH = 120
MAX_SEARCH_OFFSET = 10_000
MAX_BRIEFING_LIMIT = 25
MAX_BRIEFING_OFFSET = 10_000

FilterValue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_FILTER_VALUE_LENGTH),
]
FilterValues = Annotated[list[FilterValue], Field(max_length=MAX_FILTER_VALUES)]
PositiveArticleId = Annotated[
    int,
    Field(
        strict=True,
        gt=0,
        le=9_223_372_036_854_775_807,
        description="Positive PostgreSQL BIGINT article identifier.",
    ),
]
SearchQuery = Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_QUERY_LENGTH)]
AskQuestion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUERY_LENGTH),
]
AskCorpus = Literal["saved_and_read", "all_visible"]
SearchLimit = Annotated[int, Field(ge=1, le=MAX_RESULT_LIMIT)]
SearchOffset = Annotated[int, Field(ge=0, le=MAX_SEARCH_OFFSET)]
BriefingId = Annotated[int, Field(strict=True, ge=1)]
BriefingLimit = Annotated[int, Field(strict=True, ge=1, le=MAX_BRIEFING_LIMIT)]
BriefingOffset = Annotated[int, Field(strict=True, ge=0, le=MAX_BRIEFING_OFFSET)]
SourceCursor = Annotated[
    str,
    StringConstraints(max_length=20, pattern=r"^(0|[1-9][0-9]{0,19})$"),
]
WorkflowState = Literal["today", "later", "done", "skipped", "archived"]
WorkflowStates = Annotated[list[WorkflowState], Field(max_length=MAX_FILTER_VALUES)]
DateRange = Literal["all", "day", "week", "month"]


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
