"""Persistence helpers for canonical lesson records."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import ValidationError

from news_dashboard.body_fetch import extract_body
from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.learn_from_link.models import LessonContent
from news_dashboard.reading_list.metadata import fetch_url_metadata
from news_dashboard.reading_list.service import normalize_url
from news_dashboard.url_safety import UnsafeUrlError, validate_server_fetch_url

logger = logging.getLogger(__name__)

DEFAULT_LESSON_MODEL = "gpt-4o-mini"
_MAX_SOURCE_CHARS = 6_000
_LESSON_PROMPT = (
    "You are a study-aid assistant helping a lazy-but-curious reader decide whether an "
    "article is worth their time. Based ONLY on the article below, produce a structured "
    "lesson as a single JSON object with exactly these keys:\n"
    "- gist: a one or two sentence, 30-second summary\n"
    "- explanation: a short paragraph explaining the core idea\n"
    "- key_claims: a JSON array of the main factual claims or arguments (strings)\n"
    "- prerequisites: a JSON array of concepts the reader should already know (strings, "
    "can be empty)\n"
    "- why_it_matters: one or two sentences on why this is worth caring about\n"
    '- verdict: one of "skip", "skim", "read", "study"\n'
    "- verdict_rationale: one or two sentences justifying the verdict\n"
    "- intended_readers: a JSON array describing who should read the full source "
    "(strings, can be empty)\n"
    "- guiding_questions: a JSON array of questions to keep in mind while reading "
    "(strings, can be empty)\n"
    '- citations: a JSON array of objects with a "text" key holding a short snippet '
    "quoted verbatim from the article that supports a key claim (can be empty)\n\n"
    "Return ONLY the JSON object. No other text."
)


class LessonUrlError(ValueError):
    """Raised when a lesson URL cannot be fetched safely."""


class LessonNotFoundError(LookupError):
    """Raised when a lesson row cannot be found for the given user."""


class LessonGenerationError(RuntimeError):
    """Raised when the AI failed to produce a valid structured lesson."""


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
                lesson_content = NULL,
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
    lesson_content = lesson_fields.get("lesson_content")
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
                lesson_content = %s::jsonb,
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
                json.dumps(lesson_content) if lesson_content is not None else None,
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
                lesson_content = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (error_message, lesson_id, user_id),
        ).fetchone()
    return _serialize_lesson(row)


def _lesson_ai_config() -> tuple[str, str | None, str]:
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        msg = "FREE_LLM_API_KEY (or OPENAI_API_KEY) is not configured"
        raise RuntimeError(msg)
    model = os.getenv("OPENAI_LESSON_MODEL", DEFAULT_LESSON_MODEL)
    return api_key, base_url, model


def _normalize_for_matching(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _verify_citations(content: LessonContent, source_content: str) -> LessonContent:
    """Drop any citation whose text isn't actually present in the source content."""
    normalized_source = _normalize_for_matching(source_content)
    verified = [
        citation
        for citation in content.citations
        if _normalize_for_matching(citation.text) in normalized_source
    ]
    if len(verified) != len(content.citations):
        logger.warning(
            "dropped %d lesson citation(s) not found in source content",
            len(content.citations) - len(verified),
        )
    return content.model_copy(update={"citations": verified})


def _parse_lesson_content(response_text: str) -> LessonContent:
    from news_dashboard.ai_client import strip_markdown_fence

    text = strip_markdown_fence(response_text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = "AI returned malformed JSON for the structured lesson"
        raise LessonGenerationError(msg) from exc
    if not isinstance(data, dict):
        msg = "AI returned a non-object JSON payload for the structured lesson"
        raise LessonGenerationError(msg)
    try:
        return LessonContent.model_validate(data)
    except ValidationError as exc:
        msg = "AI-generated lesson failed schema validation"
        raise LessonGenerationError(msg) from exc


def generate_lesson_content(
    *,
    user_id: int,
    title: str,
    source_content: str,
) -> LessonContent:
    """Call the AI model to produce and validate a structured lesson.

    Raises :class:`LessonGenerationError` when the model is unavailable or its
    output does not validate against :class:`LessonContent`.
    """
    try:
        api_key, base_url, model = _lesson_ai_config()
    except RuntimeError as exc:
        raise LessonGenerationError(str(exc)) from exc

    from news_dashboard.ai_client import chat_create, get_chat_client

    client = get_chat_client(api_key=api_key, base_url=base_url)
    truncated_source = source_content[:_MAX_SOURCE_CHARS]
    messages = [
        {
            "role": "user",
            "content": f"{_LESSON_PROMPT}\n\nTitle: {title}\n\nArticle:\n{truncated_source}",
        }
    ]
    try:
        result = chat_create(
            client,
            name="learn-from-link-lesson",
            tags=["learn-from-link"],
            user_id=user_id,
            model=model,
            messages=messages,
            max_tokens=1500,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise LessonGenerationError(str(exc)) from exc

    response_text = (result.choices[0].message.content or "").strip()
    content = _parse_lesson_content(response_text)
    return _verify_citations(content, source_content)


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

    title = str(metadata.get("title") or lesson_url)
    try:
        lesson_content = generate_lesson_content(
            user_id=user_id,
            title=title,
            source_content=body_text,
        )
    except LessonGenerationError as exc:
        logger.warning("lesson content generation failed for %r: %s", lesson_url, exc)
        return _update_lesson_failure(
            lesson_id,
            user_id,
            "Could not generate a structured lesson from this article.",
            database_url=database_url,
        )

    return _update_lesson_success(
        lesson_id,
        user_id,
        lesson_fields={
            "title": title,
            "source_name": metadata.get("site_name"),
            "author": metadata.get("author"),
            "published_at": metadata.get("published_at"),
            "source_content": body_text,
            "lesson_content": lesson_content.model_dump(mode="json"),
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
