from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Annotated, Any

import typer

from .db import connect, init_db

app = typer.Typer(help="Migration helpers for news-dashboard")

SOURCE_COLUMNS = [
    "slug",
    "name",
    "url",
    "category",
    "kind",
    "priority",
    "enabled",
    "last_checked_at",
    "last_success_at",
    "last_error",
    "last_fetched_count",
    "last_inserted_count",
]
ARTICLE_COLUMNS = [
    "url",
    "canonical_url",
    "title",
    "source_slug",
    "source_name",
    "category",
    "kind",
    "published_at",
    "summary",
    "reason",
    "importance_score",
    "tags",
    "status",
    "discovered_at",
    "read_at",
    "saved_at",
    "skipped_at",
    "archived_at",
    "updated_at",
]


def sqlite_rows(path: Path, table: str) -> list[sqlite3.Row]:
    sqlite = sqlite3.connect(path)
    sqlite.row_factory = sqlite3.Row
    try:
        return list(sqlite.execute(f"SELECT * FROM {table}"))
    finally:
        sqlite.close()


@app.command("sqlite-to-postgres")
def sqlite_to_postgres(
    sqlite_path: Annotated[Path, typer.Argument(help="Existing SQLite database path")],
) -> None:
    if not os.getenv("POSTGRES_HOST") and not os.getenv("DATABASE_URL"):
        message = "Set POSTGRES_* env vars or DATABASE_URL before migrating"
        raise typer.BadParameter(message)
    if not sqlite_path.exists():
        message = f"SQLite DB not found: {sqlite_path}"
        raise typer.BadParameter(message)

    init_db()
    sources = sqlite_rows(sqlite_path, "sources")
    articles = sqlite_rows(sqlite_path, "articles")
    with connect() as conn:
        for row in sources:
            # Gracefully handle older SQLite dumps that lack new health columns
            source_values = tuple(
                row[c] if c in row.keys() else None  # noqa: SIM118 - sqlite3.Row is not a Mapping
                for c in SOURCE_COLUMNS
            )
            conn.execute(
                """
                INSERT INTO sources(
                  slug, name, url, category, kind, priority, enabled, last_checked_at,
                  last_success_at, last_error, last_fetched_count, last_inserted_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                  name=excluded.name,
                  url=excluded.url,
                  category=excluded.category,
                  kind=excluded.kind,
                  priority=excluded.priority,
                  enabled=excluded.enabled,
                  last_checked_at=excluded.last_checked_at,
                  last_success_at=excluded.last_success_at,
                  last_error=excluded.last_error,
                  last_fetched_count=excluded.last_fetched_count,
                  last_inserted_count=excluded.last_inserted_count
                """,
                source_values,
            )
        for row in articles:
            article_values: tuple[Any, ...] = tuple(row[column] for column in ARTICLE_COLUMNS)
            conn.execute(
                """
                INSERT INTO articles(
                  url, canonical_url, title, source_slug, source_name, category, kind, published_at,
                  summary, reason, importance_score, tags, status, discovered_at, read_at, saved_at,
                  skipped_at, archived_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (url) DO UPDATE SET
                  title=excluded.title,
                  source_slug=excluded.source_slug,
                  source_name=excluded.source_name,
                  category=excluded.category,
                  kind=excluded.kind,
                  published_at=excluded.published_at,
                  summary=excluded.summary,
                  reason=excluded.reason,
                  importance_score=excluded.importance_score,
                  tags=excluded.tags,
                  status=excluded.status,
                  read_at=excluded.read_at,
                  saved_at=excluded.saved_at,
                  skipped_at=excluded.skipped_at,
                  archived_at=excluded.archived_at,
                  updated_at=excluded.updated_at
                """,
                article_values,
            )
    typer.echo(
        f"Migrated {len(sources)} source(s) and {len(articles)} article(s) from {sqlite_path}"
    )


if __name__ == "__main__":
    app()
