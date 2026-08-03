"""HTTP routes for the user settings domain."""

from __future__ import annotations

import json
import os
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
)

from news_dashboard.analytics import reading_dna
from news_dashboard.auth import (
    count_admins,
    delete_user,
    require_auth,
)
from news_dashboard.auth_routes.router import SESSION_COOKIE as _SESSION_COOKIE
from news_dashboard.user_settings import service
from news_dashboard.user_settings.models import (
    AnalyticsSettingsUpdate,
    AutomaticAiEnrichmentUpdate,
    DeleteAccountRequest,
    NotificationSettingsUpdate,
    PushSubscribeRequest,
    PushUnsubscribeRequest,
    RecommendationPreferencesUpdate,
)

router = APIRouter()


MAX_ARCHIVE_IMPORT_BYTES = int(os.getenv("MAX_ARCHIVE_IMPORT_BYTES", str(20 * 1024 * 1024)))


@router.get("/api/users/me/reading-dna")
def reading_dna_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> dict[str, Any]:
    return reading_dna(current_user["id"], days=days)


@router.get("/api/users/me/export")
def export_user_data(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.export import assemble_user_export

    return assemble_user_export(current_user["id"])


@router.post("/api/users/me/import")
def import_user_archive(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    """Restore a personal archive previously downloaded from /api/users/me/export."""
    from news_dashboard.import_export import ArchiveImportError, restore_user_archive

    contents = file.file.read(MAX_ARCHIVE_IMPORT_BYTES + 1)
    if len(contents) > MAX_ARCHIVE_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Archive file too large (max {MAX_ARCHIVE_IMPORT_BYTES} bytes)",
        )

    try:
        payload = json.loads(contents)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid archive JSON: {exc}") from exc

    try:
        result = restore_user_archive(current_user["id"], payload)
    except ArchiveImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result


@router.delete("/api/users/me")
def delete_own_account(
    payload: DeleteAccountRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    response: Response,
) -> dict[str, str]:
    if payload.confirmation != current_user["username"]:
        raise HTTPException(
            status_code=400, detail="Confirmation text does not match your username"
        )
    if current_user.get("is_admin") and count_admins() <= 1:
        raise HTTPException(
            status_code=400, detail="Cannot delete the last remaining admin account"
        )
    delete_user(current_user["id"])
    response.delete_cookie(key=_SESSION_COOKIE, path="/")
    return {"status": "deleted"}


@router.get("/api/users/me/recommendation-preferences")
def get_recommendation_preferences_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    from news_dashboard.recommendations import get_recommendation_preferences

    return service.preference_payload(get_recommendation_preferences(current_user["id"]))


@router.patch("/api/users/me/recommendation-preferences")
def update_recommendation_preferences_endpoint(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: RecommendationPreferencesUpdate,
) -> dict[str, Any]:
    from news_dashboard.recommendations import (
        recompute_user_recommendations,
        save_recommendation_preferences,
    )

    preferences = save_recommendation_preferences(
        current_user["id"],
        category_weights=payload.category_weights,
        novelty_weight=payload.novelty_weight,
    )
    scored = recompute_user_recommendations(current_user["id"])
    return {**service.preference_payload(preferences), "recomputed": scored}


@router.get("/api/settings/notifications")
def get_notification_settings(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    try:
        return service.get_notification_settings(current_user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/api/settings/notifications")
def update_notification_settings(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: NotificationSettingsUpdate,
) -> dict[str, Any]:
    try:
        return service.update_notification_settings(current_user["id"], payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/settings/analytics")
def get_analytics_settings(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return service.get_analytics_settings(current_user["id"])


@router.put("/api/settings/analytics")
def update_analytics_settings(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: AnalyticsSettingsUpdate,
) -> dict[str, Any]:
    return service.update_analytics_settings(current_user["id"], enabled=payload.enabled)


@router.get("/api/settings/automatic-ai-enrichment")
def get_automatic_ai_enrichment_settings(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return service.get_automatic_ai_enrichment_settings(current_user["id"])


@router.put("/api/settings/automatic-ai-enrichment")
def update_automatic_ai_enrichment_settings(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: AutomaticAiEnrichmentUpdate,
) -> dict[str, Any]:
    return service.update_automatic_ai_enrichment_settings(
        current_user["id"], enabled=payload.enabled
    )


@router.post("/api/notifications/subscribe")
def push_subscribe(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: PushSubscribeRequest,
) -> dict[str, Any]:
    from news_dashboard.push import save_push_subscription, validate_push_subscription

    try:
        validate_push_subscription(payload.endpoint, payload.p256dh, payload.auth)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    save_push_subscription(
        current_user["id"],
        payload.endpoint,
        payload.p256dh,
        payload.auth,
    )
    return {"subscribed": True}


@router.delete("/api/notifications/subscribe")
def push_unsubscribe(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
    payload: PushUnsubscribeRequest | None = None,
) -> dict[str, Any]:
    from news_dashboard.push import delete_push_subscriptions

    if payload and payload.endpoint is not None:
        delete_push_subscriptions(current_user["id"], endpoint=payload.endpoint)
    else:
        delete_push_subscriptions(current_user["id"])
    return {"unsubscribed": True}
