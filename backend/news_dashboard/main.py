from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .db import connect, describe_database, init_db, row_to_dict
from .ingest import ingest_all, list_articles, search_articles, set_article_status, sync_sources

app = FastAPI(title="News Dashboard", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StatusUpdate(BaseModel):
    status: str


@app.on_event("startup")
def startup() -> None:
    sync_sources()


@app.get("/api/health")
def health() -> dict:
    init_db()
    return {"status": "ok", "database": describe_database()}


@app.post("/api/ingest")
def ingest() -> dict:
    results = ingest_all()
    return {"results": results, "inserted": sum(v for v in results.values() if v > 0)}


@app.get("/api/articles")
def articles(
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    return {"items": list_articles(status=status, category=category, limit=limit)}


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


@app.get("/api/sources")
def sources() -> dict:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sources ORDER BY category, priority DESC, name"
        ).fetchall()
        return {"items": [row_to_dict(row) for row in rows]}


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
