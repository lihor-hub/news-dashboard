"""Persistence helpers for canonical lesson records."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.reading_list.service import normalize_url
from news_dashboard.url_safety import UnsafeUrlError, validate_server_fetch_url


class LessonUrlError(ValueError):
    """Raised when a lesson URL cannot be fetched safely."""


def _normalize_lesson_url(url: str) -> str:
    normalized = normalize_url(url)
    parts = urlsplit(normalized)
    sorted_query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, sorted_query, parts.fragment))


def _serialize_lesson(row: Any) -> dict[str, Any]:
    lesson = row_to_dict(row)
    for key in ("created_at", "updated_at"):
        value = lesson.get(key)
        if value is not None:
            lesson[key] = value.isoformat()
    return lesson


def create_lesson(
    user_id: int,
    url: str,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    cleaned = url.strip()
    try:
        validate_server_fetch_url(cleaned)
    except UnsafeUrlError as exc:
        raise LessonUrlError(str(exc)) from exc

    normalized = _normalize_lesson_url(cleaned)
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO lessons (
              user_id,
              original_url,
              normalized_url,
              generation_status,
              generation_error
            )
            VALUES (%s, %s, %s, 'pending', NULL)
            ON CONFLICT (user_id, normalized_url) DO UPDATE
            SET original_url = EXCLUDED.original_url,
                generation_status = 'pending',
                generation_error = NULL,
                updated_at = NOW()
            RETURNING *
            """,
            (user_id, cleaned, normalized),
        ).fetchone()
    return _serialize_lesson(row)


def get_lesson(
    lesson_id: int,
    user_id: int,
    *,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "SELECT * FROM lessons WHERE id = %s AND user_id = %s",
            (lesson_id, user_id),
        ).fetchone()
    if row is None:
        return None
    return _serialize_lesson(row)
