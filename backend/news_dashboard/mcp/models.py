from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

MAX_QUERY_LENGTH = 2_000
MAX_RESULT_LIMIT = 25


class TokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class McpRpcRequest(BaseModel):
    tool: str = Field(min_length=1, max_length=60)
    arguments: dict[str, Any] = Field(default_factory=dict)
