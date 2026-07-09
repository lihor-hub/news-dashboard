"""Persistence helpers for canonical lesson records."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from news_dashboard.body_fetch import extract_body
from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.reading_list.metadata import fetch_url_metadata
from news_dashboard.reading_list.service import normalize_url
from news_dashboard.url_safety import UnsafeUrlError, validate_server_fetch_url

logger = logging.getLogger(__name__)


class LessonUrlError(ValueError):
    """Raised when a lesson URL cannot be fetched safely."""


class LessonNotFoundError(LookupError):
    """Raised when a lesson row cannot be found for the given user."""


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
    extract: bool = True,
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
            SET generation_status = 'pending',
                generation_error = NULL,
                title = NULL,
                source_name = NULL,
                author = NULL,
                published_at = NULL,
                source_content = NULL,
                updated_at = NOW()
            RETURNING *
            """,
            (user_id, cleaned, normalized),
        ).fetchone()
    lesson = _serialize_lesson(row)
    if not extract:
        return lesson
    return generate_lesson_from_url(
        int(lesson["id"]),
        user_id,
        database_url=database_url,
    )


def _update_lesson_success(
    lesson_id: int,
    user_id: int,
    *,
    lesson_fields: dict[str, str | None],
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE lessons
            SET title = %s,
                source_name = %s,
                author = %s,
                published_at = %s,
                source_content = %s,
                generation_status = 'complete',
                generation_error = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (
                lesson_fields["title"],
                lesson_fields["source_name"],
                lesson_fields["author"],
                lesson_fields["published_at"],
                lesson_fields["source_content"],
                lesson_id,
                user_id,
            ),
        ).fetchone()
    return _serialize_lesson(row)


def _update_lesson_failure(
    lesson_id: int,
    user_id: int,
    error_message: str,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE lessons
            SET generation_status = 'failed',
                generation_error = %s,
                title = NULL,
                source_name = NULL,
                author = NULL,
                published_at = NULL,
                source_content = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (error_message, lesson_id, user_id),
        ).fetchone()
    return _serialize_lesson(row)


def generate_lesson_from_url(
    lesson_id: int,
    user_id: int,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    lesson = get_lesson(lesson_id, user_id, database_url=database_url)
    if lesson is None:
        raise LessonNotFoundError

    lesson_url = str(lesson["original_url"])
    metadata: dict[str, Any] = {}
    try:
        metadata = fetch_url_metadata(lesson_url)
    except Exception as exc:
        logger.warning("lesson metadata fetch failed for %r: %s", lesson_url, exc)

    try:
        body, status = extract_body(lesson_url)
    except Exception as exc:
        logger.warning("lesson body extraction failed for %r: %s", lesson_url, exc)
        return _update_lesson_failure(
            lesson_id,
            user_id,
            "Could not extract readable article content.",
            database_url=database_url,
        )

    body_text = body.strip()
    if status != "ok" or not body_text:
        return _update_lesson_failure(
            lesson_id,
            user_id,
            "Could not extract readable article content.",
            database_url=database_url,
        )

    return _update_lesson_success(
        lesson_id,
        user_id,
        lesson_fields={
            "title": str(metadata.get("title") or lesson_url),
            "source_name": metadata.get("site_name"),
            "author": metadata.get("author"),
            "published_at": metadata.get("published_at"),
            "source_content": body_text,
        },
        database_url=database_url,
    )


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
