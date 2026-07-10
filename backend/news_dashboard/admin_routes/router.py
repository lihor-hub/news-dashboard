"""HTTP routes for the admin routes domain."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from news_dashboard.admin_routes import service
from news_dashboard.admin_routes.models import (
    CreateUserRequest,
    GenerateUserRequest,
    UpdatePasswordRequest,
)
from news_dashboard.auth import (
    require_auth,
)

router = APIRouter()


@router.get("/analytics")
def admin_get_analytics(days: Annotated[int, Query(ge=1, le=365)] = 30) -> dict[str, Any]:
    return service.admin_analytics(days=days)


@router.get("/ai/metrics")
def admin_ai_metrics(days: Annotated[int, Query(ge=1, le=365)] = 30) -> dict[str, Any]:
    """Aggregate AI usage/cost/feedback metrics from Langfuse for admins.

    Returns ``{"enabled": False}`` when Langfuse tracing is not configured.
    """
    return service.fetch_metrics(days=days)


@router.get("/ai/quality")
def admin_ai_quality(days: Annotated[int, Query(ge=1, le=365)] = 30) -> dict[str, Any]:
    return service.admin_quality_summary(days=days)


@router.get("/learning-agent/runs")
def admin_learning_agent_runs(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> dict[str, Any]:
    """Recent Learn from Link generation runs with per-step status/latency/cost/retry.

    For debug workflows: shows what happened in a run without reading logs.
    """
    return service.admin_run_summary(limit=limit)


@router.get("/users")
def admin_list_users() -> dict[str, Any]:
    return {"items": service.list_users()}


@router.post("/users")
def admin_create_user(payload: CreateUserRequest) -> dict[str, Any]:
    try:
        return service.create_user(
            payload.username,
            payload.password,
            email=payload.email,
            is_admin=payload.is_admin,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/users/generate")
async def admin_generate_user(payload: GenerateUserRequest) -> dict[str, Any]:
    """Create a user with a server-generated password and return the credentials.

    The plaintext password is returned exactly once here so the admin can hand it
    to the new user; it is never stored or retrievable afterwards.

    When Keycloak SSO is enabled, local password login is disabled, so the user
    must be created in Keycloak (with a one-time temporary password) for the
    credentials to actually work. Otherwise the user is created in the local
    ``users`` table.
    """
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="username is required")
    try:
        return await service.generate_user(
            username,
            email=payload.email,
            is_admin=payload.is_admin,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/users/{user_id}")
def admin_get_user(user_id: int) -> dict[str, Any]:
    user = service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return user


@router.patch("/users/{user_id}/password")
def admin_update_password(user_id: int, payload: UpdatePasswordRequest) -> dict[str, Any]:
    if service.keycloak_enabled():
        raise HTTPException(status_code=409, detail="Keycloak owns user passwords")
    if not service.update_password(user_id, payload.password):
        raise HTTPException(status_code=404, detail="user not found")
    return {"status": "updated"}


@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if service.keycloak_enabled():
        raise HTTPException(
            status_code=409,
            detail="Keycloak users must be deprovisioned outside the local app table",
        )
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="cannot delete your own account")
    if not service.delete_user(user_id):
        raise HTTPException(status_code=404, detail="user not found")
    return {"status": "deleted"}
