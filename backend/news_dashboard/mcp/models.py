from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from news_dashboard.mcp.service import KNOWN_SCOPES

MAX_QUERY_LENGTH = 2_000
MAX_RESULT_LIMIT = 25


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


class McpRpcRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=60)
    arguments: dict[str, Any] = Field(default_factory=dict)
