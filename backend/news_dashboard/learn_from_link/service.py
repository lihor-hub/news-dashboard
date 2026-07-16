"""Persistence helpers for canonical lesson records."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Literal, NotRequired, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langchain_core.messages import convert_to_messages
from langchain_core.prompt_values import ChatPromptValue
from psycopg.types.json import Jsonb
from pydantic import ValidationError
from typing_extensions import TypedDict

from news_dashboard.body_fetch import extract_body
from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.learn_from_link import agent_runs
from news_dashboard.learn_from_link.models import (
    InfographicArtifact,
    LessonDepth,
    LessonDetail,
    LessonGraphContext,
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
DEFAULT_STALE_PENDING_LESSON_MINUTES = 15
DEFAULT_LESSON_SUMMARY_LIMIT = 20
MAX_LESSON_SUMMARY_LIMIT = 100
STALE_PENDING_LESSON_ERROR = (
    "Lesson generation was interrupted before it could finish. Please retry generation."
)

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
_GRAPH_NODE_TYPES = {"concept", "entity", "article", "briefing"}
_GRAPH_RELATIONSHIP_TYPES = {"introduces", "supports", "cites", "related_to"}

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

_LESSON_ARTIFACT_RESET_ASSIGNMENTS = """\
podcast_status = NULL,
                podcast_error = NULL,
slide_deck = NULL,
                slide_deck_status = NULL,
                slide_deck_error = NULL,
                infographic = NULL,
                infographic_status = NULL,
                infographic_error = NULL,
                study_artifacts = NULL,
                personal_relevance = NULL,
                relevance_feedback = NULL,
"""
_MAX_LESSON_GRAPH_ENTITIES = 12
_MAX_LESSON_GRAPH_RELATIONSHIPS = 16
_MAX_RELATED_ARTICLES = 8
_MAX_RELATED_BRIEFINGS = 5
_LESSON_GRAPH_ENTITY_TYPES = frozenset({"concept", "person", "org", "product", "place"})


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


class LessonInfographicNotConfiguredError(RuntimeError):
    """Raised when no AI credentials are configured for lesson infographic generation."""


class LessonInfographicGenerationError(RuntimeError):
    """Raised when lesson infographic generation fails for a reason other than missing config."""


class InfographicValidationError(ValueError):
    """Raised when generated infographic content fails schema validation."""


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
    lesson["graph_context_available"] = bool(lesson.get("graph_context_available", False))
    return lesson


def _graph_key(node_type: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return f"{node_type}:{slug[:80]}"


def _graph_name(value: Any, *, max_length: int = 120) -> str:
    name = re.sub(r"\s+", " ", str(value or "")).strip()
    return name[:max_length].strip()


def _graph_node(
    nodes: dict[str, dict[str, Any]],
    *,
    name: Any,
    node_type: str,
    source_field: str,
    related_article_id: int | None = None,
) -> str | None:
    normalized = _graph_name(name)
    if not normalized or node_type not in _GRAPH_NODE_TYPES:
        return None
    node_key = _graph_key(node_type, normalized)
    nodes.setdefault(
        node_key,
        {
            "node_key": node_key,
            "name": normalized,
            "node_type": node_type,
            "source_field": source_field,
            "related_article_id": related_article_id,
        },
    )
    return node_key


def _graph_edge(
    edges: list[dict[str, Any]],
    *,
    source_key: str | None,
    target_key: str | None,
    relationship_type: str,
    label: str,
    confidence: float = 1.0,
) -> None:
    if (
        source_key is None
        or target_key is None
        or source_key == target_key
        or relationship_type not in _GRAPH_RELATIONSHIP_TYPES
    ):
        return
    edges.append(
        {
            "source_key": source_key,
            "target_key": target_key,
            "relationship_type": relationship_type,
            "label": label,
            "confidence": max(0.0, min(confidence, 1.0)),
        }
    )


def extract_lesson_graph_candidates(
    lesson_fields: dict[str, Any], *, related_article_id: int | None = None
) -> dict[str, list[dict[str, Any]]]:
    detail = lesson_fields.get("lesson_detail")
    if not isinstance(detail, dict):
        return {"nodes": [], "edges": []}

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    title_key = _graph_node(
        nodes,
        name=lesson_fields.get("title") or lesson_fields.get("original_url"),
        node_type="article",
        source_field="title",
        related_article_id=related_article_id,
    )
    source_key = _graph_node(
        nodes,
        name=lesson_fields.get("source_name"),
        node_type="entity",
        source_field="source_name",
    )
    _graph_edge(
        edges,
        source_key=title_key,
        target_key=source_key,
        relationship_type="cites",
        label="published by",
        confidence=0.7,
    )

    for concept in detail.get("prerequisite_concepts") or []:
        concept_key = _graph_node(
            nodes, name=concept, node_type="concept", source_field="prerequisite_concepts"
        )
        _graph_edge(
            edges,
            source_key=title_key,
            target_key=concept_key,
            relationship_type="introduces",
            label="introduces",
        )

    for claim in detail.get("key_claims") or []:
        claim_key = _graph_node(nodes, name=claim, node_type="concept", source_field="key_claims")
        _graph_edge(
            edges,
            source_key=title_key,
            target_key=claim_key,
            relationship_type="supports",
            label="supports",
            confidence=0.8,
        )

    for citation in detail.get("citations") or []:
        if not isinstance(citation, dict):
            continue
        citation_key = _graph_node(
            nodes, name=citation.get("source"), node_type="entity", source_field="citations"
        )
        _graph_edge(
            edges,
            source_key=title_key,
            target_key=citation_key,
            relationship_type="cites",
            label="cites",
        )

    unique_edges = {
        (edge["source_key"], edge["target_key"], edge["relationship_type"]): edge for edge in edges
    }
    return {"nodes": list(nodes.values()), "edges": list(unique_edges.values())}


def persist_lesson_graph_context(
    lesson_id: int,
    user_id: int,
    lesson_fields: dict[str, Any],
    *,
    database_url: str | None = None,
) -> int:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        related_article = conn.execute(
            """
            SELECT id FROM articles
            WHERE url = %s OR canonical_url = %s
            LIMIT 1
            """,
            (
                lesson_fields.get("original_url"),
                lesson_fields.get("normalized_url") or lesson_fields.get("original_url"),
            ),
        ).fetchone()
        related_article_id = int(related_article["id"]) if related_article is not None else None
        candidates = extract_lesson_graph_candidates(
            lesson_fields, related_article_id=related_article_id
        )
        nodes = candidates["nodes"]
        edges = candidates["edges"]
        conn.execute("DELETE FROM lesson_graph_edges WHERE lesson_id = %s", (lesson_id,))
        conn.execute("DELETE FROM lesson_graph_nodes WHERE lesson_id = %s", (lesson_id,))
        for node in nodes:
            conn.execute(
                """
                INSERT INTO lesson_graph_nodes(
                  lesson_id, user_id, node_key, name, node_type, source_field, related_article_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (lesson_id, node_key) DO UPDATE
                SET name = EXCLUDED.name,
                    node_type = EXCLUDED.node_type,
                    source_field = EXCLUDED.source_field,
                    related_article_id = EXCLUDED.related_article_id
                """,
                (
                    lesson_id,
                    user_id,
                    node["node_key"],
                    node["name"],
                    node["node_type"],
                    node["source_field"],
                    node["related_article_id"],
                ),
            )
        for edge in edges:
            conn.execute(
                """
                INSERT INTO lesson_graph_edges(
                  lesson_id, user_id, source_key, target_key,
                  relationship_type, label, confidence
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (lesson_id, source_key, target_key, relationship_type) DO UPDATE
                SET label = EXCLUDED.label,
                    confidence = EXCLUDED.confidence
                """,
                (
                    lesson_id,
                    user_id,
                    edge["source_key"],
                    edge["target_key"],
                    edge["relationship_type"],
                    edge["label"],
                    edge["confidence"],
                ),
            )
    return len(nodes)


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
            f"""
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
                {_LESSON_ARTIFACT_RESET_ASSIGNMENTS}
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
            f"""
            UPDATE lessons
            SET depth = %s,
                persona = %s,
                generation_status = 'pending',
                generation_error = NULL,
                {_LESSON_ARTIFACT_RESET_ASSIGNMENTS}
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
    try:
        persist_lesson_graph_context(lesson_id, user_id, lesson_fields, database_url=database_url)
    except Exception:
        logger.exception("lesson graph extraction failed for lesson %d", lesson_id)
    return get_lesson(lesson_id, user_id, database_url=database_url) or _serialize_lesson(row)


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


def recover_stale_pending_lessons(
    *,
    stale_after_minutes: int = DEFAULT_STALE_PENDING_LESSON_MINUTES,
    batch_limit: int = 50,
    database_url: str | None = None,
) -> int:
    """Mark stale pending lesson generations failed so users can retry them.

    Uses PostgreSQL row locking so multiple app workers can run recovery without
    processing the same pending lessons.
    """
    safe_minutes = max(1, stale_after_minutes)
    safe_limit = max(1, min(batch_limit, 500))
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            WITH stale AS (
                SELECT id
                FROM lessons
                WHERE generation_status = 'pending'
                  AND updated_at < NOW() - (%s * INTERVAL '1 minute')
                ORDER BY updated_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            ),
            recovered AS (
                UPDATE lessons
                SET generation_status = 'failed',
                    generation_error = %s,
                    updated_at = NOW()
                WHERE id IN (SELECT id FROM stale)
                RETURNING id
            ),
            failed_runs AS (
                UPDATE learning_agent_runs
                SET status = 'failed',
                    failed_step = COALESCE(failed_step, 'recovery'),
                    error = COALESCE(error, %s),
                    updated_at = NOW()
                WHERE status = 'running'
                  AND lesson_id IN (SELECT id FROM recovered)
                RETURNING id
            )
            SELECT COUNT(*) AS recovered_count FROM recovered
            """,
            (safe_minutes, safe_limit, STALE_PENDING_LESSON_ERROR, STALE_PENDING_LESSON_ERROR),
        ).fetchone()
    if row is None:
        return 0
    return int(row_to_dict(row)["recovered_count"])


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

    from langfuse import propagate_attributes

    from news_dashboard.ai_client import get_chat_model, get_prompt, langfuse_enabled, response_text
    from news_dashboard.prompt_catalog import get_chat_prompt

    model = os.getenv("OPENAI_LESSON_CHAT_MODEL", DEFAULT_LESSON_CHAT_MODEL)
    chat_model = get_chat_model(
        api_key=api_key,
        base_url=base_url,
        model=model,
        response_format={"type": "json_object"},
    )
    prompt = get_prompt(
        "lesson-slide-deck",
        fallback=get_chat_prompt("lesson-slide-deck"),
        prompt_type="chat",
        variables={"lesson_content": _build_slide_deck_prompt(lesson)},
    )
    callbacks: list[Any] = []
    if langfuse_enabled():
        from langfuse.langchain import CallbackHandler

        callbacks.append(CallbackHandler())
    with propagate_attributes(
        user_id=str(user_id),
        session_id=f"lesson:{user_id}:{lesson['id']}",
        tags=["lesson", "slide-deck"],
        trace_name="lesson-slide-deck",
        prompt=prompt.langfuse_prompt,
    ):
        prompt_value = ChatPromptValue(messages=convert_to_messages(prompt.messages))
        response = chat_model.invoke(prompt_value, config={"callbacks": callbacks})
    parsed = json.loads(response_text(response))
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


def _update_lesson_infographic_success(
    lesson_id: int,
    user_id: int,
    *,
    infographic: dict[str, Any],
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE lessons
            SET infographic = %s::jsonb,
                infographic_status = 'complete',
                infographic_error = NULL,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (Jsonb(infographic), lesson_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonNotFoundError
    return _serialize_lesson(row)


def _update_lesson_infographic_failure(
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
            SET infographic_status = 'failed',
                infographic_error = %s,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING *
            """,
            (error_message, lesson_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonNotFoundError
    return _serialize_lesson(row)


_LESSON_INFOGRAPHIC_SYSTEM_PROMPT = """\
You are the Lesson Infographic Generator. Produce a deterministic, text-first \
infographic artifact from the lesson below. Return JSON with title, subtitle, \
sections, and footer fields. Each section needs a heading and body. Ground the \
artifact only in the supplied lesson detail; do not invent facts, image URLs, \
or external assets.
"""


def _build_infographic_prompt(lesson: dict[str, Any]) -> str:
    detail = lesson.get("lesson_detail") or {}
    lines = [
        f"Title: {lesson.get('title') or lesson.get('original_url')}",
        f"Gist: {detail.get('gist', '')}",
        f"Read-worthiness: {(detail.get('read_worthiness') or {}).get('verdict', '')}",
        f"Rationale: {(detail.get('read_worthiness') or {}).get('rationale', '')}",
        f"Why it matters: {detail.get('why_it_matters', '')}",
    ]
    for label, key in (
        ("Key claims", "key_claims"),
        ("Prerequisite concepts", "prerequisite_concepts"),
        ("Questions", "questions_to_keep_in_mind"),
    ):
        values = detail.get(key) or []
        if values:
            lines.append(f"{label}:\n" + "\n".join(f"- {value}" for value in values))
    return "\n".join(lines)


def validate_infographic(raw_infographic: Any) -> dict[str, Any]:
    try:
        infographic = InfographicArtifact.model_validate(raw_infographic)
    except ValidationError as exc:
        raise InfographicValidationError from exc
    return infographic.model_dump(mode="json")


def generate_infographic_content(lesson: dict[str, Any], user_id: int) -> dict[str, Any]:
    api_key, base_url = _lesson_chat_ai_config()

    import json

    from langfuse import propagate_attributes

    from news_dashboard.ai_client import get_chat_model, get_prompt, langfuse_enabled, response_text
    from news_dashboard.prompt_catalog import get_chat_prompt

    model = os.getenv("OPENAI_LESSON_CHAT_MODEL", DEFAULT_LESSON_CHAT_MODEL)
    chat_model = get_chat_model(
        api_key=api_key,
        base_url=base_url,
        model=model,
        response_format={"type": "json_object"},
    )
    prompt = get_prompt(
        "lesson-infographic",
        fallback=get_chat_prompt("lesson-infographic"),
        prompt_type="chat",
        variables={"lesson_content": _build_infographic_prompt(lesson)},
    )
    callbacks: list[Any] = []
    if langfuse_enabled():
        from langfuse.langchain import CallbackHandler

        callbacks.append(CallbackHandler())
    with propagate_attributes(
        user_id=str(user_id),
        session_id=f"lesson:{user_id}:{lesson['id']}",
        tags=["lesson", "infographic"],
        trace_name="lesson-infographic",
        prompt=prompt.langfuse_prompt,
    ):
        prompt_value = ChatPromptValue(messages=convert_to_messages(prompt.messages))
        response = chat_model.invoke(prompt_value, config={"callbacks": callbacks})
    parsed = json.loads(response_text(response))
    return validate_infographic(parsed)


def generate_lesson_infographic(
    lesson_id: int,
    user_id: int,
    *,
    force: bool = False,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Generate (or return cached) a text-first infographic for a completed lesson."""
    lesson = get_lesson(lesson_id, user_id, database_url=database_url)
    if lesson is None:
        raise LessonNotFoundError
    if lesson.get("generation_status") != "complete" or lesson.get("lesson_detail") is None:
        raise LessonNotReadyError

    if not force and lesson.get("infographic_status") == "complete" and lesson.get("infographic"):
        return lesson

    try:
        infographic = generate_infographic_content(lesson, user_id)
    except LessonChatNotConfiguredError as exc:
        _update_lesson_infographic_failure(lesson_id, user_id, str(exc), database_url=database_url)
        raise LessonInfographicNotConfiguredError(str(exc)) from exc
    except InfographicValidationError as exc:
        logger.warning("lesson infographic validation failed for lesson %d", lesson_id)
        _update_lesson_infographic_failure(
            lesson_id,
            user_id,
            "Generated infographic was malformed.",
            database_url=database_url,
        )
        raise LessonInfographicGenerationError from exc
    except Exception as exc:
        logger.warning("lesson infographic generation failed for lesson %d: %s", lesson_id, exc)
        _update_lesson_infographic_failure(
            lesson_id,
            user_id,
            "Could not generate infographic.",
            database_url=database_url,
        )
        raise LessonInfographicGenerationError from exc

    return _update_lesson_infographic_success(
        lesson_id, user_id, infographic=infographic, database_url=database_url
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


def _graph_entity_id(name: str, entity_type: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{entity_type}:{slug}"


def _add_graph_entity(
    entities: list[dict[str, str]],
    seen: set[tuple[str, str]],
    *,
    name: str,
    entity_type: str,
) -> str | None:
    clean_name = re.sub(r"\s+", " ", name).strip()
    clean_type = entity_type.strip().lower()
    if not clean_name or clean_type not in _LESSON_GRAPH_ENTITY_TYPES:
        return None
    key = (clean_name.lower(), clean_type)
    entity_id = _graph_entity_id(clean_name, clean_type)
    if key not in seen and len(entities) < _MAX_LESSON_GRAPH_ENTITIES:
        seen.add(key)
        entities.append({"id": entity_id, "name": clean_name, "type": clean_type})
    return entity_id


def _candidate_named_entities(text: str) -> list[str]:
    candidates = re.findall(r"\b(?:[A-Z][A-Za-z0-9&.-]+)(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3}\b", text)
    ignored = {"The", "A", "An", "This", "That", "It", "Context"}
    seen: set[str] = set()
    names: list[str] = []
    for candidate in candidates:
        clean = candidate.strip()
        if clean in ignored or clean.lower() in seen:
            continue
        seen.add(clean.lower())
        names.append(clean)
        if len(names) >= 6:
            break
    return names


def extract_lesson_graph_context(
    lesson_detail: dict[str, Any],
    lesson_fields: dict[str, Any],
    *,
    user_id: int,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Build graph metadata from a validated lesson and user-visible related content."""
    entities: list[dict[str, str]] = []
    seen_entities: set[tuple[str, str]] = set()
    relationships: list[dict[str, Any]] = []

    concept_ids: list[str] = []
    for concept in lesson_detail.get("prerequisite_concepts") or []:
        entity_id = _add_graph_entity(
            entities,
            seen_entities,
            name=str(concept),
            entity_type="concept",
        )
        if entity_id is not None:
            concept_ids.append(entity_id)

    source_text = "\n".join(
        str(value)
        for value in (
            lesson_fields.get("title"),
            lesson_fields.get("source_name"),
            lesson_fields.get("author"),
            lesson_fields.get("source_content"),
        )
        if value
    )
    for name in _candidate_named_entities(source_text):
        _add_graph_entity(entities, seen_entities, name=name, entity_type="org")

    gist_id = concept_ids[0] if concept_ids else None
    for entity in entities:
        if entity["type"] != "concept" and gist_id is not None:
            relationships.append(
                {
                    "source": gist_id,
                    "target": entity["id"],
                    "relationship_type": "mentions",
                    "label": "mentions",
                    "confidence": 0.6,
                }
            )
            if len(relationships) >= _MAX_LESSON_GRAPH_RELATIONSHIPS:
                break

    related_article_ids, related_briefing_ids = _find_related_graph_content(
        user_id=user_id,
        entities=entities,
        database_url=database_url,
    )
    return {
        "available": bool(entities or related_article_ids or related_briefing_ids),
        "entities": entities,
        "relationships": relationships,
        "related_article_ids": related_article_ids,
        "related_briefing_ids": related_briefing_ids,
    }


def _find_related_graph_content(
    *,
    user_id: int,
    entities: list[dict[str, str]],
    database_url: str | None,
) -> tuple[list[int], list[int]]:
    terms = [entity["name"] for entity in entities[:6] if entity.get("name")]
    if not terms:
        return [], []

    article_ids: list[int] = []
    briefing_ids: list[int] = []
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        for term in terms:
            like_term = f"%{term}%"
            article_rows = conn.execute(
                """
                SELECT DISTINCT a.id
                FROM articles a
                JOIN sources src ON src.slug = a.source_slug
                LEFT JOIN user_sources us
                  ON us.source_slug = src.slug AND us.user_id = %s
                LEFT JOIN user_article_state uas
                  ON uas.article_id = a.id AND uas.user_id = %s
                WHERE COALESCE(uas.state, 'today') != 'archived'
                  AND (
                    (src.owner_user_id IS NULL AND COALESCE(us.enabled, TRUE) IS TRUE)
                    OR (src.owner_user_id = %s AND src.enabled IS TRUE)
                  )
                  AND (
                    a.title ILIKE %s
                    OR a.summary ILIKE %s
                    OR a.body ILIKE %s
                    OR a.entities::text ILIKE %s
                  )
                ORDER BY a.id DESC
                LIMIT %s
                """,
                (
                    user_id,
                    user_id,
                    user_id,
                    like_term,
                    like_term,
                    like_term,
                    like_term,
                    _MAX_RELATED_ARTICLES,
                ),
            ).fetchall()
            for row in article_rows:
                article_id = int(row["id"])
                if article_id not in article_ids:
                    article_ids.append(article_id)
                    if len(article_ids) >= _MAX_RELATED_ARTICLES:
                        break
            if len(article_ids) >= _MAX_RELATED_ARTICLES:
                break

        for term in terms:
            like_term = f"%{term}%"
            rows = conn.execute(
                """
                SELECT DISTINCT id
                FROM briefings
                WHERE user_id = %s
                  AND (title ILIKE %s OR content::text ILIKE %s)
                ORDER BY id DESC
                LIMIT %s
                """,
                (user_id, like_term, like_term, _MAX_RELATED_BRIEFINGS),
            ).fetchall()
            for row in rows:
                briefing_id = int(row["id"])
                if briefing_id not in briefing_ids:
                    briefing_ids.append(briefing_id)
                    if len(briefing_ids) >= _MAX_RELATED_BRIEFINGS:
                        break
            if len(briefing_ids) >= _MAX_RELATED_BRIEFINGS:
                break
    return article_ids, briefing_ids


def _add_lesson_graph_context(
    *,
    user_id: int,
    lesson_id: int,
    lesson_fields: dict[str, Any],
    database_url: str | None,
) -> None:
    try:
        raw_context = extract_lesson_graph_context(
            lesson_fields["lesson_detail"],
            lesson_fields,
            user_id=user_id,
            database_url=database_url,
        )
        graph_context = LessonGraphContext.model_validate(raw_context)
        lesson_fields["lesson_detail"]["graph_context"] = graph_context.model_dump(mode="json")
    except Exception as exc:
        logger.warning("lesson graph extraction failed for lesson %d: %s", lesson_id, exc)


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
            lesson_id=lesson_id,
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


class LessonGraphState(TypedDict):
    """Typed state shared by the durable lesson-generation graph."""

    lesson_id: int
    user_id: int
    database_url: str | None
    run_id: int
    depth: LessonDepth
    persona: LessonPersona
    lesson_url: str
    metadata: NotRequired[dict[str, Any]]
    body_text: NotRequired[str]
    lesson_fields: NotRequired[dict[str, Any]]
    detail_model: NotRequired[LessonDetail]
    error: NotRequired[str]
    failed_step: NotRequired[str]
    result: NotRequired[dict[str, Any]]


def _lesson_graph_route(state: LessonGraphState) -> Literal["continue", "fail"]:
    return "fail" if state.get("error") else "continue"


def build_lesson_graph() -> Any:  # noqa: PLR0915 - graph wiring is clearest in one factory
    """Compile the lesson pipeline without a checkpointer.

    Durable run, step, generation, and lesson records remain the persistence
    boundary; graph state is deliberately invocation-local.
    """
    from langgraph.graph import END, START, StateGraph

    # LangGraph's runtime accepts TypedDict schemas, while ty/pyrefly do not
    # currently recognize Python 3.14's TypedDict metaclass against its bound.
    state_schema = cast("Any", LessonGraphState)
    graph = StateGraph(state_schema)

    def fetch_node(state: LessonGraphState) -> dict[str, Any]:
        metadata = _run_fetch_step(state["database_url"], state["run_id"], state["lesson_url"])
        return {"metadata": metadata}

    def extraction_node(state: LessonGraphState) -> dict[str, Any]:
        body_text, error = _run_extraction_step(
            state["database_url"], state["run_id"], state["lesson_url"]
        )
        if error or body_text is None:
            return {
                "error": error or "Could not extract readable article content.",
                "failed_step": agent_runs.STEP_EXTRACTION,
            }
        metadata = state.get("metadata", {})
        return {
            "body_text": body_text,
            "lesson_fields": {
                "original_url": state["lesson_url"],
                "title": str(metadata.get("title") or state["lesson_url"]),
                "source_name": metadata.get("site_name"),
                "author": metadata.get("author"),
                "published_at": metadata.get("published_at"),
                "source_content": body_text,
            },
        }

    def synthesis_node(state: LessonGraphState) -> dict[str, Any]:
        lesson_fields = state["lesson_fields"]
        detail_model, artifacts, error = _run_synthesis_step(
            state["database_url"],
            state["run_id"],
            lesson_fields,
            state["depth"],
            state["persona"],
            state["lesson_id"],
        )
        if error or detail_model is None:
            return {
                "error": error or "Generated lesson detail was malformed.",
                "failed_step": agent_runs.STEP_SYNTHESIS,
            }
        lesson_fields["study_artifacts"] = artifacts
        return {"lesson_fields": lesson_fields, "detail_model": detail_model}

    def citation_node(state: LessonGraphState) -> dict[str, Any]:
        lesson_fields = state["lesson_fields"]
        detail, error = _run_citation_verification_step(
            state["database_url"],
            state["run_id"],
            state["detail_model"],
            lesson_fields,
            state["lesson_id"],
        )
        if error or detail is None:
            return {
                "error": error or "Generated lesson citations did not match source content.",
                "failed_step": agent_runs.STEP_CITATION_VERIFICATION,
            }
        lesson_fields["lesson_detail"] = detail
        _add_lesson_graph_context(
            user_id=state["user_id"],
            lesson_id=state["lesson_id"],
            lesson_fields=lesson_fields,
            database_url=state["database_url"],
        )
        return {"lesson_fields": lesson_fields}

    def relevance_node(state: LessonGraphState) -> dict[str, Any]:
        lesson_fields = state["lesson_fields"]
        _add_personal_relevance(
            state["user_id"],
            state["lesson_id"],
            lesson_fields,
            state["database_url"],
        )
        return {"lesson_fields": lesson_fields}

    def persistence_node(state: LessonGraphState) -> dict[str, Any]:
        started = time.monotonic()
        try:
            result = _update_lesson_success(
                state["lesson_id"],
                state["user_id"],
                lesson_fields=state["lesson_fields"],
                database_url=state["database_url"],
            )
            _record_lesson_generation(
                state["lesson_id"],
                depth=state["depth"],
                persona=state["persona"],
                generation_status="complete",
                lesson_detail=state["lesson_fields"]["lesson_detail"],
                generation_error=None,
                database_url=state["database_url"],
            )
        except Exception as exc:
            agent_runs.record_step(
                state["database_url"],
                state["run_id"],
                agent_runs.STEP_PERSISTENCE,
                5,
                status="failed",
                latency_ms=int((time.monotonic() - started) * 1000),
                error=str(exc)[:2000],
            )
            agent_runs.finish_run(
                state["database_url"],
                state["run_id"],
                status="failed",
                failed_step=agent_runs.STEP_PERSISTENCE,
                error=str(exc)[:2000],
            )
            raise
        agent_runs.record_step(
            state["database_url"],
            state["run_id"],
            agent_runs.STEP_PERSISTENCE,
            5,
            status="complete",
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        agent_runs.finish_run(state["database_url"], state["run_id"], status="complete")
        return {"result": result}

    def failure_node(state: LessonGraphState) -> dict[str, Any]:
        error = state["error"]
        result = _update_lesson_failure(
            state["lesson_id"], state["user_id"], error, database_url=state["database_url"]
        )
        _record_lesson_generation(
            state["lesson_id"],
            depth=state["depth"],
            persona=state["persona"],
            generation_status="failed",
            lesson_detail=None,
            generation_error=error,
            database_url=state["database_url"],
        )
        agent_runs.finish_run(
            state["database_url"],
            state["run_id"],
            status="failed",
            failed_step=state["failed_step"],
            error=error,
        )
        return {"result": result}

    graph.add_node("fetch", fetch_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("citation_verification", citation_node)
    graph.add_node("personal_relevance", relevance_node)
    graph.add_node("persistence", persistence_node)
    graph.add_node("failure", failure_node)
    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "extraction")
    graph.add_conditional_edges(
        "extraction", _lesson_graph_route, {"continue": "synthesis", "fail": "failure"}
    )
    graph.add_conditional_edges(
        "synthesis",
        _lesson_graph_route,
        {"continue": "citation_verification", "fail": "failure"},
    )
    graph.add_conditional_edges(
        "citation_verification",
        _lesson_graph_route,
        {"continue": "personal_relevance", "fail": "failure"},
    )
    graph.add_edge("personal_relevance", "persistence")
    graph.add_edge("persistence", END)
    graph.add_edge("failure", END)
    return graph.compile()


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

    from langfuse import propagate_attributes

    from news_dashboard.ai_client import langfuse_enabled

    callbacks: list[Any] = []
    if langfuse_enabled():
        from langfuse.langchain import CallbackHandler

        callbacks.append(CallbackHandler())
    with propagate_attributes(
        user_id=str(user_id),
        session_id=f"lesson-run:{run_id}",
        tags=["lesson", "generation"],
        trace_name="lesson-generation",
    ):
        final_state = build_lesson_graph().invoke(
            {
                "lesson_id": lesson_id,
                "user_id": user_id,
                "database_url": database_url,
                "run_id": run_id,
                "depth": depth,
                "persona": persona,
                "lesson_url": str(lesson["original_url"]),
            },
            config={"callbacks": callbacks},
        )
    return cast("dict[str, Any]", final_state["result"])


def list_lessons(
    user_id: int,
    *,
    q: str | None = None,
    status: str | None = None,
    verdict: str | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(database_url=database_url)
    query = """
        SELECT lessons.*,
               EXISTS(
                 SELECT 1 FROM lesson_graph_nodes
                 WHERE lesson_graph_nodes.lesson_id = lessons.id
               ) AS graph_context_available
        FROM lessons
        WHERE user_id = %s
    """
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


def list_lesson_summaries(
    user_id: int,
    *,
    q: str | None = None,
    status: str | None = None,
    verdict: str | None = None,
    limit: int = DEFAULT_LESSON_SUMMARY_LIMIT,
    offset: int = 0,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    bounded_limit = max(1, min(limit, MAX_LESSON_SUMMARY_LIMIT))
    bounded_offset = max(0, offset)
    where_sql = "WHERE user_id = %s"
    params: list[Any] = [user_id]
    if status is not None:
        where_sql += " AND generation_status = %s"
        params.append(status)
    if verdict is not None:
        where_sql += " AND lesson_detail->'read_worthiness'->>'verdict' = %s"
        params.append(verdict)
    if q is not None and q.strip():
        where_sql += """
            AND (
                title ILIKE %s
                OR original_url ILIKE %s
                OR source_name ILIKE %s
                OR lesson_detail::text ILIKE %s
            )
        """
        term = f"%{q.strip()}%"
        params.extend([term, term, term, term])

    count_query = f"SELECT COUNT(*) AS total_count FROM lessons {where_sql}"
    query = f"""
        SELECT id,
               user_id,
               original_url,
               normalized_url,
               title,
               source_name,
               author,
               published_at,
               generation_status,
               generation_error,
               jsonb_build_object(
                 'gist', lesson_detail->>'gist',
                 'read_worthiness', lesson_detail->'read_worthiness'
               ) AS lesson_detail,
               depth,
               persona,
               podcast_status,
               podcast_error,
               slide_deck_status,
               slide_deck_error,
               infographic_status,
               infographic_error,
               EXISTS(
                 SELECT 1 FROM lesson_graph_nodes
                 WHERE lesson_graph_nodes.lesson_id = lessons.id
               ) AS graph_context_available,
               created_at,
               updated_at
        FROM lessons
        {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    with connect(database_url=database_url) as conn:
        total_row = conn.execute(count_query, params).fetchone()
        rows = conn.execute(query, [*params, bounded_limit, bounded_offset]).fetchall()
    lessons = [_serialize_lesson(row) for row in rows]
    total = int(total_row["total_count"]) if total_row is not None else 0
    for lesson in lessons:
        if lesson.get("lesson_detail", {}).get("gist") is None:
            lesson["lesson_detail"] = None
    next_offset = bounded_offset + bounded_limit if bounded_offset + bounded_limit < total else None
    return {
        "lessons": lessons,
        "total": total,
        "limit": bounded_limit,
        "offset": bounded_offset,
        "next_offset": next_offset,
    }


def get_lesson(
    lesson_id: int,
    user_id: int,
    *,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            SELECT lessons.*,
                   EXISTS(
                     SELECT 1 FROM lesson_graph_nodes
                     WHERE lesson_graph_nodes.lesson_id = lessons.id
                   ) AS graph_context_available
            FROM lessons
            WHERE id = %s AND user_id = %s
            """,
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
    from langfuse import propagate_attributes

    from news_dashboard.ai_client import (
        get_chat_model,
        get_prompt,
        langfuse_enabled,
        response_text,
    )
    from news_dashboard.prompt_catalog import get_chat_prompt

    chat_model = get_chat_model(api_key=api_key, base_url=base_url, model=model)
    prompt = get_prompt(
        "lesson-chat",
        fallback=get_chat_prompt("lesson-chat"),
        prompt_type="chat",
        variables={
            "lesson_context": lesson_context,
            "source_context": source_context,
            "question": stripped,
        },
    )
    messages = [*prompt.messages[:-1], *history, prompt.messages[-1]]
    prompt_value = ChatPromptValue(messages=convert_to_messages(messages))
    callbacks: list[Any] = []
    if langfuse_enabled():
        from langfuse.langchain import CallbackHandler

        callbacks.append(CallbackHandler())
    with propagate_attributes(
        user_id=str(user_id),
        session_id=f"lesson:{user_id}:{lesson_id}",
        tags=["lesson", "chat"],
        trace_name="lesson-chat",
        prompt=prompt.langfuse_prompt,
    ):
        response = chat_model.invoke(prompt_value, config={"callbacks": callbacks})
    return response_text(response)


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
    lesson_id: int,
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

    from langfuse import propagate_attributes

    from news_dashboard.ai_client import get_chat_model, get_prompt, langfuse_enabled, response_text
    from news_dashboard.prompt_catalog import get_chat_prompt

    lesson_title = str(lesson_fields.get("title") or lesson_fields.get("original_url"))
    lesson_detail = lesson_fields.get("lesson_detail") or {}
    lesson_context = f"Lesson title: {lesson_title}\nLesson gist: {lesson_detail.get('gist', '')}"
    profile_context = (
        f"Interests: {interests}\n"
        f"Reading DNA categories: {dna_categories}\n"
        f"Reading DNA sources: {dna_sources}\n"
        f"Recent article titles: {[item['title'] for item in recent_articles]}"
    )
    try:
        model = os.getenv("OPENAI_LESSON_CHAT_MODEL", DEFAULT_LESSON_CHAT_MODEL)
        chat_model = get_chat_model(
            api_key=api_key,
            base_url=base_url,
            model=model,
            response_format={"type": "json_object"},
        )
        prompt = get_prompt(
            "lesson-relevance",
            fallback=get_chat_prompt("lesson-relevance"),
            prompt_type="chat",
            variables={
                "lesson_context": lesson_context,
                "profile_context": profile_context,
            },
        )
        callbacks: list[Any] = []
        if langfuse_enabled():
            from langfuse.langchain import CallbackHandler

            callbacks.append(CallbackHandler())
        with propagate_attributes(
            user_id=str(user_id),
            session_id=f"lesson:{user_id}:{lesson_id}",
            tags=["lesson", "relevance"],
            trace_name="lesson-relevance",
            prompt=prompt.langfuse_prompt,
        ):
            prompt_value = ChatPromptValue(messages=convert_to_messages(prompt.messages))
            response = chat_model.invoke(prompt_value, config={"callbacks": callbacks})
        parsed = json.loads(response_text(response))
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
                   EXTRACT(EPOCH FROM (NOW() - a.discovered_at)) / 86400.0
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
