"""Persistence helpers for canonical lesson records."""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from news_dashboard.body_fetch import extract_body
from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.learn_from_link.models import (
    LessonDepth,
    LessonDetail,
    LessonPersona,
    StudyArtifacts,
)
from news_dashboard.reading_list.metadata import fetch_url_metadata
from news_dashboard.reading_list.service import normalize_url
from news_dashboard.url_safety import UnsafeUrlError, validate_server_fetch_url


class StudyArtifactsValidationError(ValueError):
    """Raised when generated study artifacts fail schema validation."""


logger = logging.getLogger(__name__)

DEFAULT_LESSON_CHAT_MODEL = "gpt-4o-mini"

_DEPTH_EXPLANATION_LIMITS: dict[str, int] = {
    "tiny": 150,
    "normal": 600,
    "deep": 1500,
    "expert": 4000,
}
_DEPTH_KEY_CLAIM_COUNTS: dict[str, int] = {
    "tiny": 1,
    "normal": 3,
    "deep": 5,
    "expert": 8,
}
_PERSONA_FRAMING: dict[str, str] = {
    "developer": "for developers weighing implementation details",
    "product_builder": "for product builders assessing user impact",
    "new_to_ai": "for readers new to AI who want a clear on-ramp",
    "preparing_talk": "for someone preparing a talk on this topic",
}

_LESSON_CHAT_SYSTEM_PROMPT = """\
You are the Lesson Follow-up Assistant. Answer follow-up questions about the \
lesson below, grounded in the lesson detail and source article content \
supplied. If information is not present in the provided context, say so \
clearly rather than guessing.

--- LESSON ---
{lesson_context}

--- SOURCE ARTICLE ---
{source_context}
"""


class LessonUrlError(ValueError):
    """Raised when a lesson URL cannot be fetched safely."""


class LessonNotFoundError(LookupError):
    """Raised when a lesson row cannot be found for the given user."""


class LessonQuestionEmptyError(ValueError):
    """Raised when a lesson follow-up question is blank."""


class LessonChatNotConfiguredError(RuntimeError):
    """Raised when no AI credentials are configured for lesson follow-up chat."""


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
    depth: LessonDepth = "normal",
    persona: LessonPersona = "developer",
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
              generation_error,
              depth,
              persona
            )
            VALUES (%s, %s, %s, 'pending', NULL, %s, %s)
            ON CONFLICT (user_id, normalized_url) DO UPDATE
            SET generation_status = 'pending',
                generation_error = NULL,
                title = NULL,
                source_name = NULL,
                author = NULL,
                published_at = NULL,
                source_content = NULL,
                lesson_detail = NULL,
                depth = %s,
                persona = %s,
                updated_at = NOW()
            RETURNING *
            """,
            (user_id, cleaned, normalized, depth, persona, depth, persona),
        ).fetchone()
    lesson = _serialize_lesson(row)
    if not extract:
        return lesson
    return generate_lesson_from_url(
        int(lesson["id"]),
        user_id,
        database_url=database_url,
    )


def regenerate_lesson(
    lesson_id: int,
    user_id: int,
    *,
    depth: LessonDepth,
    persona: LessonPersona,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Mark a lesson pending regeneration under new depth/persona controls.

    Prior generations remain in ``lesson_generations`` history; only the
    current-generation controls on the ``lessons`` row are replaced.
    """
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE lessons
            SET depth = %s,
                persona = %s,
                generation_status = 'pending',
                generation_error = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (depth, persona, lesson_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonNotFoundError
    return _serialize_lesson(row)


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
                study_artifacts = %s::jsonb,
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
                Jsonb(lesson_fields["study_artifacts"])
                if lesson_fields.get("study_artifacts") is not None
                else None,
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
                study_artifacts = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (error_message, lesson_id, user_id),
        ).fetchone()
    return _serialize_lesson(row)


def _record_lesson_generation(
    lesson_id: int,
    *,
    depth: str,
    persona: str,
    generation_status: str,
    lesson_detail: dict[str, Any] | None,
    generation_error: str | None,
    database_url: str | None = None,
) -> None:
    """Append an immutable history row for a completed or failed generation."""
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO lesson_generations (
              lesson_id, depth, persona, lesson_detail, generation_status, generation_error
            )
            VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                lesson_id,
                depth,
                persona,
                Jsonb(lesson_detail) if lesson_detail is not None else None,
                generation_status,
                generation_error,
            ),
        )


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


def generate_structured_lesson_detail(
    lesson_fields: dict[str, Any],
    *,
    depth: LessonDepth = "normal",
    persona: LessonPersona = "developer",
) -> dict[str, Any]:
    source_content = str(lesson_fields["source_content"])
    title = str(lesson_fields["title"] or lesson_fields["original_url"])
    source_name = lesson_fields.get("source_name")
    sentence_list = _sentences(source_content)
    gist = sentence_list[0] if sentence_list else _clip(source_content, 180)
    claim_count = _DEPTH_KEY_CLAIM_COUNTS[depth]
    key_claims = sentence_list[:claim_count] or [gist]
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

    explanation_limit = _DEPTH_EXPLANATION_LIMITS[depth]
    framing = _PERSONA_FRAMING[persona]

    return {
        "gist": gist,
        "explanation": source_content
        if len(source_content) <= explanation_limit
        else _clip(source_content, explanation_limit),
        "key_claims": key_claims,
        "prerequisite_concepts": [f"Context from {source_label}"],
        "why_it_matters": (
            f"It helps you decide whether {title} deserves deeper reading, {framing}."
        ),
        "read_worthiness": {
            "verdict": verdict,
            "rationale": rationale,
        },
        "who_should_read": [
            f"Readers deciding whether to spend more time with this source, {framing}."
        ],
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


def validate_study_artifacts(raw_artifacts: Any) -> dict[str, Any]:
    try:
        artifacts = StudyArtifacts.model_validate(raw_artifacts)
    except ValidationError as exc:
        raise StudyArtifactsValidationError from exc
    return artifacts.model_dump(mode="json")


def generate_study_artifacts(lesson_fields: dict[str, Any]) -> dict[str, Any]:
    source_content = str(lesson_fields["source_content"])
    sentence_list = _sentences(source_content)
    gist = sentence_list[0] if sentence_list else _clip(source_content, 180)
    return {
        "comprehension_questions": [
            {
                "question": "What is the primary topic of the text?",
                "expected_answer": f"The primary topic is: {gist}",
            }
        ],
        "flashcards": [
            {
                "concept": "Core Claim",
                "claim": f"{gist}",
            }
        ],
        "quiz": [
            {
                "question": "Which of the following best summarizes the main point of the source?",
                "options": [
                    f"{gist}",
                    "A completely unrelated fact about the topic.",
                    "An incorrect assertion about the author.",
                    "A generic fallback option.",
                ],
                "correct_index": 0,
                "explanation": f"The source content explicitly states the core claim: {gist}",
            }
        ],
    }


def generate_lesson_from_url(
    lesson_id: int,
    user_id: int,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    lesson = get_lesson(lesson_id, user_id, database_url=database_url)
    if lesson is None:
        raise LessonNotFoundError

    depth = lesson["depth"]
    persona = lesson["persona"]

    def _fail(error_message: str) -> dict[str, Any]:
        result = _update_lesson_failure(
            lesson_id,
            user_id,
            error_message,
            database_url=database_url,
        )
        _record_lesson_generation(
            lesson_id,
            depth=depth,
            persona=persona,
            generation_status="failed",
            lesson_detail=None,
            generation_error=error_message,
            database_url=database_url,
        )
        return result

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
        return _fail("Could not extract readable article content.")

    body_text = body.strip()
    if status != "ok" or not body_text:
        return _fail("Could not extract readable article content.")

    lesson_fields: dict[str, Any] = {
        "original_url": lesson_url,
        "title": str(metadata.get("title") or lesson_url),
        "source_name": metadata.get("site_name"),
        "author": metadata.get("author"),
        "published_at": metadata.get("published_at"),
        "source_content": body_text,
    }
    try:
        raw_detail = generate_structured_lesson_detail(lesson_fields, depth=depth, persona=persona)
        lesson_fields["lesson_detail"] = validate_structured_lesson_detail(
            raw_detail,
            lesson_fields=lesson_fields,
        )
    except LessonDetailValidationError:
        logger.warning("lesson detail validation failed for lesson %d", lesson_id)
        return _fail("Generated lesson detail was malformed.")
    except LessonCitationValidationError:
        logger.warning("lesson citation validation failed for lesson %d", lesson_id)
        return _fail("Generated lesson citations did not match source content.")
    except Exception as exc:
        logger.warning("lesson detail generation failed for lesson %d: %s", lesson_id, exc)
        return _fail("Generated lesson detail was malformed.")

    try:
        raw_artifacts = generate_study_artifacts(lesson_fields)
        lesson_fields["study_artifacts"] = validate_study_artifacts(raw_artifacts)
    except StudyArtifactsValidationError:
        logger.warning("study artifacts validation failed for lesson %d", lesson_id)
        return _fail("Generated study artifacts were malformed.")
    except Exception as exc:
        logger.warning("study artifacts generation failed for lesson %d: %s", lesson_id, exc)
        return _fail("Generated study artifacts were malformed.")

    result = _update_lesson_success(
        lesson_id,
        user_id,
        lesson_fields=lesson_fields,
        database_url=database_url,
    )
    _record_lesson_generation(
        lesson_id,
        depth=depth,
        persona=persona,
        generation_status="complete",
        lesson_detail=lesson_fields["lesson_detail"],
        generation_error=None,
        database_url=database_url,
    )
    return result


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


def list_lesson_generations(
    lesson_id: int,
    user_id: int,
    *,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    """Return prior generation history for a lesson, newest first.

    Raises LessonNotFoundError if the lesson does not exist for this user.
    """
    if get_lesson(lesson_id, user_id, database_url=database_url) is None:
        raise LessonNotFoundError

    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT * FROM lesson_generations
            WHERE lesson_id = %s
            ORDER BY created_at DESC
            """,
            (lesson_id,),
        ).fetchall()

    generations = []
    for row in rows:
        generation = row_to_dict(row)
        if generation.get("created_at") is not None:
            generation["created_at"] = generation["created_at"].isoformat()
        generations.append(generation)
    return generations


def _lesson_chat_ai_config() -> tuple[str, str | None]:
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        msg = "FREE_LLM_API_KEY (or OPENAI_API_KEY) is not configured"
        raise LessonChatNotConfiguredError(msg)
    return api_key, base_url


def _lesson_chat_context(lesson: dict[str, Any]) -> tuple[str, str]:
    detail = lesson.get("lesson_detail") or {}
    lesson_lines = [
        f"Title: {lesson.get('title') or lesson.get('original_url')}",
        f"Gist: {detail.get('gist', '')}",
        f"Explanation: {detail.get('explanation', '')}",
        f"Why it matters: {detail.get('why_it_matters', '')}",
    ]
    key_claims = detail.get("key_claims") or []
    if key_claims:
        lesson_lines.append("Key claims:\n" + "\n".join(f"- {claim}" for claim in key_claims))
    lesson_context = "\n".join(lesson_lines)
    source_content = str(lesson.get("source_content") or "")[:6000]
    source_context = source_content or "(No source content extracted.)"
    return lesson_context, source_context


def ask_lesson_question(
    lesson_id: int,
    user_id: int,
    question: str,
    history: list[dict[str, str]],
    *,
    database_url: str | None = None,
) -> str:
    """Answer a follow-up question grounded in a lesson's detail and source content."""
    stripped = question.strip()
    if not stripped:
        raise LessonQuestionEmptyError

    lesson = get_lesson(lesson_id, user_id, database_url=database_url)
    if lesson is None:
        raise LessonNotFoundError

    api_key, base_url = _lesson_chat_ai_config()
    model = os.getenv("OPENAI_LESSON_CHAT_MODEL", DEFAULT_LESSON_CHAT_MODEL)

    lesson_context, source_context = _lesson_chat_context(lesson)
    system = _LESSON_CHAT_SYSTEM_PROMPT.format(
        lesson_context=lesson_context,
        source_context=source_context,
    )

    from news_dashboard.ai_client import chat_create, get_chat_client

    client = get_chat_client(api_key=api_key, base_url=base_url)
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": stripped})

    response = chat_create(
        client,
        name="lesson-chat",
        tags=["lesson", "chat"],
        user_id=user_id,
        model=model,
        messages=messages,
    )
    return response.choices[0].message.content or ""
