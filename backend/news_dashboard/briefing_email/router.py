"""Authenticated preview and public unsubscribe HTTP routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from news_dashboard.auth import require_auth
from news_dashboard.briefing_email.models import PreviewResponse
from news_dashboard.briefing_email.service import (
    PreviewCooldownError,
    PreviewUnavailableError,
    send_preview,
    unsubscribe_user,
)
from news_dashboard.briefing_email.tokens import verify_unsubscribe_token

router = APIRouter()
public_router = APIRouter()

_CONFIRMATION_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Email preferences updated</title></head><body><main><h1>You have been unsubscribed</h1>
<p>Daily briefing emails are now disabled.</p></main></body></html>"""


def _verified_user_id(token: str) -> int:
    try:
        return verify_unsubscribe_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe link") from exc


@public_router.get("/email/briefing/unsubscribe", response_class=HTMLResponse)
def unsubscribe_get(token: Annotated[str, Query(min_length=1)]) -> HTMLResponse:
    """Disable email and show a PII-free confirmation page."""
    unsubscribe_user(_verified_user_id(token))
    return HTMLResponse(_CONFIRMATION_HTML)


@public_router.post("/email/briefing/unsubscribe", response_class=Response)
def unsubscribe_one_click(
    token: Annotated[str, Query(min_length=1)],
    list_unsubscribe: Annotated[str, Form(alias="List-Unsubscribe")],
) -> Response:
    """Handle the RFC 8058 one-click unsubscribe form submission."""
    if list_unsubscribe != "One-Click":
        raise HTTPException(status_code=400, detail="Invalid one-click request")
    unsubscribe_user(_verified_user_id(token))
    return Response(status_code=200)


@router.post(
    "/api/settings/notifications/email/preview",
    response_model=PreviewResponse,
)
def preview_email(user: Annotated[dict[str, Any], Depends(require_auth)]) -> PreviewResponse:
    """Send the authenticated user's latest complete briefing as a preview."""
    try:
        sent = send_preview(int(user["id"]))
    except PreviewCooldownError as exc:
        raise HTTPException(status_code=429, detail="Preview cooldown active") from exc
    except PreviewUnavailableError as exc:
        status_code = 404 if exc.reason == "missing_briefing" else 400
        raise HTTPException(status_code=status_code, detail="Preview unavailable") from exc
    return PreviewResponse(sent=sent)
