"""Persistence and validation for per-user saved search views."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from news_dashboard.db import connect, init_db
from news_dashboard.saved_searches.models import SavedSearchFilters

_ALLOWED_STATES = {"today", "later", "done", "skipped", "archived"}
_ALLOWED_DATE_RANGES = {"all", "today", "week", "month"}
_MAX_TEXT = 200
_MAX_ITEMS = 50


def _clean_strings(values: list[str], allowed: set[str] | None = None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values[:_MAX_ITEMS]:
        item = value.strip()
        if not item or len(item) > _MAX_TEXT:
            continue
        if allowed is not None and item not in allowed:
            continue
        if item not in seen:
            cleaned.append(item)
            seen.add(item)
    return cleaned


def normalize_filters(filters: SavedSearchFilters) -> dict[str, Any]:
    date_range = filters.date_range if filters.date_range in _ALLOWED_DATE_RANGES else "all"
    return {
        "q": filters.q.strip()[:_MAX_TEXT],
        "states": _clean_strings(filters.states, _ALLOWED_STATES),
        "categories": _clean_strings(filters.categories),
        "sources": _clean_strings(filters.sources),
        "starred_only": filters.starred_only,
        "include_archived": filters.include_archived,
        "date_range": date_range,
        "tag_id": filters.tag_id if filters.tag_id and filters.tag_id > 0 else None,
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["filters"] = dict(item["filters"])
    return item


def list_saved_searches(
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, name, filters, created_at, updated_at
            FROM user_saved_searches
            WHERE user_id = %s
            ORDER BY name ASC
            """,
            (user_id,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def create_saved_search(
    user_id: int,
    name: str,
    filters: SavedSearchFilters,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_saved_searches (user_id, name, filters)
            VALUES (%s, %s, %s::jsonb)
            RETURNING id, user_id, name, filters, created_at, updated_at
            """,
            (user_id, name.strip(), Jsonb(normalize_filters(filters))),
        ).fetchone()
    return _row_to_dict(row)


def update_saved_search(
    search_id: int,
    user_id: int,
    name: str | None = None,
    filters: SavedSearchFilters | None = None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    init_db(db_path, database_url=database_url)
    assignments = ["updated_at = NOW()"]
    params: list[Any] = []
    if name is not None:
        assignments.append("name = %s")
        params.append(name.strip())
    if filters is not None:
        assignments.append("filters = %s::jsonb")
        params.append(Jsonb(normalize_filters(filters)))
    params.extend([search_id, user_id])
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            f"""
            UPDATE user_saved_searches
            SET {", ".join(assignments)}
            WHERE id = %s AND user_id = %s
            RETURNING id, user_id, name, filters, created_at, updated_at
            """,
            params,
        ).fetchone()
    return _row_to_dict(row) if row else None


def delete_saved_search(
    search_id: int,
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> bool:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            "DELETE FROM user_saved_searches WHERE id = %s AND user_id = %s RETURNING id",
            (search_id, user_id),
        ).fetchone()
    return row is not None
