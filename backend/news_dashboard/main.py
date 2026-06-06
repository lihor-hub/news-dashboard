from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .db import connect, describe_database, init_db, row_to_dict
from .ingest import ingest_all, list_articles, search_articles, set_article_status, sync_sources
from .scheduler import get_next_ingest_at, start_scheduler, stop_scheduler

app = FastAPI(title="News Dashboard", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StatusUpdate(BaseModel):
    status: str


class EnabledUpdate(BaseModel):
    enabled: bool


@app.on_event("startup")
def startup() -> None:
    sync_sources()
    start_scheduler()


@app.on_event("shutdown")
def shutdown() -> None:
    stop_scheduler()


@app.get("/api/health")
def health() -> dict:
    init_db()
    return {
        "status": "ok",
        "database": describe_database(),
        "next_ingest_at": get_next_ingest_at(),
    }


@app.post("/api/ingest")
def ingest() -> dict:
    results = ingest_all()
    return {"results": results, "inserted": sum(v for v in results.values() if v > 0)}


@app.get("/api/articles")
def articles(
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    return {"items": list_articles(status=status, category=category, limit=limit, offset=offset)}


@app.get("/api/search")
def search(
    q: str = Query(default="", min_length=1, description="Space-separated search terms"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    return {"items": search_articles(q=q.strip(), limit=limit)}


@app.patch("/api/articles/{article_id}/status")
def update_status(article_id: int, payload: StatusUpdate) -> dict:
    try:
        article = set_article_status(article_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@app.get("/api/articles/{article_id}/read")
def mark_read_via_token(article_id: int, token: str = Query(...)) -> dict:
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
def sources() -> dict:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sources ORDER BY category, priority DESC, name"
        ).fetchall()
        return {"items": [row_to_dict(row) for row in rows]}


@app.patch("/api/sources/{slug}/enabled")
def set_source_enabled(slug: str, payload: EnabledUpdate) -> dict:
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


class AskRequest(BaseModel):
    query: str


@app.post("/api/ask")
def ask_ai(payload: AskRequest) -> dict:
    """Answer a natural-language question using saved/read articles as context."""
    from .embeddings import ask

    q = payload.query.strip()
    if not q:
        raise HTTPException(status_code=400, detail="query must not be empty")
    try:
        return ask(q)
    except Exception as exc:
        # Surface errors clearly (missing API keys, etc.)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/summary")
def summary() -> dict:
    init_db()
    with connect() as conn:
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM articles GROUP BY status"
        ).fetchall()
        category_rows = conn.execute(
            "SELECT category, COUNT(*) AS count FROM articles GROUP BY category"
        ).fetchall()
    return {
        "byStatus":   {row["status"]:   row["count"] for row in status_rows},
        "byCategory": {row["category"]: row["count"] for row in category_rows},
    }


static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
