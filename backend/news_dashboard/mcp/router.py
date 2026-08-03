from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from news_dashboard.auth import require_auth
from news_dashboard.mcp import service
from news_dashboard.mcp.models import TokenCreateRequest

router = APIRouter()


@router.get("/api/users/me/mcp-tokens")
def list_mcp_tokens(
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    return {"items": service.list_tokens(int(current_user["id"])), "enabled": service.mcp_enabled()}


@router.post("/api/users/me/mcp-tokens")
def create_mcp_token(
    payload: TokenCreateRequest,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    if not service.mcp_enabled():
        raise HTTPException(status_code=403, detail="MCP server is not enabled on this instance")
    scopes = service.DEFAULT_SCOPES if payload.scopes is None else tuple(payload.scopes)
    try:
        return service.create_token(int(current_user["id"]), payload.name, scopes=scopes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/users/me/mcp-tokens/{token_id}")
def revoke_mcp_token(
    token_id: int,
    current_user: Annotated[dict[str, Any], Depends(require_auth)],
) -> dict[str, Any]:
    token = service.revoke_token(int(current_user["id"]), token_id)
    if token is None:
        raise HTTPException(status_code=404, detail="token not found")
    return token


def authenticate_bearer(
    authorization: str | None,
    *,
    enabled: bool,
    disabled_detail: str,
    required_scope: str | None = None,
) -> dict[str, Any]:
    """Shared bearer-token gate for token-authenticated surfaces (MCP, A2A)."""
    if not enabled:
        raise HTTPException(status_code=403, detail=disabled_detail)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    auth = service.authenticate_token(token)
    if auth is None:
        raise HTTPException(
            status_code=401,
            detail="invalid or revoked token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if required_scope is not None and required_scope not in auth["scopes"]:
        raise HTTPException(
            status_code=403,
            detail=f"token is missing required scope '{required_scope}'",
        )
    return auth
