"""Persistence helpers for canonical lesson records."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from news_dashboard.body_fetch import extract_body
from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.learn_from_link import agent_runs
from news_dashboard.learn_from_link.models import (
    LessonDepth,
    LessonDetail,
    LessonPersona,
    PersonalRelevance,
    SlideDeck,
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


class LessonNotReadyError(ValueError):
    """Raised when podcast audio is requested before the lesson finished generating."""


class LessonPodcastNotConfiguredError(RuntimeError):
    """Raised when no TTS credentials are configured for lesson podcast audio."""


class LessonPodcastGenerationError(RuntimeError):
    """Raised when lesson podcast audio synthesis fails for a reason other than missing config."""


class LessonSlideDeckNotConfiguredError(RuntimeError):
    """Raised when no AI credentials are configured for lesson slide deck generation."""


class LessonSlideDeckGenerationError(RuntimeError):
    """Raised when lesson slide deck generation fails for a reason other than missing config."""


class SlideDeckValidationError(ValueError):
    """Raised when generated slide deck content fails schema validation."""


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
                personal_relevance = %s::jsonb,
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
                Jsonb(lesson_fields["personal_relevance"])
                if lesson_fields.get("personal_relevance") is not None
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


def _update_lesson_podcast_success(
    lesson_id: int,
    user_id: int,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE lessons
            SET podcast_status = 'complete',
                podcast_error = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (lesson_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonNotFoundError
    return _serialize_lesson(row)


def _update_lesson_podcast_failure(
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
            SET podcast_status = 'failed',
                podcast_error = %s,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (error_message, lesson_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonNotFoundError
    return _serialize_lesson(row)


def generate_lesson_podcast(
    lesson_id: int,
    user_id: int,
    *,
    force: bool = False,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Generate (or return cached) spoken narration audio for a completed lesson.

    Narration is built from the lesson's structured ``lesson_detail`` fields so
    it stays consistent with what's shown on the lesson page, rather than
    re-summarizing the raw source article independently.
    """
    lesson = get_lesson(lesson_id, user_id, database_url=database_url)
    if lesson is None:
        raise LessonNotFoundError
    if lesson.get("generation_status") != "complete" or lesson.get("lesson_detail") is None:
        raise LessonNotReadyError

    from news_dashboard.tts import TTSNotConfiguredError, generate_lesson_podcast_audio

    title = str(lesson.get("title") or lesson["original_url"])
    try:
        generate_lesson_podcast_audio(
            lesson_id,
            title,
            lesson["lesson_detail"],
            force=force,
        )
    except TTSNotConfiguredError as exc:
        _update_lesson_podcast_failure(lesson_id, user_id, str(exc), database_url=database_url)
        raise LessonPodcastNotConfiguredError(str(exc)) from exc
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("lesson podcast audio generation failed for lesson %d: %s", lesson_id, exc)
        _update_lesson_podcast_failure(
            lesson_id,
            user_id,
            "Could not generate podcast audio.",
            database_url=database_url,
        )
        raise LessonPodcastGenerationError from exc

    return _update_lesson_podcast_success(lesson_id, user_id, database_url=database_url)


def _update_lesson_slide_deck_success(
    lesson_id: int,
    user_id: int,
    *,
    slide_deck: dict[str, Any],
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE lessons
            SET slide_deck = %s::jsonb,
                slide_deck_status = 'complete',
                slide_deck_error = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (Jsonb(slide_deck), lesson_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonNotFoundError
    return _serialize_lesson(row)


def _update_lesson_slide_deck_failure(
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
            SET slide_deck_status = 'failed',
                slide_deck_error = %s,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (error_message, lesson_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonNotFoundError
    return _serialize_lesson(row)


_LESSON_SLIDE_DECK_SYSTEM_PROMPT = """\
You are the Lesson Slide Deck Generator. Produce a short teaching slide deck \
summarizing the lesson below as a shareable learning artifact. Return JSON \
with a "slides" array of 6 to 10 slides, each with a "title" and 1-6 \
"bullets". Ground every slide in the supplied lesson detail; do not invent \
facts.
"""


def _build_slide_deck_prompt(lesson: dict[str, Any]) -> str:
    detail = lesson.get("lesson_detail") or {}
    lines = [
        f"Title: {lesson.get('title') or lesson.get('original_url')}",
        f"Gist: {detail.get('gist', '')}",
        f"Explanation: {detail.get('explanation', '')}",
        f"Why it matters: {detail.get('why_it_matters', '')}",
    ]
    key_claims = detail.get("key_claims") or []
    if key_claims:
        lines.append("Key claims:\n" + "\n".join(f"- {claim}" for claim in key_claims))
    concepts = detail.get("prerequisite_concepts") or []
    if concepts:
        lines.append("Concepts:\n" + "\n".join(f"- {concept}" for concept in concepts))
    citations = detail.get("citations") or []
    if citations:
        evidence = "\n".join(
            f"- {citation.get('label', '')}: {citation.get('snippet', '')}"
            for citation in citations
        )
        lines.append("Evidence:\n" + evidence)
    return "\n".join(lines)


def validate_slide_deck(raw_deck: Any) -> dict[str, Any]:
    try:
        deck = SlideDeck.model_validate(raw_deck)
    except ValidationError as exc:
        raise SlideDeckValidationError from exc
    return deck.model_dump(mode="json")


def generate_slide_deck_content(lesson: dict[str, Any], user_id: int) -> dict[str, Any]:
    api_key, base_url = _lesson_chat_ai_config()

    import json

    from news_dashboard.ai_client import chat_create, get_chat_client

    client = get_chat_client(api_key=api_key, base_url=base_url)
    messages = [
        {"role": "system", "content": _LESSON_SLIDE_DECK_SYSTEM_PROMPT},
        {"role": "user", "content": _build_slide_deck_prompt(lesson)},
    ]
    response = chat_create(
        client,
        name="lesson-slide-deck",
        tags=["lesson", "slide-deck"],
        user_id=user_id,
        model=os.getenv("OPENAI_LESSON_CHAT_MODEL", DEFAULT_LESSON_CHAT_MODEL),
        messages=messages,
        response_format={"type": "json_object"},
    )
    parsed = json.loads(response.choices[0].message.content or "")
    return validate_slide_deck(parsed)


def generate_lesson_slide_deck(
    lesson_id: int,
    user_id: int,
    *,
    force: bool = False,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Generate (or return cached) a teaching slide deck for a completed lesson.

    Slides are built from the lesson's structured ``lesson_detail`` fields so
    they stay consistent with what's shown on the lesson page, rather than
    re-summarizing the raw source article independently.
    """
    lesson = get_lesson(lesson_id, user_id, database_url=database_url)
    if lesson is None:
        raise LessonNotFoundError
    if lesson.get("generation_status") != "complete" or lesson.get("lesson_detail") is None:
        raise LessonNotReadyError

    if not force and lesson.get("slide_deck_status") == "complete" and lesson.get("slide_deck"):
        return lesson

    try:
        deck = generate_slide_deck_content(lesson, user_id)
    except LessonChatNotConfiguredError as exc:
        _update_lesson_slide_deck_failure(lesson_id, user_id, str(exc), database_url=database_url)
        raise LessonSlideDeckNotConfiguredError(str(exc)) from exc
    except SlideDeckValidationError as exc:
        logger.warning("lesson slide deck validation failed for lesson %d", lesson_id)
        _update_lesson_slide_deck_failure(
            lesson_id,
            user_id,
            "Generated slide deck was malformed.",
            database_url=database_url,
        )
        raise LessonSlideDeckGenerationError from exc
    except Exception as exc:
        logger.warning("lesson slide deck generation failed for lesson %d: %s", lesson_id, exc)
        _update_lesson_slide_deck_failure(
            lesson_id,
            user_id,
            "Could not generate slide deck.",
            database_url=database_url,
        )
        raise LessonSlideDeckGenerationError from exc

    return _update_lesson_slide_deck_success(
        lesson_id, user_id, slide_deck=deck, database_url=database_url
    )


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


def validate_structured_lesson_detail(raw_detail: Any) -> LessonDetail:
    """Validate a raw synthesis payload against the LessonDetail schema.

    This is the structured-output boundary check: it runs immediately after
    generation and before any downstream code (including citation
    verification) touches the payload.
    """
    try:
        return LessonDetail.model_validate(raw_detail)
    except ValidationError as exc:
        raise LessonDetailValidationError from exc


def verify_lesson_citations(detail: LessonDetail, lesson_fields: dict[str, Any]) -> dict[str, Any]:
    """Verify every citation is grounded in the source content, as its own pipeline step.

    Raises LessonCitationValidationError if any citation snippet or source
    label cannot be found in the lesson's fetched metadata/content.
    """
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


def _build_lesson_detail(
    lesson_fields: dict[str, Any],
    depth: LessonDepth,
    persona: LessonPersona,
    lesson_id: int,
) -> tuple[LessonDetail | None, str | None]:
    """Generate + schema-validate a lesson detail (the "synthesis" step).

    Citation grounding is verified separately by :func:`verify_lesson_citations`
    so it can be tracked as its own pipeline step.
    """
    try:
        raw_detail = generate_structured_lesson_detail(lesson_fields, depth=depth, persona=persona)
        detail = validate_structured_lesson_detail(raw_detail)
    except LessonDetailValidationError:
        logger.warning("lesson detail validation failed for lesson %d", lesson_id)
        return None, "Generated lesson detail was malformed."
    except Exception as exc:
        logger.warning("lesson detail generation failed for lesson %d: %s", lesson_id, exc)
        return None, "Generated lesson detail was malformed."
    return detail, None


def _build_study_artifacts(
    lesson_fields: dict[str, Any],
    lesson_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw_artifacts = generate_study_artifacts(lesson_fields)
        artifacts = validate_study_artifacts(raw_artifacts)
    except StudyArtifactsValidationError:
        logger.warning("study artifacts validation failed for lesson %d", lesson_id)
        return None, "Generated study artifacts were malformed."
    except Exception as exc:
        logger.warning("study artifacts generation failed for lesson %d: %s", lesson_id, exc)
        return None, "Generated study artifacts were malformed."
    return artifacts, None


def _add_personal_relevance(
    user_id: int,
    lesson_id: int,
    lesson_fields: dict[str, Any],
    database_url: str | None,
) -> None:
    try:
        raw_relevance = generate_personal_relevance(
            user_id,
            lesson_fields,
            database_url=database_url,
        )
        lesson_fields["personal_relevance"] = validate_personal_relevance(raw_relevance)
    except Exception as exc:
        logger.warning("personal relevance generation failed for lesson %d: %s", lesson_id, exc)
        lesson_fields["personal_relevance"] = {
            "explanation": "This lesson might interest you based on your reading profile.",
            "signals": [],
        }


def _timed(func: Any, *args: Any, **kwargs: Any) -> tuple[Any, int]:
    """Call ``func`` and return ``(result, elapsed_ms)``."""
    start = time.monotonic()
    result = func(*args, **kwargs)
    return result, int((time.monotonic() - start) * 1000)


def _run_fetch_step(database_url: str | None, run_id: int, lesson_url: str) -> dict[str, Any]:
    """Fetch article metadata. Non-fatal: failures are logged and the pipeline continues."""
    try:
        metadata, latency_ms = _timed(fetch_url_metadata, lesson_url)
    except Exception as exc:
        logger.warning("lesson metadata fetch failed for %r: %s", lesson_url, exc)
        agent_runs.record_step(
            database_url, run_id, agent_runs.STEP_FETCH, 1, status="failed", error=str(exc)[:2000]
        )
        return {}
    agent_runs.record_step(
        database_url, run_id, agent_runs.STEP_FETCH, 1, status="complete", latency_ms=latency_ms
    )
    return dict(metadata)


def _run_extraction_step(
    database_url: str | None, run_id: int, lesson_url: str
) -> tuple[str | None, str | None]:
    """Extract article body text. Returns ``(body_text, error_message)``."""
    try:
        (body, status), latency_ms = _timed(extract_body, lesson_url)
    except Exception as exc:
        logger.warning("lesson body extraction failed for %r: %s", lesson_url, exc)
        agent_runs.record_step(
            database_url,
            run_id,
            agent_runs.STEP_EXTRACTION,
            2,
            status="failed",
            error=str(exc)[:2000],
        )
        return None, "Could not extract readable article content."

    body_text = body.strip()
    if status != "ok" or not body_text:
        agent_runs.record_step(
            database_url,
            run_id,
            agent_runs.STEP_EXTRACTION,
            2,
            status="failed",
            latency_ms=latency_ms,
            error=f"extract_body returned status={status!r}",
        )
        return None, "Could not extract readable article content."

    agent_runs.record_step(
        database_url,
        run_id,
        agent_runs.STEP_EXTRACTION,
        2,
        status="complete",
        latency_ms=latency_ms,
    )
    return body_text, None


def _run_synthesis_step(
    database_url: str | None,
    run_id: int,
    lesson_fields: dict[str, Any],
    depth: LessonDepth,
    persona: LessonPersona,
    lesson_id: int,
) -> tuple[LessonDetail | None, dict[str, Any] | None, str | None]:
    """Generate the lesson detail + study artifacts. Returns ``(detail, artifacts, error)``."""
    start = time.monotonic()
    detail_model, detail_error = _build_lesson_detail(lesson_fields, depth, persona, lesson_id)
    artifacts: dict[str, Any] | None = None
    error = detail_error
    if error is None:
        artifacts, artifacts_error = _build_study_artifacts(lesson_fields, lesson_id)
        error = artifacts_error
    agent_runs.record_step(
        database_url,
        run_id,
        agent_runs.STEP_SYNTHESIS,
        3,
        status="failed" if error else "complete",
        latency_ms=int((time.monotonic() - start) * 1000),
        error=error,
    )
    if error or detail_model is None:
        return None, None, error or "Generated lesson detail was malformed."
    return detail_model, artifacts, None


def _run_citation_verification_step(
    database_url: str | None,
    run_id: int,
    detail_model: LessonDetail,
    lesson_fields: dict[str, Any],
    lesson_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Verify citations are grounded in source content. Returns ``(detail, error)``."""
    start = time.monotonic()
    error: str | None = None
    detail: dict[str, Any] | None = None
    try:
        detail = verify_lesson_citations(detail_model, lesson_fields)
    except LessonCitationValidationError:
        logger.warning("lesson citation validation failed for lesson %d", lesson_id)
        error = "Generated lesson citations did not match source content."
    agent_runs.record_step(
        database_url,
        run_id,
        agent_runs.STEP_CITATION_VERIFICATION,
        4,
        status="failed" if error else "complete",
        latency_ms=int((time.monotonic() - start) * 1000),
        error=error,
    )
    return detail, error


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
    chat_model = os.getenv("OPENAI_LESSON_CHAT_MODEL", DEFAULT_LESSON_CHAT_MODEL)
    run_id = agent_runs.start_run(
        database_url,
        lesson_id=lesson_id,
        user_id=user_id,
        prompt_version=agent_runs.SYNTHESIS_PROMPT_VERSION,
        model_version=chat_model,
        config={"depth": depth, "persona": persona},
    )

    def _fail(error_message: str, *, failed_step: str) -> dict[str, Any]:
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
        agent_runs.finish_run(
            database_url,
            run_id,
            status="failed",
            failed_step=failed_step,
            error=error_message,
        )
        return result

    lesson_url = str(lesson["original_url"])
    metadata = _run_fetch_step(database_url, run_id, lesson_url)

    body_text, extraction_error = _run_extraction_step(database_url, run_id, lesson_url)
    if extraction_error or body_text is None:
        return _fail(
            extraction_error or "Could not extract readable article content.",
            failed_step=agent_runs.STEP_EXTRACTION,
        )

    lesson_fields: dict[str, Any] = {
        "original_url": lesson_url,
        "title": str(metadata.get("title") or lesson_url),
        "source_name": metadata.get("site_name"),
        "author": metadata.get("author"),
        "published_at": metadata.get("published_at"),
        "source_content": body_text,
    }

    detail_model, artifacts, synthesis_error = _run_synthesis_step(
        database_url, run_id, lesson_fields, depth, persona, lesson_id
    )
    if synthesis_error or detail_model is None:
        return _fail(
            synthesis_error or "Generated lesson detail was malformed.",
            failed_step=agent_runs.STEP_SYNTHESIS,
        )
    lesson_fields["study_artifacts"] = artifacts

    detail, citation_error = _run_citation_verification_step(
        database_url, run_id, detail_model, lesson_fields, lesson_id
    )
    if citation_error or detail is None:
        return _fail(
            citation_error or "Generated lesson citations did not match source content.",
            failed_step=agent_runs.STEP_CITATION_VERIFICATION,
        )
    lesson_fields["lesson_detail"] = detail

    _add_personal_relevance(
        user_id,
        lesson_id,
        lesson_fields,
        database_url=database_url,
    )

    persistence_start = time.monotonic()
    try:
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
    except Exception as exc:
        agent_runs.record_step(
            database_url,
            run_id,
            agent_runs.STEP_PERSISTENCE,
            5,
            status="failed",
            latency_ms=int((time.monotonic() - persistence_start) * 1000),
            error=str(exc)[:2000],
        )
        agent_runs.finish_run(
            database_url,
            run_id,
            status="failed",
            failed_step=agent_runs.STEP_PERSISTENCE,
            error=str(exc)[:2000],
        )
        raise
    agent_runs.record_step(
        database_url,
        run_id,
        agent_runs.STEP_PERSISTENCE,
        5,
        status="complete",
        latency_ms=int((time.monotonic() - persistence_start) * 1000),
    )
    agent_runs.finish_run(database_url, run_id, status="complete")
    return result


def list_lessons(
    user_id: int,
    *,
    q: str | None = None,
    status: str | None = None,
    verdict: str | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(database_url=database_url)
    query = "SELECT * FROM lessons WHERE user_id = %s"
    params: list[Any] = [user_id]
    if status is not None:
        query += " AND generation_status = %s"
        params.append(status)
    if verdict is not None:
        query += " AND lesson_detail->'read_worthiness'->>'verdict' = %s"
        params.append(verdict)
    if q is not None and q.strip():
        query += """
            AND (
                title ILIKE %s
                OR original_url ILIKE %s
                OR source_name ILIKE %s
                OR lesson_detail::text ILIKE %s
            )
        """
        term = f"%{q.strip()}%"
        params.extend([term, term, term, term])
    query += " ORDER BY created_at DESC"
    with connect(database_url=database_url) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_serialize_lesson(row) for row in rows]


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


def _get_relevance_data(
    user_id: int,
    database_url: str | None,
) -> tuple[list[str], list[str], list[str], list[dict[str, Any]]]:
    from news_dashboard.analytics import reading_dna
    from news_dashboard.article_visibility import visible_article_sql

    interests: list[str] = []
    try:
        with connect(database_url=database_url) as conn:
            row = conn.execute(
                "SELECT interests FROM user_interest_profiles WHERE user_id = %s",
                (user_id,),
            ).fetchone()
            if row and row["interests"]:
                interests = [str(item) for item in row["interests"]]
    except Exception as exc:
        logger.warning("Failed to fetch user interests for relevance: %s", exc)

    dna_categories: list[str] = []
    dna_sources: list[str] = []
    try:
        dna = reading_dna(user_id, days=30, database_url=database_url)
        dna_categories = [
            str(item["category"]) for item in dna.get("categories", []) if item.get("category")
        ]
        dna_sources = [str(item["source"]) for item in dna.get("sources", []) if item.get("source")]
    except Exception as exc:
        logger.warning("Failed to fetch reading DNA for relevance: %s", exc)

    recent_articles: list[dict[str, Any]] = []
    try:
        with connect(database_url=database_url) as conn:
            rows = conn.execute(
                f"""
                SELECT a.title, a.source_name, a.category, s.state, s.starred
                FROM user_article_state s
                JOIN articles a ON a.id = s.article_id
                JOIN sources a_src ON a_src.slug = a.source_slug
                LEFT JOIN user_sources a_us
                  ON a_us.source_slug = a.source_slug AND a_us.user_id = %s
                WHERE s.user_id = %s AND (s.state = 'done' OR s.starred = TRUE)
                  AND ({visible_article_sql("a")})
                ORDER BY s.updated_at DESC
                LIMIT 10
                """,
                (user_id, user_id, user_id),
            ).fetchall()
            recent_articles = [row_to_dict(row) for row in rows]
    except Exception as exc:
        logger.warning("Failed to fetch recent reads/saves for relevance: %s", exc)

    return interests, dna_categories, dna_sources, recent_articles


def generate_personal_relevance(
    user_id: int,
    lesson_fields: dict[str, Any],
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    interests, dna_categories, dna_sources, recent_articles = _get_relevance_data(
        user_id,
        database_url,
    )
    if not interests and not dna_categories and not dna_sources and not recent_articles:
        return {
            "explanation": (
                "No personalization data is available yet. "
                "Start reading articles to see custom relevance explanations."
            ),
            "signals": [],
        }

    try:
        api_key, base_url = _lesson_chat_ai_config()
    except LessonChatNotConfiguredError:
        return {"explanation": "Personalization is not configured.", "signals": []}

    import json

    from news_dashboard.ai_client import chat_create, get_chat_client

    lesson_title = str(lesson_fields.get("title") or lesson_fields.get("original_url"))
    lesson_detail = lesson_fields.get("lesson_detail") or {}
    messages = [
        {
            "role": "system",
            "content": (
                "Explain why a lesson is relevant using only the user's provided reading profile. "
                "Return JSON with non-empty explanation and a signals array."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Lesson title: {lesson_title}\n"
                f"Lesson gist: {lesson_detail.get('gist', '')}\n"
                f"Interests: {interests}\n"
                f"Reading DNA categories: {dna_categories}\n"
                f"Reading DNA sources: {dna_sources}\n"
                f"Recent article titles: {[item['title'] for item in recent_articles]}"
            ),
        },
    ]
    try:
        response = chat_create(
            get_chat_client(api_key=api_key, base_url=base_url),
            name="lesson-relevance",
            tags=["lesson", "relevance"],
            user_id=user_id,
            model=os.getenv("OPENAI_LESSON_CHAT_MODEL", DEFAULT_LESSON_CHAT_MODEL),
            messages=messages,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content or "")
        return {
            "explanation": str(parsed["explanation"]),
            "signals": [str(signal) for signal in parsed["signals"] if signal],
        }
    except Exception as exc:
        logger.warning("Failed to generate relevance with LLM: %s", exc)
        return {
            "explanation": "This lesson might interest you based on your reading profile.",
            "signals": [],
        }


def validate_personal_relevance(raw_relevance: Any) -> dict[str, Any]:
    try:
        relevance = PersonalRelevance.model_validate(raw_relevance)
    except ValidationError as exc:
        message = "Invalid personal relevance schema"
        raise ValueError(message) from exc
    return relevance.model_dump(mode="json")


_SUGGESTION_LIMIT_DEFAULT = 10
_SUGGESTION_CANDIDATE_POOL = 200
_NOVELTY_RECENT_DAYS = 7
_NOVELTY_MEDIUM_DAYS = 30


def _novelty_score(age_days: float | None) -> float:
    if age_days is None:
        return 0.3
    if age_days <= _NOVELTY_RECENT_DAYS:
        return 1.0
    if age_days <= _NOVELTY_MEDIUM_DAYS:
        return 0.6
    return 0.3


def _score_suggestion_candidate(
    article: dict[str, Any],
    *,
    interests: list[str],
    dna_categories: list[str],
    dna_sources: list[str],
) -> dict[str, Any]:
    url = str(article["canonical_url"])
    category = str(article.get("category") or "")
    source_name = str(article.get("source_name") or "")
    title = str(article.get("title") or "")
    starred = bool(article.get("starred"))
    try:
        importance = int(article.get("importance_score") or 50)
    except (TypeError, ValueError):
        importance = 50
    age_days_raw = article.get("age_days")
    age_days = float(age_days_raw) if age_days_raw is not None else None

    reasons: list[str] = []
    relevance_score = 0.0
    if category and category in dna_categories:
        relevance_score += 0.5
        reasons.append(f"Matches your recent interest in {category}")
    if source_name and source_name in dna_sources:
        relevance_score += 0.3
        reasons.append(f"From {source_name}, a source you read often")
    if interests and any(interest.lower() in title.lower() for interest in interests):
        relevance_score += 0.2
        reasons.append("Matches topics you told us you're interested in")
    relevance_score = min(relevance_score, 1.0)

    interest_signal = 1.0 if starred else 0.6
    if starred:
        reasons.append("You starred this article")

    novelty_score = _novelty_score(age_days)
    if novelty_score >= 1.0:
        reasons.append("Recently added to your reading list")

    value_score = importance / 100
    if importance >= 80:
        reasons.append("High editorial importance score")

    total = (
        0.35 * relevance_score + 0.25 * interest_signal + 0.15 * novelty_score + 0.25 * value_score
    )
    if not reasons:
        reasons.append("A good candidate based on your reading history")

    return {
        "article_id": int(article["id"]),
        "title": title or url,
        "url": url,
        "source_name": source_name or None,
        "category": category or None,
        "score": round(total, 3),
        "reasons": reasons,
    }


def list_lesson_suggestions(
    user_id: int,
    *,
    database_url: str | None = None,
    limit: int = _SUGGESTION_LIMIT_DEFAULT,
) -> list[dict[str, Any]]:
    """Suggest saved/read articles worth turning into a lesson.

    Candidates are the user's starred or completed articles that don't already
    have a lesson and haven't been dismissed, scored using relevance to the
    user's reading DNA/interests, novelty, and editorial importance.
    """
    from news_dashboard.article_visibility import visible_article_sql

    interests, dna_categories, dna_sources, _ = _get_relevance_data(user_id, database_url)
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            f"""
            SELECT a.id, a.title, a.canonical_url, a.source_name, a.category,
                   a.importance_score, s.starred,
                   EXTRACT(EPOCH FROM (NOW() - a.discovered_at::timestamptz)) / 86400.0
                     AS age_days
            FROM articles a
            JOIN user_article_state s ON s.article_id = a.id
            JOIN sources a_src ON a_src.slug = a.source_slug
            LEFT JOIN user_sources a_us
              ON a_us.source_slug = a.source_slug AND a_us.user_id = %s
            WHERE s.user_id = %s AND (s.state = 'done' OR s.starred = TRUE)
              AND ({visible_article_sql("a")})
            ORDER BY a.discovered_at DESC
            LIMIT %s
            """,
            (user_id, user_id, user_id, _SUGGESTION_CANDIDATE_POOL),
        ).fetchall()
        existing_lesson_rows = conn.execute(
            "SELECT normalized_url FROM lessons WHERE user_id = %s", (user_id,)
        ).fetchall()
        dismissed_rows = conn.execute(
            "SELECT article_id FROM user_lesson_suggestion_dismissals WHERE user_id = %s",
            (user_id,),
        ).fetchall()

    existing_lesson_urls = {str(r["normalized_url"]) for r in existing_lesson_rows}
    dismissed_ids = {int(r["article_id"]) for r in dismissed_rows}

    candidates: list[dict[str, Any]] = []
    for row in rows:
        article = row_to_dict(row)
        article_id = int(article["id"])
        if article_id in dismissed_ids:
            continue
        if _normalize_lesson_url(str(article["canonical_url"])) in existing_lesson_urls:
            continue
        candidates.append(
            _score_suggestion_candidate(
                article,
                interests=interests,
                dna_categories=dna_categories,
                dna_sources=dna_sources,
            )
        )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:limit]


def dismiss_lesson_suggestion(
    user_id: int,
    article_id: int,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        conn.execute(
            """
            INSERT INTO user_lesson_suggestion_dismissals(user_id, article_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, article_id) DO NOTHING
            """,
            (user_id, article_id),
        )
    return {"dismissed": True, "article_id": article_id}


def submit_relevance_feedback(
    lesson_id: int,
    user_id: int,
    helpful: bool,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE lessons
            SET relevance_feedback = %s,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (helpful, lesson_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonNotFoundError
    return _serialize_lesson(row)
