"""HTTP routes for the scheduler domain."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)

from news_dashboard.auth import (
    require_admin,
)
from news_dashboard.run_history import get_ingest_run_sources, list_ingest_runs
from news_dashboard.scheduler.models import (
    IntervalUpdate,
)
from news_dashboard.scheduler.service import (
    get_interval_minutes,
    get_next_ingest_at,
    is_ingest_interval_enabled,
    is_paused,
    pause_scheduler,
    resume_scheduler,
    run_embedding_dedup_now,
    set_interval,
)

router = APIRouter()
_admin_dep = [Depends(require_admin)]


@router.get("/api/scheduler/status", dependencies=_admin_dep)
def scheduler_status() -> dict[str, Any]:
    interval_enabled = is_ingest_interval_enabled()
    next_run = get_next_ingest_at()
    paused = is_paused() if interval_enabled else False
    return {
        "interval_minutes": get_interval_minutes(),
        "paused": paused,
        "next_run_at": next_run,
        "interval_ingest_enabled": interval_enabled,
        "ingest_authority": "in_process" if interval_enabled else "external",
    }


@router.post("/api/scheduler/interval", dependencies=_admin_dep)
def scheduler_set_interval(payload: IntervalUpdate) -> dict[str, Any]:
    if payload.minutes < 1:
        raise HTTPException(status_code=400, detail="minutes must be >= 1")
    set_interval(payload.minutes)
    return {"interval_minutes": payload.minutes, "next_run_at": get_next_ingest_at()}


@router.post("/api/scheduler/pause", dependencies=_admin_dep)
def scheduler_pause() -> dict[str, Any]:
    pause_scheduler()
    return {"paused": True}


@router.post("/api/scheduler/resume", dependencies=_admin_dep)
def scheduler_resume() -> dict[str, Any]:
    resume_scheduler()
    return {"paused": False, "next_run_at": get_next_ingest_at()}


@router.get("/api/ingest/runs", dependencies=_admin_dep)
def ingest_runs(
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    return list_ingest_runs(from_=from_, to=to, page=page, per_page=per_page)


@router.get("/api/ingest/runs/{run_id}", dependencies=_admin_dep)
def ingest_run_sources(run_id: int) -> dict[str, Any]:
    run_sources = get_ingest_run_sources(run_id)
    if run_sources is None:
        raise HTTPException(status_code=404, detail="ingest run not found")
    return {"items": run_sources}


@router.get("/api/scheduler/job-runs", dependencies=_admin_dep)
def list_scheduled_job_runs() -> dict[str, Any]:
    from news_dashboard.scheduled_job_history import list_latest_job_runs

    return {"items": list_latest_job_runs()}


@router.post("/api/scheduler/jobs/embedding-dedup/run", dependencies=_admin_dep)
def scheduler_run_embedding_dedup() -> dict[str, int | str]:
    try:
        return run_embedding_dedup_now()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="duplicate cleanup failed") from exc
