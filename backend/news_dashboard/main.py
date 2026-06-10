from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .body_fetch import fetch_and_cache_body, get_article
from .db import connect, describe_database, init_db, row_to_dict
from .ingest import (
    ingest_all,
    list_articles,
    search_articles,
    send_article_later,
    set_article_starred,
    set_article_status,
    sync_sources,
    transition_article_state,
)
from .ingest_events import stream_ingest_events
from .run_history import get_ingest_run_sources, list_ingest_runs
from .scheduler import (
    get_interval_minutes,
    get_next_ingest_at,
    is_paused,
    pause_scheduler,
    resume_scheduler,
    set_interval,
    start_scheduler,
    stop_scheduler,
)
from .source_health import list_source_health
from .stats import (
    article_counts,
    articles_over_time,
    category_mix,
    ingested_vs_handled,
    source_quality,
    sources_volume,
    stats_overview,
    triage_metrics,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    sync_sources()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="News Dashboard", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StatusUpdate(BaseModel):
    status: str


class StateUpdate(BaseModel):
    state: str


class StarUpdate(BaseModel):
    starred: bool


class LaterUpdate(BaseModel):
    days: int = 1


class EnabledUpdate(BaseModel):
    enabled: bool


@app.get("/api/health")
def health() -> dict[str, Any]:
    init_db()
    return {
        "status": "ok",
        "database": describe_database(),
        "next_ingest_at": get_next_ingest_at(),
    }


@app.post("/api/ingest")
def ingest() -> dict[str, Any]:
    results = ingest_all()
    return {"results": results, "inserted": sum(v for v in results.values() if v > 0)}


@app.get("/api/ingest/stream")
def ingest_stream() -> StreamingResponse:
    return StreamingResponse(stream_ingest_events(), media_type="text/event-stream")


@app.get("/api/ingest/runs")
def ingest_runs(
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    return list_ingest_runs(from_=from_, to=to, page=page, per_page=per_page)


@app.get("/api/ingest/runs/{run_id}")
def ingest_run_sources(run_id: int) -> dict[str, Any]:
    sources = get_ingest_run_sources(run_id)
    if sources is None:
        raise HTTPException(status_code=404, detail="ingest run not found")
    return {"items": sources}


@app.get("/api/articles")
def articles(
    status: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    starred: Annotated[bool | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return {
        "items": list_articles(
            status=status,
            state=state,
            starred=starred,
            category=category,
            limit=limit,
            offset=offset,
        )
    }


@app.get("/api/search")
def search(
    q: Annotated[str, Query(min_length=1, description="Space-separated search terms")] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    return {"items": search_articles(q=q.strip(), limit=limit)}


@app.get("/api/articles/{article_id}")
def get_article_by_id(article_id: int) -> dict[str, Any]:
    article = get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@app.post("/api/articles/{article_id}/body")
def fetch_article_body(article_id: int) -> dict[str, Any]:
    """Fetch and cache full body text for an article. Idempotent (cache hit returns fast)."""
    article = fetch_and_cache_body(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@app.patch("/api/articles/{article_id}/status")
def update_status(article_id: int, payload: StatusUpdate) -> dict[str, Any]:
    try:
        article = set_article_status(article_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@app.patch("/api/articles/{article_id}/state")
def update_state(article_id: int, payload: StateUpdate) -> dict[str, Any]:
    try:
        article = transition_article_state(article_id, payload.state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@app.patch("/api/articles/{article_id}/star")
def update_star(article_id: int, payload: StarUpdate) -> dict[str, Any]:
    article = set_article_starred(article_id, payload.starred)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@app.patch("/api/articles/{article_id}/later")
def snooze_later(article_id: int, payload: LaterUpdate) -> dict[str, Any]:
    try:
        article = send_article_later(article_id, payload.days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@app.get("/api/articles/{article_id}/read")
def mark_read_via_token(article_id: int, token: Annotated[str, Query()]) -> dict[str, Any]:
    """One-click mark-read endpoint for digest emails. Validates a signed token."""
    from .digest import verify_read_token

    if not verify_read_token(article_id, token):
        raise HTTPException(status_code=403, detail="invalid or expired token")
    try:
        article = set_article_status(article_id, "read")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return {"status": "marked_read", "article": article}


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sources ORDER BY category, priority DESC, name"
        ).fetchall()
        return {"items": [row_to_dict(row) for row in rows]}


@app.get("/api/sources/health")
def sources_health() -> dict[str, Any]:
    return {"items": list_source_health()}


@app.patch("/api/sources/{slug}/enabled")
def set_source_enabled(slug: str, payload: EnabledUpdate) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE sources SET enabled=? WHERE slug=?",
            (1 if payload.enabled else 0, slug),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="source not found")
        row = conn.execute("SELECT * FROM sources WHERE slug=?", (slug,)).fetchone()
        return row_to_dict(row)


class IntervalUpdate(BaseModel):
    minutes: int


@app.get("/api/scheduler/status")
def scheduler_status() -> dict[str, Any]:
    next_run = get_next_ingest_at()
    paused = is_paused()
    return {
        "interval_minutes": get_interval_minutes(),
        "paused": paused,
        "next_run_at": next_run,
    }


@app.post("/api/scheduler/interval")
def scheduler_set_interval(payload: IntervalUpdate) -> dict[str, Any]:
    if payload.minutes < 1:
        raise HTTPException(status_code=400, detail="minutes must be >= 1")
    set_interval(payload.minutes)
    return {"interval_minutes": payload.minutes, "next_run_at": get_next_ingest_at()}


@app.post("/api/scheduler/pause")
def scheduler_pause() -> dict[str, Any]:
    pause_scheduler()
    return {"paused": True}


@app.post("/api/scheduler/resume")
def scheduler_resume() -> dict[str, Any]:
    resume_scheduler()
    return {"paused": False, "next_run_at": get_next_ingest_at()}


@app.get("/api/stats/overview")
def stats_overview_endpoint(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return stats_overview(from_, to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/stats/articles-over-time")
def stats_articles_over_time_endpoint(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return {"items": articles_over_time(from_, to)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/stats/sources-volume")
def stats_sources_volume_endpoint(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query()],
) -> dict[str, Any]:
    try:
        return {"items": sources_volume(from_, to)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/stats/article-counts")
def stats_article_counts_endpoint() -> dict[str, Any]:
    return article_counts()


@app.get("/api/stats/triage-metrics")
def stats_triage_metrics_endpoint() -> dict[str, Any]:
    return triage_metrics()


@app.get("/api/stats/source-quality")
def stats_source_quality_endpoint() -> dict[str, Any]:
    return {"items": source_quality()}


@app.get("/api/stats/category-mix")
def stats_category_mix_endpoint() -> dict[str, Any]:
    return {"items": category_mix()}


@app.get("/api/stats/ingested-vs-handled")
def stats_ingested_vs_handled_endpoint() -> dict[str, Any]:
    return {"items": ingested_vs_handled()}


class AskRequest(BaseModel):
    query: str
    include_all: bool = False


@app.post("/api/ask")
def ask_ai(payload: AskRequest) -> dict[str, Any]:
    """Answer a natural-language question using saved/read articles as context."""
    from .embeddings import ask

    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query must not be empty")
    try:
        return ask(q, include_all=payload.include_all)
    except Exception as exc:
        # Surface errors clearly (missing API keys, etc.)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/summary")
def summary() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM articles GROUP BY status"
        ).fetchall()
        category_rows = conn.execute(
            "SELECT category, COUNT(*) AS count FROM articles GROUP BY category"
        ).fetchall()
    return {
        "byStatus": {row["status"]: row["count"] for row in status_rows},
        "byCategory": {row["category"]: row["count"] for row in category_rows},
    }


static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
