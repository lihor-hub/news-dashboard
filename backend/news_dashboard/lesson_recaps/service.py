"""Weekly learning recap assembly and persistence.

A learning recap summarizes one user's trailing 7-day lesson activity: which
lessons were created or completed, the concepts and themes that came up
across them, unfinished lessons still in progress, and notable source
articles worth revisiting. Persisted so history can be listed via
``GET /api/lesson-recaps``, mirroring ``news_dashboard.recaps`` for reading
recaps.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db

logger = logging.getLogger(__name__)

RECAP_WINDOW_DAYS = 7
_TOP_CONCEPTS = 8
_MAX_NOTABLE_ARTICLES = 5
_MAX_UNFINISHED = 5
_NOTABLE_VERDICTS = {"read", "study"}


class LessonRecapNotFoundError(LookupError):
    """Raised when a lesson recap does not exist or is not owned by the user."""


def assemble_weekly_lesson_recap(
    user_id: int,
    now: datetime | None = None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Aggregate the trailing 7 days of lesson activity for ``user_id``."""
    init_db(db_path, database_url=database_url)
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=RECAP_WINDOW_DAYS)

    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, title, original_url, source_name, generation_status,
                   lesson_detail, created_at, updated_at
            FROM lessons
            WHERE user_id = %s
              AND (created_at >= %s
                   OR (generation_status = 'complete' AND updated_at >= %s))
            ORDER BY created_at DESC
            """,
            (user_id, start, start),
        ).fetchall()
    lessons = [dict(r) for r in rows]

    completed = [lesson for lesson in lessons if lesson["generation_status"] == "complete"]
    unfinished = [lesson for lesson in lessons if lesson["generation_status"] != "complete"]

    return {
        "week_start": start.date().isoformat(),
        "week_end": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "lessons_touched": len(lessons),
        "lessons_completed": len(completed),
        "key_concepts": _top_concepts(completed),
        "repeated_themes": _repeated_themes(completed),
        "unfinished_lessons": _unfinished_lessons(unfinished),
        "notable_articles": _notable_articles(completed),
    }


def _top_concepts(completed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for lesson in completed:
        detail = lesson.get("lesson_detail") or {}
        for raw_concept in detail.get("prerequisite_concepts") or []:
            concept = str(raw_concept).strip()
            if concept:
                counter[concept] += 1
    return [
        {"concept": concept, "count": count}
        for concept, count in counter.most_common(_TOP_CONCEPTS)
    ]


def _repeated_themes(completed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entry for entry in _top_concepts(completed) if entry["count"] > 1]


def _unfinished_lessons(unfinished: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": lesson["id"],
            "title": lesson.get("title") or lesson["original_url"],
            "original_url": lesson["original_url"],
            "generation_status": lesson["generation_status"],
        }
        for lesson in unfinished[:_MAX_UNFINISHED]
    ]


def _notable_articles(completed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    notable = [
        lesson
        for lesson in completed
        if ((lesson.get("lesson_detail") or {}).get("read_worthiness") or {}).get("verdict")
        in _NOTABLE_VERDICTS
    ]
    return [
        {
            "id": lesson["id"],
            "title": lesson.get("title") or lesson["original_url"],
            "source_name": lesson.get("source_name"),
            "verdict": (lesson.get("lesson_detail") or {})
            .get("read_worthiness", {})
            .get("verdict"),
        }
        for lesson in notable[:_MAX_NOTABLE_ARTICLES]
    ]


def save_weekly_lesson_recap(
    user_id: int,
    recap: dict[str, Any],
    narrative: str | None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Persist a computed recap, upserting on (user_id, week_start)."""
    init_db(db_path, database_url=database_url)
    week_start = date.fromisoformat(recap["week_start"])
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_lesson_recaps (user_id, week_start, data, narrative)
            VALUES (%s, %s, %s::jsonb, %s)
            ON CONFLICT (user_id, week_start)
            DO UPDATE SET data = EXCLUDED.data, narrative = EXCLUDED.narrative,
                          podcast_status = NULL, podcast_error = NULL
            RETURNING id, user_id, week_start, created_at, data, narrative,
                      podcast_status, podcast_error
            """,
            (user_id, week_start, json.dumps(recap), narrative),
        ).fetchone()
    result = dict(row)
    result["data"] = recap
    return result


def list_lesson_recaps(
    user_id: int,
    limit: int = 12,
    offset: int = 0,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, week_start, created_at, data, narrative,
                   podcast_status, podcast_error
            FROM user_lesson_recaps
            WHERE user_id = %s
            ORDER BY week_start DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_lesson_recap(
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    recaps = list_lesson_recaps(user_id, limit=1, db_path=db_path, database_url=database_url)
    return recaps[0] if recaps else None


def get_lesson_recap(
    recap_id: int,
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            SELECT id, user_id, week_start, created_at, data, narrative,
                   podcast_status, podcast_error
            FROM user_lesson_recaps
            WHERE id = %s AND user_id = %s
            """,
            (recap_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def generate_and_save_weekly_lesson_recap(
    user_id: int,
    now: datetime | None = None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Assemble, narrate, and persist the current week's recap on demand."""
    from news_dashboard.lesson_recaps.narrative import generate_lesson_recap_narrative

    recap = assemble_weekly_lesson_recap(
        user_id, now=now, db_path=db_path, database_url=database_url
    )
    narrative = generate_lesson_recap_narrative(recap)
    return save_weekly_lesson_recap(
        user_id, recap, narrative, db_path=db_path, database_url=database_url
    )


def _update_lesson_recap_podcast_success(
    recap_id: int,
    user_id: int,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE user_lesson_recaps
            SET podcast_status = 'complete', podcast_error = NULL
            WHERE id = %s AND user_id = %s
            RETURNING id, user_id, week_start, created_at, data, narrative,
                      podcast_status, podcast_error
            """,
            (recap_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonRecapNotFoundError
    return dict(row)


def _update_lesson_recap_podcast_failure(
    recap_id: int,
    user_id: int,
    error_message: str,
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            UPDATE user_lesson_recaps
            SET podcast_status = 'failed', podcast_error = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, user_id, week_start, created_at, data, narrative,
                      podcast_status, podcast_error
            """,
            (error_message, recap_id, user_id),
        ).fetchone()
    if row is None:
        raise LessonRecapNotFoundError
    return dict(row)


class LessonRecapPodcastNotConfiguredError(RuntimeError):
    """Raised when podcast audio synthesis has no configured API key."""


class LessonRecapPodcastGenerationError(RuntimeError):
    """Raised when podcast audio synthesis fails unexpectedly."""


def generate_lesson_recap_podcast(
    recap_id: int,
    user_id: int,
    *,
    force: bool = False,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Generate (or return cached) spoken narration audio for a lesson recap."""
    recap = get_lesson_recap(recap_id, user_id, database_url=database_url)
    if recap is None:
        raise LessonRecapNotFoundError

    from news_dashboard.tts import TTSNotConfiguredError, generate_lesson_recap_podcast_audio

    try:
        generate_lesson_recap_podcast_audio(
            recap_id,
            recap["narrative"] or "",
            recap["data"],
            force=force,
        )
    except TTSNotConfiguredError as exc:
        _update_lesson_recap_podcast_failure(recap_id, user_id, str(exc), database_url=database_url)
        raise LessonRecapPodcastNotConfiguredError(str(exc)) from exc
    except ValueError:
        raise
    except Exception as exc:
        logger.warning(
            "lesson recap podcast audio generation failed for recap %d: %s", recap_id, exc
        )
        _update_lesson_recap_podcast_failure(
            recap_id,
            user_id,
            "Could not generate podcast audio.",
            database_url=database_url,
        )
        raise LessonRecapPodcastGenerationError from exc

    return _update_lesson_recap_podcast_success(recap_id, user_id, database_url=database_url)
