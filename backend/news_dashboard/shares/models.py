"""Request models for the shares domain."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_SHARE_NOTE_LENGTH = 2_000

MAX_ANNOTATION_HIGHLIGHT_LENGTH = 4_000

MAX_ANNOTATION_NOTE_LENGTH = 2_000

MAX_SHARE_MESSAGE_LENGTH = 4_000


class ShareArticleRequest(BaseModel):
    to_user_id: int
    note: str | None = Field(default=None, max_length=MAX_SHARE_NOTE_LENGTH)

    @field_validator("note")
    @classmethod
    def _note_blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class AddAnnotationRequest(BaseModel):
    highlighted_text: str = Field(min_length=1, max_length=MAX_ANNOTATION_HIGHLIGHT_LENGTH)
    offset_chars: int = 0
    note: str | None = Field(default=None, max_length=MAX_ANNOTATION_NOTE_LENGTH)

    @field_validator("highlighted_text")
    @classmethod
    def _highlighted_text_not_blank(cls, value: str) -> str:
        if not value.strip():
            msg = "highlighted_text must not be blank"
            raise ValueError(msg)
        return value

    @field_validator("note")
    @classmethod
    def _note_blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class AddMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_SHARE_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def _message_not_blank(cls, value: str) -> str:
        if not value.strip():
            msg = "message must not be blank"
            raise ValueError(msg)
        return value
