"""HTTP routes for health, liveness, readiness, metrics, config, version, and changelog.

The router carries no auth dependency; it is mounted directly on the app
alongside ``main``'s ``public_router``, unauthenticated.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from news_dashboard.system import service

router = APIRouter()


@router.get("/api/health")
def health() -> dict[str, Any]:
    service.check_health()
    return {"status": "ok"}


@router.get("/api/live")
def liveness() -> dict[str, Any]:
    return {"status": "ok"}


@router.get("/api/ready")
def readiness() -> dict[str, Any]:
    try:
        service.check_readiness()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok"}


@router.get("/metrics")
def prometheus_metrics() -> Response:
    from news_dashboard.metrics import CONTENT_TYPE_LATEST, metrics_enabled, render_metrics

    if not metrics_enabled():
        raise HTTPException(status_code=404, detail="not found")
    return Response(content=render_metrics(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/config")
def public_config() -> dict[str, Any]:
    return service.public_config()


@router.get("/api/version")
def version_endpoint(request: Request) -> dict[str, str]:
    """Return the running app version, matching the OpenAPI ``info.version``."""
    return {"version": request.app.version}


@router.get("/api/changelog")
def changelog_endpoint(request: Request) -> dict[str, object]:
    """Return changelog entries parsed from CHANGELOG.md."""
    return {"version": request.app.version, "entries": service.parse_changelog()}
