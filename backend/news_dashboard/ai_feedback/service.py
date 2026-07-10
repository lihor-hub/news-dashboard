"""Persist explicit thumbs up/down feedback on briefings, recommendations, and lessons.

Recommendation feedback keys ``subject_id`` on the article id (there is no
separate recommendation entity — see ``user_article_recommendations``'s
``(user_id, article_id)`` primary key). Briefing feedback keys ``subject_id``
on the briefing id, optionally scoped to one cited ``article_id`` within it.
Lesson feedback keys ``subject_id`` on the lesson id and doubles as an eval
seed: each verdict is captured as an ``ai_eval_examples`` row (feature
``lesson-feedback``) so real user judgments can later be reviewed and
promoted into the curated eval set.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from news_dashboard.ai_feedback.models import SubjectType
from news_dashboard.db import connect, init_db, row_to_dict

logger = logging.getLogger(__name__)


def _upsert_sql(article_id: int | None) -> str:
    # Two different partial unique indexes back this table (see db.py) depending
    # on whether article_id is NULL, so the ON CONFLICT target must match.
    if article_id is None:
        conflict = "(user_id, subject_type, subject_id) WHERE article_id IS NULL"
    else:
        conflict = "(user_id, subject_type, subject_id, article_id) WHERE article_id IS NOT NULL"
    return f"""
        INSERT INTO ai_feedback (user_id, subject_type, subject_id, article_id, verdict, comment)
        VALUES (%(user_id)s, %(subject_type)s, %(subject_id)s, %(article_id)s,
                %(verdict)s, %(comment)s)
        ON CONFLICT {conflict}
        DO UPDATE SET verdict = EXCLUDED.verdict, comment = EXCLUDED.comment,
                       updated_at = NOW()
        RETURNING id, user_id, subject_type, subject_id, article_id, verdict, comment, created_at
    """


def record_feedback(  # noqa: PLR0913
    user_id: int,
    subject_type: SubjectType,
    subject_id: int,
    verdict: int,
    *,
    article_id: int | None = None,
    comment: str | None = None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Record or replace the user's verdict; returns the saved row.

    Also attaches the verdict as a Langfuse score to the briefing's generation
    trace when one was captured and Langfuse is configured; a no-op otherwise.
    """
    init_db(db_path, database_url=database_url)
    params = {
        "user_id": user_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "article_id": article_id,
        "verdict": verdict,
        "comment": comment,
    }
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(_upsert_sql(article_id), params).fetchone()
    saved = dict(row_to_dict(row))

    if subject_type == "briefing":
        _score_briefing_trace(
            subject_id, verdict, comment, db_path=db_path, database_url=database_url
        )
    elif subject_type == "lesson":
        _seed_lesson_eval_example(
            subject_id,
            user_id,
            verdict,
            comment,
            db_path=db_path,
            database_url=database_url,
        )
    return saved


def delete_feedback(
    user_id: int,
    subject_type: SubjectType,
    subject_id: int,
    *,
    article_id: int | None = None,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> bool:
    """Retract a previously recorded verdict. Returns whether a row was deleted."""
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        if article_id is None:
            result = conn.execute(
                "DELETE FROM ai_feedback WHERE user_id = %s AND subject_type = %s"
                " AND subject_id = %s AND article_id IS NULL",
                (user_id, subject_type, subject_id),
            )
        else:
            result = conn.execute(
                "DELETE FROM ai_feedback WHERE user_id = %s AND subject_type = %s"
                " AND subject_id = %s AND article_id = %s",
                (user_id, subject_type, subject_id, article_id),
            )
        return bool(result.rowcount > 0)


def get_feedback_map(
    user_id: int,
    subject_type: SubjectType,
    subject_ids: list[int],
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, int]:
    """Return ``{"<subject_id>:<article_id or ''>": verdict}`` for the given subjects."""
    if not subject_ids:
        return {}
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            "SELECT subject_id, article_id, verdict FROM ai_feedback"
            " WHERE user_id = %s AND subject_type = %s AND subject_id = ANY(%s)",
            (user_id, subject_type, subject_ids),
        ).fetchall()
    result: dict[str, int] = {}
    for row in rows:
        d = row_to_dict(row)
        key = f"{d['subject_id']}:{d['article_id'] if d['article_id'] is not None else ''}"
        result[key] = int(d["verdict"])
    return result


def _score_briefing_trace(
    briefing_id: int,
    verdict: int,
    comment: str | None,
    *,
    db_path: Path | str | None,
    database_url: str | None,
) -> None:
    from news_dashboard.ai_client import create_score

    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            "SELECT trace_id FROM briefings WHERE id = %s",
            (briefing_id,),
        ).fetchone()
    trace_id = row_to_dict(row).get("trace_id") if row else None
    if not trace_id:
        return
    create_score(
        trace_id,
        name="user-thumbs",
        value=verdict,
        data_type="NUMERIC",
        comment=comment,
    )


def _seed_lesson_eval_example(
    lesson_id: int,
    user_id: int,
    verdict: int,
    comment: str | None,
    *,
    db_path: Path | str | None,
    database_url: str | None,
) -> None:
    """Capture lesson helpfulness feedback as a candidate eval example.

    Stores the lesson's own structured detail as ``input`` so a human can
    later review and promote real user feedback into the curated
    lesson-synthesis eval fixtures (see ``news_dashboard.learn_from_link.evals``).
    Best-effort: a failure here never blocks recording the feedback itself.
    """
    try:
        with connect(db_path, database_url=database_url) as conn:
            lesson_row = conn.execute(
                "SELECT title, original_url, lesson_detail FROM lessons WHERE id = %s",
                (lesson_id,),
            ).fetchone()
            if lesson_row is None:
                return
            lesson = row_to_dict(lesson_row)
            conn.execute(
                """
                INSERT INTO ai_eval_examples
                  (feature, input, expected_properties, feedback_helpful, created_by_user_id)
                VALUES ('lesson-feedback', %s::jsonb, %s::jsonb, %s, %s)
                """,
                (
                    json.dumps(
                        {
                            "lesson_id": lesson_id,
                            "title": lesson.get("title"),
                            "original_url": lesson.get("original_url"),
                            "lesson_detail": lesson.get("lesson_detail"),
                        }
                    ),
                    json.dumps({"feedback_helpful": verdict == 1, "comment": comment}),
                    verdict == 1,
                    user_id,
                ),
            )
    except Exception:
        logger.exception("Failed to seed lesson eval example for lesson %d", lesson_id)
