"""API response models for briefing-email actions."""

from pydantic import BaseModel


class PreviewResponse(BaseModel):
    """Confirmation that a preview was handed to the email transport."""

    sent: bool
