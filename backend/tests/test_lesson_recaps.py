"""Tests for weekly learning recap assembly, persistence, and podcast audio."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.lesson_recaps import service
from news_dashboard.main import app

pytestmark = pytest.mark.postgres


def _setup_db(monkeypatch: Any, pg_url: str) -> str:
    monkeypatch.setenv("DATABASE_URL", pg_url)
    init_db(database_url=pg_url)
    return pg_url


def _make_user(db_path: str, username: str = "alice") -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _insert_lesson(
    db_path: str,
    user_id: int,
    *,
    url: str,
    title: str,
    generation_status: str = "complete",
    lesson_detail: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> int:
    with connect(db_path) as conn:
        row = conn.execute(
            """
            INSERT INTO lessons(
              user_id, original_url, normalized_url, title, source_name,
              generation_status, lesson_detail, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                url,
                url,
                title,
                "Example Source",
                generation_status,
                json.dumps(lesson_detail) if lesson_detail is not None else None,
                created_at or datetime.now(timezone.utc),
                created_at or datetime.now(timezone.utc),
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


def _detail(concepts: list[str] | None = None, verdict: str = "read") -> dict[str, Any]:
    return {
        "gist": "A short summary.",
        "explanation": "A longer explanation.",
        "key_claims": ["Claim one"],
        "prerequisite_concepts": concepts or [],
        "why_it_matters": "It matters because...",
        "read_worthiness": {"verdict": verdict, "rationale": "Solid source."},
        "who_should_read": [],
        "questions_to_keep_in_mind": [],
        "citations": [],
    }


# ── assemble_weekly_lesson_recap ──────────────────────────────────────────────


def test_assemble_weekly_lesson_recap_empty_week_returns_zeroed_recap(
    monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    now = datetime.now(timezone.utc)

    recap = service.assemble_weekly_lesson_recap(user_id, now=now, database_url=db_path)

    assert recap["lessons_touched"] == 0
    assert recap["lessons_completed"] == 0
    assert recap["key_concepts"] == []
    assert recap["repeated_themes"] == []
    assert recap["unfinished_lessons"] == []
    assert recap["notable_articles"] == []


def test_assemble_weekly_lesson_recap_counts_within_window(monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=30)

    _insert_lesson(
        db_path,
        user_id,
        url="https://example.com/a",
        title="Lesson A",
        lesson_detail=_detail(["gradient descent", "backprop"]),
        created_at=now,
    )
    # Outside the 7-day window: must not be counted.
    _insert_lesson(
        db_path,
        user_id,
        url="https://example.com/old",
        title="Old Lesson",
        lesson_detail=_detail(["gradient descent"]),
        created_at=stale,
    )

    recap = service.assemble_weekly_lesson_recap(user_id, now=now, database_url=db_path)

    assert recap["lessons_touched"] == 1
    assert recap["lessons_completed"] == 1


def test_assemble_weekly_lesson_recap_key_concepts_and_themes(
    monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    now = datetime.now(timezone.utc)

    _insert_lesson(
        db_path,
        user_id,
        url="https://example.com/a",
        title="Lesson A",
        lesson_detail=_detail(["gradient descent", "backprop"]),
        created_at=now,
    )
    _insert_lesson(
        db_path,
        user_id,
        url="https://example.com/b",
        title="Lesson B",
        lesson_detail=_detail(["gradient descent"]),
        created_at=now,
    )

    recap = service.assemble_weekly_lesson_recap(user_id, now=now, database_url=db_path)

    concepts = {entry["concept"]: entry["count"] for entry in recap["key_concepts"]}
    assert concepts["gradient descent"] == 2
    assert concepts["backprop"] == 1
    themes = {entry["concept"] for entry in recap["repeated_themes"]}
    assert themes == {"gradient descent"}


def test_assemble_weekly_lesson_recap_unfinished_and_notable(
    monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    now = datetime.now(timezone.utc)

    _insert_lesson(
        db_path,
        user_id,
        url="https://example.com/pending",
        title="Still Pending",
        generation_status="pending",
        lesson_detail=None,
        created_at=now,
    )
    _insert_lesson(
        db_path,
        user_id,
        url="https://example.com/skip",
        title="Skip This",
        lesson_detail=_detail(verdict="skip"),
        created_at=now,
    )
    _insert_lesson(
        db_path,
        user_id,
        url="https://example.com/study",
        title="Study This",
        lesson_detail=_detail(verdict="study"),
        created_at=now,
    )

    recap = service.assemble_weekly_lesson_recap(user_id, now=now, database_url=db_path)

    assert len(recap["unfinished_lessons"]) == 1
    assert recap["unfinished_lessons"][0]["title"] == "Still Pending"
    assert len(recap["notable_articles"]) == 1
    assert recap["notable_articles"][0]["title"] == "Study This"


# ── save / list / get ─────────────────────────────────────────────────────────


def test_save_and_list_lesson_recaps_upserts_by_week(monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    recap = {
        "week_start": "2026-06-22",
        "week_end": "2026-06-29",
        "generated_at": "2026-06-29T00:00:00+00:00",
        "lessons_touched": 2,
        "lessons_completed": 2,
        "key_concepts": [],
        "repeated_themes": [],
        "unfinished_lessons": [],
        "notable_articles": [],
    }

    saved = service.save_weekly_lesson_recap(
        user_id, recap, "Great learning week!", database_url=db_path
    )
    assert saved["narrative"] == "Great learning week!"
    assert saved["data"]["lessons_completed"] == 2

    updated = dict(recap, lessons_completed=5)
    service.save_weekly_lesson_recap(user_id, updated, "Even better!", database_url=db_path)

    recaps = service.list_lesson_recaps(user_id, database_url=db_path)
    assert len(recaps) == 1
    assert recaps[0]["data"]["lessons_completed"] == 5
    assert recaps[0]["narrative"] == "Even better!"


def test_get_latest_lesson_recap_returns_none_when_empty(monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)

    assert service.get_latest_lesson_recap(user_id, database_url=db_path) is None


# ── router endpoints ──────────────────────────────────────────────────────────


def test_lesson_recaps_endpoint_returns_saved_history(monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    recap = {
        "week_start": "2026-06-22",
        "week_end": "2026-06-29",
        "generated_at": "2026-06-29T00:00:00+00:00",
        "lessons_touched": 3,
        "lessons_completed": 3,
        "key_concepts": [],
        "repeated_themes": [],
        "unfinished_lessons": [],
        "notable_articles": [],
    }
    service.save_weekly_lesson_recap(user_id, recap, "Nice learning week", database_url=db_path)

    try:
        with _client_for(user_id) as client:
            list_response = client.get("/api/lesson-recaps")
            latest_response = client.get("/api/lesson-recaps/latest")
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["data"]["lessons_completed"] == 3

    assert latest_response.status_code == 200
    assert latest_response.json()["narrative"] == "Nice learning week"


def test_lesson_recaps_latest_endpoint_404_when_none(monkeypatch: Any, pg_clean: str) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)

    try:
        with _client_for(user_id) as client:
            response = client.get("/api/lesson-recaps/latest")
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 404


def test_generate_lesson_recap_endpoint_assembles_and_persists(
    monkeypatch: Any, pg_clean: str
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    _insert_lesson(
        db_path,
        user_id,
        url="https://example.com/a",
        title="Lesson A",
        lesson_detail=_detail(["gradient descent"]),
    )

    with patch("news_dashboard.ai_client.free_llm_config", return_value=("", None)):
        try:
            with _client_for(user_id) as client:
                response = client.post("/api/lesson-recaps/generate")
        finally:
            app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["lessons_completed"] == 1
    assert body["narrative"]


# ── podcast audio ──────────────────────────────────────────────────────────────


@contextmanager
def _api_client(user_id: int) -> Generator[TestClient]:
    fake_user = {"id": user_id, "username": "alice", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    finally:
        app.dependency_overrides.pop(require_auth, None)


def _mock_audio_client() -> MagicMock:
    mock_response = MagicMock()

    def fake_stream(path: Path) -> None:
        path.write_bytes(b"fake-mp3-data")

    mock_response.stream_to_file.side_effect = fake_stream
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.audio.speech.with_streaming_response.create.return_value = mock_response
    return mock_client


def _saved_recap(db_path: str, user_id: int) -> dict[str, Any]:
    recap = {
        "week_start": "2026-06-22",
        "week_end": "2026-06-29",
        "generated_at": "2026-06-29T00:00:00+00:00",
        "lessons_touched": 1,
        "lessons_completed": 1,
        "key_concepts": [{"concept": "gradient descent", "count": 1}],
        "repeated_themes": [],
        "unfinished_lessons": [],
        "notable_articles": [{"id": 1, "title": "Backprop Explained", "source_name": "Example"}],
    }
    return service.save_weekly_lesson_recap(
        user_id, recap, "You completed 1 lesson this week.", database_url=db_path
    )


def test_generate_lesson_recap_podcast_raises_not_found(pg_clean: str) -> None:
    with pytest.raises(service.LessonRecapNotFoundError):
        service.generate_lesson_recap_podcast(999, 1, database_url=pg_clean)


def test_generate_lesson_recap_podcast_raises_not_configured_and_persists_failure(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str, tmp_path: Path
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    recap = _saved_recap(db_path, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(service.LessonRecapPodcastNotConfiguredError):
        service.generate_lesson_recap_podcast(int(recap["id"]), user_id, database_url=db_path)

    persisted = service.get_lesson_recap(int(recap["id"]), user_id, database_url=db_path)
    assert persisted is not None
    assert persisted["podcast_status"] == "failed"
    assert persisted["podcast_error"]


def test_generate_lesson_recap_podcast_succeeds_and_persists_complete(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str, tmp_path: Path
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    recap = _saved_recap(db_path, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    mock_client = _mock_audio_client()
    with patch("openai.OpenAI", return_value=mock_client):
        result = service.generate_lesson_recap_podcast(
            int(recap["id"]), user_id, database_url=db_path
        )

    assert result["podcast_status"] == "complete"
    assert result["podcast_error"] is None
    mock_client.audio.speech.with_streaming_response.create.assert_called_once()


def test_generate_lesson_recap_podcast_endpoint_returns_complete(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str, tmp_path: Path
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    recap = _saved_recap(db_path, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    mock_client = _mock_audio_client()
    with (
        patch("openai.OpenAI", return_value=mock_client),
        _api_client(user_id) as client,
    ):
        response = client.post(f"/api/lesson-recaps/{recap['id']}/podcast")

    assert response.status_code == 200
    assert response.json()["podcast_status"] == "complete"


def test_generate_lesson_recap_podcast_endpoint_404s_for_missing_recap(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)

    with _api_client(user_id) as client:
        response = client.post("/api/lesson-recaps/999999/podcast")

    assert response.status_code == 404


def test_generate_lesson_recap_podcast_endpoint_503s_when_not_configured(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str, tmp_path: Path
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    recap = _saved_recap(db_path, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with _api_client(user_id) as client:
        response = client.post(f"/api/lesson-recaps/{recap['id']}/podcast")

    assert response.status_code == 503


def test_get_lesson_recap_podcast_endpoint_404s_before_generation(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str, tmp_path: Path
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    recap = _saved_recap(db_path, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    with _api_client(user_id) as client:
        response = client.get(f"/api/lesson-recaps/{recap['id']}/podcast")

    assert response.status_code == 404


def test_get_lesson_recap_podcast_endpoint_serves_generated_audio(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str, tmp_path: Path
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    user_id = _make_user(db_path)
    recap = _saved_recap(db_path, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    mock_client = _mock_audio_client()
    with patch("openai.OpenAI", return_value=mock_client):
        service.generate_lesson_recap_podcast(int(recap["id"]), user_id, database_url=db_path)

    with _api_client(user_id) as client:
        response = client.get(f"/api/lesson-recaps/{recap['id']}/podcast")

    assert response.status_code == 200
    assert response.content == b"fake-mp3-data"


def test_get_lesson_recap_podcast_endpoint_404s_for_other_user(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str, tmp_path: Path
) -> None:
    db_path = _setup_db(monkeypatch, pg_clean)
    alice = _make_user(db_path, "alice")
    bob = _make_user(db_path, "bob")
    recap = _saved_recap(db_path, alice)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    mock_client = _mock_audio_client()
    with patch("openai.OpenAI", return_value=mock_client):
        service.generate_lesson_recap_podcast(int(recap["id"]), alice, database_url=db_path)

    with _api_client(bob) as client:
        response = client.get(f"/api/lesson-recaps/{recap['id']}/podcast")

    assert response.status_code == 404
