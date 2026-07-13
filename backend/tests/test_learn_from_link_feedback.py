"""Tests for lesson helpfulness feedback via the generic ai_feedback module (#1131)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from news_dashboard.ai_feedback import service
from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.main import app


def _make_user(database_url: str, username: str = "alice") -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _seed_lesson(database_url: str, *, user_id: int, title: str = "A Lesson") -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO lessons(user_id, original_url, normalized_url, title,
                                 generation_status, lesson_detail)
            VALUES (%s, %s, %s, %s, 'complete', %s::jsonb)
            RETURNING id
            """,
            (
                user_id,
                "https://example.com/a",
                "https://example.com/a",
                title,
                '{"gist": "A grounded gist."}',
            ),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _client_for(user_id: int) -> TestClient:
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": "alice",
        "email": None,
        "is_admin": False,
    }
    return TestClient(app, raise_server_exceptions=True)


def test_record_lesson_feedback_seeds_eval_example(pg_clean: str) -> None:
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson_id = _seed_lesson(pg_clean, user_id=user_id)

    saved = service.record_feedback(
        user_id, "lesson", lesson_id, 1, comment="Very useful", database_url=pg_clean
    )

    assert saved["verdict"] == 1
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT * FROM ai_eval_examples WHERE feature = 'lesson-feedback'"
            " AND input->>'lesson_id' = %s",
            (str(lesson_id),),
        ).fetchone()
    assert row is not None
    assert row["feedback_helpful"] is True
    assert row["created_by_user_id"] == user_id
    assert row["expected_properties"]["comment"] == "Very useful"


def test_record_lesson_feedback_with_none_comment_seeds_eval_example(pg_clean: str) -> None:
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson_id = _seed_lesson(pg_clean, user_id=user_id)

    saved = service.record_feedback(
        user_id, "lesson", lesson_id, 1, comment=None, database_url=pg_clean
    )

    assert saved["verdict"] == 1
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT * FROM ai_eval_examples WHERE feature = 'lesson-feedback'"
            " AND input->>'lesson_id' = %s",
            (str(lesson_id),),
        ).fetchone()
    assert row is not None
    assert row["feedback_helpful"] is True
    assert "comment" in row["expected_properties"]
    assert row["expected_properties"]["comment"] is None


def test_record_negative_lesson_feedback_seeds_unhelpful_eval_example(pg_clean: str) -> None:
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson_id = _seed_lesson(pg_clean, user_id=user_id)

    service.record_feedback(user_id, "lesson", lesson_id, -1, database_url=pg_clean)

    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT feedback_helpful FROM ai_eval_examples WHERE feature = 'lesson-feedback'"
            " AND input->>'lesson_id' = %s",
            (str(lesson_id),),
        ).fetchone()
    assert row["feedback_helpful"] is False


def test_record_lesson_feedback_for_missing_lesson_does_not_raise(pg_clean: str) -> None:
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    saved = service.record_feedback(user_id, "lesson", 999999, 1, database_url=pg_clean)

    assert saved["verdict"] == 1
    with connect(database_url=pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_eval_examples WHERE feature = 'lesson-feedback'"
        ).fetchone()["count"]
    assert count == 0


def test_post_lesson_feedback_endpoint(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson_id = _seed_lesson(pg_clean, user_id=user_id)

    try:
        with _client_for(user_id) as client:
            response = client.post(
                "/api/ai-feedback",
                json={"subject_type": "lesson", "subject_id": lesson_id, "verdict": 1},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    assert response.json()["verdict"] == 1
