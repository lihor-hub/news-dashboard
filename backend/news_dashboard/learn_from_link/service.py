"""Persistence helpers for canonical lesson records."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from news_dashboard.body_fetch import extract_body
from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.learn_from_link.models import LessonDetail
from news_dashboard.reading_list.metadata import fetch_url_metadata
from news_dashboard.reading_list.service import normalize_url
from news_dashboard.url_safety import UnsafeUrlError, validate_server_fetch_url

logger = logging.getLogger(__name__)


class LessonUrlError(ValueError):
    """Raised when a lesson URL cannot be fetched safely."""


class LessonNotFoundError(LookupError):
    """Raised when a lesson row cannot be found for the given user."""


class LessonDetailValidationError(ValueError):
    """Raised when generated lesson detail fails schema validation."""


class LessonCitationValidationError(ValueError):
    """Raised when lesson citations are not grounded in source content."""


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
                lesson_detail = NULL,
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
    lesson_fields: dict[str, Any],
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
                lesson_detail = %s::jsonb,
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
                Jsonb(lesson_fields["lesson_detail"]),
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
                lesson_detail = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (error_message, lesson_id, user_id),
        ).fetchone()
    return _serialize_lesson(row)


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    return [
        sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", compact) if sentence.strip()
    ]


def _clip(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def generate_structured_lesson_detail(lesson_fields: dict[str, Any]) -> dict[str, Any]:
    source_content = str(lesson_fields["source_content"])
    title = str(lesson_fields["title"] or lesson_fields["original_url"])
    source_name = lesson_fields.get("source_name")
    sentence_list = _sentences(source_content)
    gist = sentence_list[0] if sentence_list else _clip(source_content, 180)
    key_claims = sentence_list[:3] or [gist]
    source_label = str(source_name or "the source")
    if len(source_content) >= 2000:
        verdict = "study"
        rationale = "Study it closely: the source is substantial enough to reward careful notes."
    elif len(source_content) >= 600:
        verdict = "read"
        rationale = "Read it: the source has enough depth to justify focused attention."
    else:
        verdict = "skim"
        rationale = "Start with a skim: the source is short enough to inspect quickly."

    return {
        "gist": gist,
        "explanation": source_content if len(source_content) <= 600 else _clip(source_content, 600),
        "key_claims": key_claims,
        "prerequisite_concepts": [f"Context from {source_label}"],
        "why_it_matters": f"It helps you decide whether {title} deserves deeper reading.",
        "read_worthiness": {
            "verdict": verdict,
            "rationale": rationale,
        },
        "who_should_read": ["Readers deciding whether to spend more time with this source."],
        "questions_to_keep_in_mind": [
            "What evidence does the source provide for its central claim?"
        ],
        "citations": [
            {
                "label": "1",
                "snippet": gist,
                "source": title,
            }
        ],
    }


def validate_structured_lesson_detail(
    raw_detail: Any,
    *,
    lesson_fields: dict[str, Any],
) -> dict[str, Any]:
    try:
        detail = LessonDetail.model_validate(raw_detail)
    except ValidationError as exc:
        raise LessonDetailValidationError from exc

    source_context = _normalized_text(
        "\n".join(
            str(value)
            for value in (
                lesson_fields.get("title"),
                lesson_fields.get("source_name"),
                lesson_fields.get("author"),
                lesson_fields.get("published_at"),
                lesson_fields.get("original_url"),
                lesson_fields.get("source_content"),
            )
            if value
        )
    )
    for citation in detail.citations:
        citation_snippet = _normalized_text(citation.snippet)
        citation_source = _normalized_text(citation.source)
        if citation_snippet not in source_context or citation_source not in source_context:
            raise LessonCitationValidationError

    return detail.model_dump(mode="json")


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

    lesson_fields: dict[str, Any] = {
        "original_url": lesson_url,
        "title": str(metadata.get("title") or lesson_url),
        "source_name": metadata.get("site_name"),
        "author": metadata.get("author"),
        "published_at": metadata.get("published_at"),
        "source_content": body_text,
    }
    try:
        raw_detail = generate_structured_lesson_detail(lesson_fields)
        lesson_fields["lesson_detail"] = validate_structured_lesson_detail(
            raw_detail,
            lesson_fields=lesson_fields,
        )
    except LessonDetailValidationError:
        logger.warning("lesson detail validation failed for lesson %d", lesson_id)
        return _update_lesson_failure(
            lesson_id,
            user_id,
            "Generated lesson detail was malformed.",
            database_url=database_url,
        )
    except LessonCitationValidationError:
        logger.warning("lesson citation validation failed for lesson %d", lesson_id)
        return _update_lesson_failure(
            lesson_id,
            user_id,
            "Generated lesson citations did not match source content.",
            database_url=database_url,
        )
    except Exception as exc:
        logger.warning("lesson detail generation failed for lesson %d: %s", lesson_id, exc)
        return _update_lesson_failure(
            lesson_id,
            user_id,
            "Generated lesson detail was malformed.",
            database_url=database_url,
        )

    return _update_lesson_success(
        lesson_id,
        user_id,
        lesson_fields=lesson_fields,
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
