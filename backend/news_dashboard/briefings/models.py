"""Request models for the briefings domain."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_BRIEFING_FOCUS_PROMPT_LENGTH = 2_000

MAX_BRIEFING_CHAT_MESSAGE_LENGTH = 4_000

MAX_BRIEFING_CHAT_HISTORY_ITEMS = 50


class BriefingCreateRequest(BaseModel):
    focus_prompt: str | None = Field(default=None, max_length=MAX_BRIEFING_FOCUS_PROMPT_LENGTH)

    @field_validator("focus_prompt")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class BriefingChatMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=MAX_BRIEFING_CHAT_MESSAGE_LENGTH)


class BriefingChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_BRIEFING_CHAT_MESSAGE_LENGTH)
    history: list[BriefingChatMessage] = Field(
        default_factory=list, max_length=MAX_BRIEFING_CHAT_HISTORY_ITEMS
    )

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "message must not be blank"
            raise ValueError(msg)
        return value
