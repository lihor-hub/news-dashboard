"""Tests for Reading Goals and quiz builder."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.main import app
from news_dashboard.quizzes.service import (
    create_goal,
    delete_goal,
    generate_weekly_quiz,
    get_latest_quiz,
    get_quiz_candidate_articles,
    goal_alignment_adjustment,
    list_goals,
    list_quizzes,
    submit_quiz,
)


def _db_url(value: Path | str) -> str | None:
    text = str(value)
    if text.startswith(("postgres://", "postgresql://")):
        return text
    return None


def _seed(db_path: Path | str) -> tuple[int, int]:
    """Create one user, source, and article; return (user_id, article_id)."""
    database_url = _db_url(db_path)
    init_db(None if database_url else db_path, database_url=database_url)
    with connect(None if database_url else db_path, database_url=database_url) as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, is_admin)"
            " VALUES (1, 'reader', 'x', FALSE)"
        )
        conn.execute(
            "INSERT INTO sources(slug, name, url, category, kind)"
            " VALUES ('s1', 'Source One', 'https://s1.example', 'tech', 'rss')"
        )
        conn.execute(
            """
            INSERT INTO articles(id, url, canonical_url, title, source_slug,
                                 source_name, category, kind)
            VALUES (10, 'https://s1.example/a', 'https://s1.example/a',
                    'AI Transformer Deep Dive', 's1', 'Source One', 'tech', 'rss')
            """
        )
    return 1, 10


# ── goal_alignment_adjustment unit tests ────────────────────────────────────


def test_goal_alignment_no_goals() -> None:
    assert goal_alignment_adjustment("Any title", "tech", None, []) == 0.0


def test_goal_alignment_keyword_match() -> None:
    goals = [{"description": "AI research", "keywords": "transformer ai"}]
    score = goal_alignment_adjustment("Transformer architecture overview", "tech", None, goals)
    assert score > 0.0


def test_goal_alignment_description_fallback() -> None:
    goals = [{"description": "transformer architecture", "keywords": ""}]
    score = goal_alignment_adjustment("Transformer in production", "ml", None, goals)
    assert score > 0.0


def test_goal_alignment_no_match() -> None:
    goals = [{"description": "quantum computing", "keywords": "quantum qubit"}]
    score = goal_alignment_adjustment("Football highlights recap", "sports", None, goals)
    assert score == 0.0


# ── Goal CRUD tests ───────────────────────────────────────────────────────────


def test_create_and_list_goals(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _seed(db_path)

    goal = create_goal(1, "Learn AI policy", "regulation policy", db_path=db_path)
    assert goal["id"] is not None
    assert goal["description"] == "Learn AI policy"
    assert goal["keywords"] == "regulation policy"

    goals = list_goals(1, db_path=db_path)
    assert len(goals) == 1
    assert goals[0]["description"] == "Learn AI policy"


def test_delete_goal(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _seed(db_path)

    goal = create_goal(1, "Temporary goal", db_path=db_path)
    assert len(list_goals(1, db_path=db_path)) == 1

    deleted = delete_goal(goal["id"], 1, db_path=db_path)
    assert deleted is True
    assert list_goals(1, db_path=db_path) == []


def test_delete_goal_wrong_user(tmp_path: Path) -> None:
    db_path = tmp_path / "g.db"
    _seed(db_path)

    goal = create_goal(1, "My goal", db_path=db_path)
    deleted = delete_goal(goal["id"], 999, db_path=db_path)
    assert deleted is False


# ── Quiz builder unit tests ───────────────────────────────────────────────────


def test_parse_questions_valid_json() -> None:
    from news_dashboard.quizzes.service import _parse_questions

    raw = """[
      {
        "question": "What is a transformer?",
        "options": ["A robot", "An attention-based model", "A dataset", "A loss function"],
        "correct_index": 1,
        "explanation": "Transformers use self-attention.",
        "article_id": 10
      }
    ]"""
    questions = _parse_questions(raw)
    assert len(questions) == 1
    assert questions[0]["question"] == "What is a transformer?"
    assert questions[0]["correct_index"] == 1
    assert len(questions[0]["options"]) == 4


def test_parse_questions_markdown_fence() -> None:
    from news_dashboard.quizzes.service import _parse_questions

    raw = """```json
[{"question":"Q?","options":["A","B","C","D"],"correct_index":0,"explanation":"E","article_id":1}]
```"""
    questions = _parse_questions(raw)
    assert len(questions) == 1
    assert questions[0]["question"] == "Q?"


def test_parse_questions_invalid_json_returns_empty() -> None:
    from news_dashboard.quizzes.service import _parse_questions

    assert _parse_questions("not json at all") == []


def test_parse_questions_missing_required_fields() -> None:
    from news_dashboard.quizzes.service import _parse_questions

    raw = '[{"question": "Q?"}]'
    assert _parse_questions(raw) == []


# ── Quiz generation + submit integration tests ────────────────────────────────


def _seed_done_article(db_path: Path, user_id: int, article_id: int) -> None:
    done_at = datetime.now(timezone.utc) - timedelta(days=1)
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO user_article_state (user_id, article_id, state, done_at)
            VALUES (%s, %s, 'done', %s)
            ON CONFLICT (user_id, article_id) DO UPDATE SET state='done', done_at=%s
            """,
            (user_id, article_id, done_at, done_at),
        )


_MOCK_QUESTIONS: list[dict[str, Any]] = [
    {
        "question": "What does self-attention compute?",
        "options": ["Sums", "Dot products", "Convolutions", "Averages"],
        "correct_index": 1,
        "explanation": "Self-attention computes scaled dot products.",
        "article_id": 10,
    },
    {
        "question": "What is BERT?",
        "options": [
            "A transformer model",
            "A dataset",
            "A loss function",
            "An optimizer",
        ],
        "correct_index": 0,
        "explanation": "BERT is a bidirectional transformer.",
        "article_id": 10,
    },
    {
        "question": "What does GPT stand for?",
        "options": [
            "Generative Pre-trained Transformer",
            "General Purpose Tokenizer",
            "Gradient Path Tracker",
            "Graph Processing Toolkit",
        ],
        "correct_index": 0,
        "explanation": "GPT = Generative Pre-trained Transformer.",
        "article_id": 10,
    },
]


def test_generate_weekly_quiz_no_articles(tmp_path: Path) -> None:
    db_path = tmp_path / "q.db"
    _seed(db_path)
    # No done articles → should return None without calling LLM
    result = generate_weekly_quiz(1, db_path=db_path)
    assert result is None


def test_generate_weekly_quiz_with_articles(tmp_path: Path) -> None:
    db_path = tmp_path / "q.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(_MOCK_QUESTIONS)

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        patch("news_dashboard.ai_client.get_openai_client") as mock_client_factory,
        patch("news_dashboard.ai_client.chat_create", return_value=mock_response),
    ):
        mock_client_factory.return_value = MagicMock()
        quiz = generate_weekly_quiz(user_id, db_path=db_path)

    assert quiz is not None
    assert quiz["user_id"] == user_id
    assert len(quiz["questions"]) == 3
    assert quiz["score"] is None


def test_get_latest_quiz_empty(tmp_path: Path) -> None:
    db_path = tmp_path / "q.db"
    _seed(db_path)
    assert get_latest_quiz(1, db_path=db_path) is None


def _insert_quiz(
    db_path: Path | str,
    *,
    user_id: int,
    created_at: datetime,
    score: int | None = None,
    submitted_at: datetime | None = None,
) -> int:
    database_url = _db_url(db_path)
    with connect(None if database_url else db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_quizzes (user_id, created_at, questions, score, submitted_at)
            VALUES (%s, %s, %s::jsonb, %s, %s)
            RETURNING id
            """,
            (user_id, created_at, json.dumps(_MOCK_QUESTIONS), score, submitted_at),
        ).fetchone()
    return int(row["id"])


def test_list_quizzes_newest_first_with_metadata(pg_clean: str) -> None:
    _seed(pg_clean)
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 1, 8, tzinfo=timezone.utc)
    old_id = _insert_quiz(pg_clean, user_id=1, created_at=old)
    new_id = _insert_quiz(
        pg_clean,
        user_id=1,
        created_at=new,
        score=2,
        submitted_at=new + timedelta(minutes=5),
    )

    items = list_quizzes(1, database_url=pg_clean)

    assert [item["id"] for item in items] == [new_id, old_id]
    assert items[0]["score"] == 2
    assert items[0]["total"] == 3
    assert items[0]["completed"] is True
    assert items[0]["submitted_at"] is not None
    assert items[1]["completed"] is False


def test_list_quizzes_limits_and_offsets(pg_clean: str) -> None:
    _seed(pg_clean)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ids = [
        _insert_quiz(pg_clean, user_id=1, created_at=base + timedelta(days=days))
        for days in range(3)
    ]

    items = list_quizzes(1, limit=1, offset=1, database_url=pg_clean)

    assert [item["id"] for item in items] == [ids[1]]


def test_list_quizzes_is_user_scoped(pg_clean: str) -> None:
    _seed(pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash, is_admin)"
            " VALUES (2, 'other', 'x', FALSE)"
        )
    mine = _insert_quiz(
        pg_clean,
        user_id=1,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    _insert_quiz(
        pg_clean,
        user_id=2,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    items = list_quizzes(1, database_url=pg_clean)

    assert [item["id"] for item in items] == [mine]


def test_list_quizzes_endpoint_returns_current_user_history(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(pg_clean)
    _insert_quiz(
        pg_clean,
        user_id=1,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        score=3,
        submitted_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
    )
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    app.dependency_overrides[require_auth] = lambda: {"id": 1, "username": "reader"}
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            response = client.get("/api/quizzes")
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    assert response.json()["items"][0]["total"] == 3


def test_submit_quiz_scoring(tmp_path: Path) -> None:
    db_path = tmp_path / "q.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(_MOCK_QUESTIONS)

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        patch("news_dashboard.ai_client.get_openai_client") as mock_client_factory,
        patch("news_dashboard.ai_client.chat_create", return_value=mock_response),
    ):
        mock_client_factory.return_value = MagicMock()
        quiz = generate_weekly_quiz(user_id, db_path=db_path)

    assert quiz is not None
    # All correct answers: correct_index is 1, 0, 0
    correct_answers = [q["correct_index"] for q in _MOCK_QUESTIONS]
    result = submit_quiz(quiz["id"], user_id, correct_answers, db_path=db_path)

    assert result["score"] == 3
    assert result["total"] == 3


def test_submit_quiz_partial_score(tmp_path: Path) -> None:
    db_path = tmp_path / "q.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)

    import json

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(_MOCK_QUESTIONS)

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        patch("news_dashboard.ai_client.get_openai_client") as mock_client_factory,
        patch("news_dashboard.ai_client.chat_create", return_value=mock_response),
    ):
        mock_client_factory.return_value = MagicMock()
        quiz = generate_weekly_quiz(user_id, db_path=db_path)

    assert quiz is not None
    # First answer correct, rest wrong
    wrong_answers = [_MOCK_QUESTIONS[0]["correct_index"], 99, 99]
    result = submit_quiz(quiz["id"], user_id, wrong_answers, db_path=db_path)
    assert result["score"] == 1
    assert result["total"] == 3


def test_submit_quiz_not_found(tmp_path: Path) -> None:
    db_path = tmp_path / "q.db"
    _seed(db_path)
    with pytest.raises(ValueError, match="not found"):
        submit_quiz(9999, 1, [0, 0, 0], db_path=db_path)


def _generate_quiz_with_mock(user_id: int, db_path: Path) -> dict[str, Any]:
    import json

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(_MOCK_QUESTIONS)
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        patch("news_dashboard.ai_client.get_openai_client") as mock_client_factory,
        patch("news_dashboard.ai_client.chat_create", return_value=mock_response),
    ):
        mock_client_factory.return_value = MagicMock()
        quiz = generate_weekly_quiz(user_id, db_path=db_path)
    assert quiz is not None
    return quiz


def test_submit_quiz_persists_submitted_answers(tmp_path: Path) -> None:
    db_path = tmp_path / "q.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)
    quiz = _generate_quiz_with_mock(user_id, db_path)

    answers = [q["correct_index"] for q in _MOCK_QUESTIONS]
    submit_quiz(quiz["id"], user_id, answers, db_path=db_path)

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT submitted_answers, submitted_at FROM user_quizzes WHERE id = %s",
            (quiz["id"],),
        ).fetchone()

    assert row is not None
    assert row["submitted_at"] is not None
    assert row["submitted_answers"] is not None
    assert len(row["submitted_answers"]) == 3
    # Each question should have your_answer populated
    for i, q in enumerate(row["submitted_answers"]):
        assert q["your_answer"] == answers[i]


def test_get_latest_quiz_returns_completed_result_after_submit(tmp_path: Path) -> None:
    db_path = tmp_path / "q.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)
    quiz = _generate_quiz_with_mock(user_id, db_path)

    # Before submit: no completed_result
    latest = get_latest_quiz(user_id, db_path=db_path)
    assert latest is not None
    assert latest.get("completed_result") is None

    answers = [q["correct_index"] for q in _MOCK_QUESTIONS]
    submit_quiz(quiz["id"], user_id, answers, db_path=db_path)

    # After submit: completed_result is populated
    latest = get_latest_quiz(user_id, db_path=db_path)
    assert latest is not None
    cr = latest.get("completed_result")
    assert cr is not None
    assert cr["quiz_id"] == quiz["id"]
    assert cr["score"] == 3
    assert cr["total"] == 3
    assert len(cr["questions"]) == 3


def test_get_latest_quiz_unanswered_has_no_completed_result(tmp_path: Path) -> None:
    db_path = tmp_path / "q.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)
    _generate_quiz_with_mock(user_id, db_path)

    latest = get_latest_quiz(user_id, db_path=db_path)
    assert latest is not None
    assert latest.get("completed_result") is None


# ── get_quiz_candidate_articles tests ────────────────────────────────────────


def test_candidates_empty_when_no_done_articles(tmp_path: Path) -> None:
    db_path = tmp_path / "c.db"
    _seed(db_path)
    candidates = get_quiz_candidate_articles(1, db_path=db_path)
    assert candidates == []


def test_candidates_fallback_to_recent_done(tmp_path: Path) -> None:
    db_path = tmp_path / "c.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)

    candidates = get_quiz_candidate_articles(user_id, db_path=db_path)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["id"] == article_id
    assert c["title"] == "AI Transformer Deep Dive"
    assert c["goal_matched"] is False
    assert c["matched_keywords"] == []
    assert "body" not in c


def test_candidates_goal_matched(tmp_path: Path) -> None:
    db_path = tmp_path / "c.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)
    create_goal(user_id, "Deep learning", keywords="transformer ai", db_path=db_path)

    candidates = get_quiz_candidate_articles(user_id, db_path=db_path)
    assert len(candidates) == 1
    c = candidates[0]
    assert c["goal_matched"] is True
    assert "transformer" in c["matched_keywords"] or "ai" in c["matched_keywords"]


def test_candidates_user_isolation(tmp_path: Path) -> None:
    db_path = tmp_path / "c.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)

    # User 2 should see no candidates
    candidates = get_quiz_candidate_articles(999, db_path=db_path)
    assert candidates == []


def test_candidates_no_body_text(tmp_path: Path) -> None:
    db_path = tmp_path / "c.db"
    user_id, article_id = _seed(db_path)
    _seed_done_article(db_path, user_id, article_id)

    candidates = get_quiz_candidate_articles(user_id, db_path=db_path)
    for c in candidates:
        assert "body" not in c
        assert "summary" not in c
