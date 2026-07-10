"""HTTP routes for the stats domain."""

from __future__ import annotations

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
from news_dashboard.db import describe_database, init_db
from news_dashboard.scheduler.service import (
    get_next_ingest_at,
)
from news_dashboard.stats.service import (
    article_counts,
    articles_over_time,
    category_mix,
    ingested_vs_handled,
    source_quality,
    sources_volume,
    stats_overview,
    triage_metrics,
)

router = APIRouter()
_admin_dep = [Depends(require_admin)]


@router.get("/api/health/details", dependencies=_admin_dep)
def health_details() -> dict[str, Any]:
    from news_dashboard.system.service import graph_status

    init_db()
    return {
        "status": "ok",
        "database": describe_database(),
        "graph": graph_status(),
        "next_ingest_at": get_next_ingest_at(),
    }


@router.get("/api/stats/overview", dependencies=_admin_dep)
def stats_overview_endpoint(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return stats_overview(from_, to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/stats/articles-over-time", dependencies=_admin_dep)
def stats_articles_over_time_endpoint(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return {"items": articles_over_time(from_, to)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/stats/sources-volume", dependencies=_admin_dep)
def stats_sources_volume_endpoint(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return {"items": sources_volume(from_, to)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/stats/article-counts", dependencies=_admin_dep)
def stats_article_counts_endpoint() -> dict[str, Any]:
    return article_counts()


@router.get("/api/stats/triage-metrics", dependencies=_admin_dep)
def stats_triage_metrics_endpoint() -> dict[str, Any]:
    return triage_metrics()


@router.get("/api/stats/source-quality", dependencies=_admin_dep)
def stats_source_quality_endpoint() -> dict[str, Any]:
    return {"items": source_quality()}


@router.get("/api/stats/category-mix", dependencies=_admin_dep)
def stats_category_mix_endpoint() -> dict[str, Any]:
    return {"items": category_mix()}


@router.get("/api/stats/ingested-vs-handled", dependencies=_admin_dep)
def stats_ingested_vs_handled_endpoint() -> dict[str, Any]:
    return {"items": ingested_vs_handled()}
