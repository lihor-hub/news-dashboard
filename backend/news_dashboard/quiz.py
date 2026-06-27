"""Reading Goals and AI-generated retention quizzes.

Users set learning goals (description + keywords). The recommendation engine
gives a small boost to articles that match those keywords. Weekly, an LLM
generates 3 multiple-choice questions from articles the user marked done.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db

logger = logging.getLogger(__name__)

DEFAULT_QUIZ_MODEL = "gpt-4o-mini"
GOAL_ALIGNMENT_ADJUSTMENT = 4.0  # points added to recommendation score per matching goal
_MAX_ARTICLE_CHARS = 3_000
_QUIZ_PROMPT = (
    "You are a study-aid assistant. Based ONLY on the articles listed below, generate exactly 3 "
    "multiple-choice questions that test the reader's understanding of key facts or arguments. "
    "For each question provide:\n"
    "- question: the question text\n"
    "- options: a JSON array of exactly 4 answer strings\n"
    "- correct_index: 0-based index of the correct answer\n"
    "- explanation: one sentence explaining why that answer is correct, citing the article\n"
    "- article_id: the integer id of the article the question is drawn from\n\n"
    "Return ONLY a JSON array of 3 objects with those exact keys. No other text."
)


# ── Goal CRUD helpers ─────────────────────────────────────────────────────────


def create_goal(
    user_id: int,
    description: str,
    keywords: str = "",
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_goals (user_id, description, keywords)
            VALUES (%s, %s, %s)
            RETURNING id, user_id, description, keywords, created_at
            """,
            (user_id, description.strip(), keywords.strip()),
        ).fetchone()
    return dict(row)


def list_goals(
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            "SELECT id, user_id, description, keywords, created_at"
            " FROM user_goals WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_goal(
    goal_id: int,
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> bool:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        result = conn.execute(
            "DELETE FROM user_goals WHERE id = %s AND user_id = %s",
            (goal_id, user_id),
        )
        return bool(result.rowcount > 0)


# ── Goal alignment score adjustment ──────────────────────────────────────────


def goal_alignment_adjustment(
    article_title: str | None,
    article_category: str | None,
    article_tags: str | None,
    goals: list[dict[str, Any]],
) -> float:
    """Return a score boost when the article matches any active goal's keywords."""
    if not goals:
        return 0.0
    text = " ".join(filter(None, [article_title, article_category, article_tags])).lower()
    for goal in goals:
        keywords_raw = str(goal.get("keywords") or goal.get("description") or "")
        for kw in keywords_raw.lower().split():
            if kw and kw in text:
                return GOAL_ALIGNMENT_ADJUSTMENT
    return 0.0


# ── Weekly quiz generation ────────────────────────────────────────────────────


def _quiz_ai_config() -> tuple[str, str | None, str]:
    api_key = os.getenv("OPENAI_QUIZ_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        msg = "OPENAI_API_KEY is not configured"
        raise RuntimeError(msg)
    base_url = os.getenv("OPENAI_QUIZ_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    model = os.getenv("OPENAI_QUIZ_MODEL", DEFAULT_QUIZ_MODEL)
    return api_key, base_url, model


def _build_article_blurb(article: dict[str, Any]) -> str:
    title = str(article.get("title") or "")
    body = str(article.get("body") or article.get("summary") or "")
    blurb = f"Article id={article['id']}\nTitle: {title}\n{body}"
    return blurb[:_MAX_ARTICLE_CHARS]


def _parse_questions(response_text: str) -> list[dict[str, Any]]:
    """Extract the JSON array from the LLM response, tolerating markdown fences."""
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            return []
        result: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "")
            options = item.get("options")
            correct_index = item.get("correct_index")
            if not question or not isinstance(options, list) or correct_index is None:
                continue
            result.append(
                {
                    "question": question,
                    "options": [str(o) for o in options],
                    "correct_index": int(correct_index),
                    "explanation": str(item.get("explanation") or ""),
                    "article_id": item.get("article_id"),
                }
            )
        return result
    except (json.JSONDecodeError, ValueError):
        return []


def generate_weekly_quiz(
    user_id: int,
    *,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Generate and persist a weekly quiz for the user.

    Queries articles marked `done` in the last 7 days that align with the
    user's active goals (or falls back to the most-recent reads). Calls an
    LLM to produce 3 MCQs and saves the result to `user_quizzes`.

    Returns the saved quiz row, or None when no eligible articles are found.
    """
    init_db(db_path, database_url=database_url)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    with connect(db_path, database_url=database_url) as conn:
        goals = conn.execute(
            "SELECT description, keywords FROM user_goals WHERE user_id = %s",
            (user_id,),
        ).fetchall()
        goal_list = [dict(g) for g in goals]

        # Build keyword filter for the SQL query when goals are present.
        articles: list[dict[str, Any]]
        if goal_list:
            keyword_terms: list[str] = []
            for g in goal_list:
                kw_str = g.get("keywords") or g.get("description") or ""
                keyword_terms.extend(kw_str.lower().split())
            if keyword_terms:
                ilike_clauses = " OR ".join(
                    "(LOWER(a.title) LIKE %s OR LOWER(a.category) LIKE %s)" for _ in keyword_terms
                )
                params: list[Any] = []
                for kw in keyword_terms:
                    params.extend([f"%{kw}%", f"%{kw}%"])
                params.extend([user_id, cutoff])
                rows = conn.execute(
                    f"""
                    SELECT a.id, a.title, a.body, a.summary, a.category
                    FROM articles a
                    JOIN user_article_state s ON s.article_id = a.id
                    WHERE ({ilike_clauses})
                      AND s.user_id = %s
                      AND s.state = 'done'
                      AND s.done_at >= %s
                    ORDER BY s.done_at DESC
                    LIMIT 10
                    """,
                    params,
                ).fetchall()
                articles = [dict(r) for r in rows]
            else:
                articles = []
        else:
            articles = []

        # Fall back to any recently-read articles when no goal matches.
        if not articles:
            rows = conn.execute(
                """
                SELECT a.id, a.title, a.body, a.summary, a.category
                FROM articles a
                JOIN user_article_state s ON s.article_id = a.id
                WHERE s.user_id = %s
                  AND s.state = 'done'
                  AND s.done_at >= %s
                ORDER BY s.done_at DESC
                LIMIT 10
                """,
                (user_id, cutoff),
            ).fetchall()
            articles = [dict(r) for r in rows]

    if not articles:
        logger.info("No eligible articles for quiz generation for user %s", user_id)
        return None

    api_key, base_url, model = _quiz_ai_config()
    blurbs = "\n\n---\n\n".join(_build_article_blurb(a) for a in articles[:5])
    messages = [{"role": "user", "content": f"{_QUIZ_PROMPT}\n\nArticles:\n{blurbs}"}]

    from news_dashboard.ai_client import chat_create, get_openai_client

    client = get_openai_client(api_key=api_key, base_url=base_url)
    logger.info("Generating weekly quiz for user %s from %d articles", user_id, len(articles))
    result = chat_create(
        client,
        name="weekly-quiz",
        tags=["quiz"],
        user_id=user_id,
        model=model,
        messages=messages,
        max_tokens=1024,
    )
    response_text = (result.choices[0].message.content or "").strip()
    questions = _parse_questions(response_text)
    if not questions:
        logger.warning("LLM returned no parseable questions for user %s", user_id)
        return None

    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_quizzes (user_id, questions)
            VALUES (%s, %s::jsonb)
            RETURNING id, user_id, created_at, questions, score
            """,
            (user_id, json.dumps(questions)),
        ).fetchone()
    quiz = dict(row)
    quiz["questions"] = questions
    return quiz


# ── Quiz retrieval and submission ─────────────────────────────────────────────


def get_latest_quiz(
    user_id: int,
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            "SELECT id, user_id, created_at, questions, score"
            " FROM user_quizzes WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return dict(row)


def submit_quiz(
    quiz_id: int,
    user_id: int,
    answers: list[int],
    db_path: Path | str | None = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            "SELECT id, user_id, questions, score FROM user_quizzes WHERE id = %s AND user_id = %s",
            (quiz_id, user_id),
        ).fetchone()
        if not row:
            msg = f"Quiz {quiz_id} not found for user {user_id}"
            raise ValueError(msg)
        quiz = dict(row)
        questions: list[dict[str, Any]] = quiz["questions"]

        correct = sum(
            1
            for i, q in enumerate(questions)
            if i < len(answers) and answers[i] == q.get("correct_index")
        )
        score = correct

        conn.execute(
            "UPDATE user_quizzes SET score = %s WHERE id = %s AND user_id = %s",
            (score, quiz_id, user_id),
        )

    return {
        "quiz_id": quiz_id,
        "score": score,
        "total": len(questions),
        "questions": [
            {**q, "your_answer": answers[i] if i < len(answers) else None}
            for i, q in enumerate(questions)
        ],
    }
