"""HTTP routes for the ingest domain."""

from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
)
from fastapi.responses import StreamingResponse

from news_dashboard.auth import (
    require_admin,
)
from news_dashboard.auto_enrichment import prefetch_then_auto_enrich
from news_dashboard.ingest.service import (
    ingest_all,
)
from news_dashboard.ingest_events import stream_ingest_events

# Kept as a module-level seam for background-task tests and integrations.
prefetch_article_bodies = prefetch_then_auto_enrich

router = APIRouter()


@router.post("/api/ingest", dependencies=[Depends(require_admin)])
def ingest(background_tasks: BackgroundTasks) -> dict[str, Any]:
    ingest_result = ingest_all()
    inserted = sum(v for v in ingest_result.results.values() if v > 0)
    if inserted > 0:
        background_tasks.add_task(prefetch_article_bodies)
    return {
        "results": ingest_result.results,
        "inserted": inserted,
        "run_id": ingest_result.run_id,
        "total_errors": ingest_result.total_errors,
        "failed_sources": ingest_result.failed_sources,
    }


@router.get("/api/ingest/stream", dependencies=[Depends(require_admin)])
def ingest_stream() -> StreamingResponse:
    return StreamingResponse(stream_ingest_events(), media_type="text/event-stream")
