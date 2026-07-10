"""Tests for generating podcast audio from a completed lesson."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_admin, require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.learn_from_link import service
from news_dashboard.main import app


def _make_user(database_url: str, username: str = "alice") -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row["id"])


@contextmanager
def _api_client(user_id: int, username: str = "alice") -> Generator[TestClient]:
    fake_user = {"id": user_id, "username": username, "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user
    app.dependency_overrides[require_admin] = lambda: fake_user
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


@pytest.fixture(autouse=True)
def _lesson_extraction_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service,
        "fetch_url_metadata",
        lambda url: {
            "title": f"Title for {url}",
            "site_name": "Example Source",
            "author": "Example Author",
            "published_at": "2026-07-09",
        },
        raising=False,
    )
    monkeypatch.setattr(
        service,
        "extract_body",
        lambda url: (f"Body for {url}. It has enough detail to be a lesson.", "ok"),
        raising=False,
    )


def _completed_lesson(pg_clean: str, user_id: int) -> dict[str, Any]:
    return service.create_lesson(user_id, "https://example.com/story", database_url=pg_clean)


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


# ── service.generate_lesson_podcast ───────────────────────────────────────────


def test_generate_lesson_podcast_raises_not_found(pg_clean: str) -> None:
    with pytest.raises(service.LessonNotFoundError):
        service.generate_lesson_podcast(999, 1, database_url=pg_clean)


def test_generate_lesson_podcast_raises_not_ready_when_lesson_pending(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(
        user_id, "https://example.com/story", database_url=pg_clean, extract=False
    )

    with pytest.raises(service.LessonNotReadyError):
        service.generate_lesson_podcast(int(lesson["id"]), user_id, database_url=pg_clean)


def test_generate_lesson_podcast_raises_not_configured_and_persists_failure(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(service.LessonPodcastNotConfiguredError):
        service.generate_lesson_podcast(int(lesson["id"]), user_id, database_url=pg_clean)

    persisted = service.get_lesson(int(lesson["id"]), user_id, database_url=pg_clean)
    assert persisted is not None
    assert persisted["podcast_status"] == "failed"
    assert persisted["podcast_error"]


def test_generate_lesson_podcast_succeeds_and_persists_complete(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    mock_client = _mock_audio_client()
    with patch("openai.OpenAI", return_value=mock_client):
        result = service.generate_lesson_podcast(int(lesson["id"]), user_id, database_url=pg_clean)

    assert result["podcast_status"] == "complete"
    assert result["podcast_error"] is None
    mock_client.audio.speech.with_streaming_response.create.assert_called_once()
    call_kwargs = mock_client.audio.speech.with_streaming_response.create.call_args
    # Narration is built from the structured lesson detail fields.
    assert result["lesson_detail"]["gist"] in call_kwargs.kwargs["input"]
    assert result["lesson_detail"]["why_it_matters"] in call_kwargs.kwargs["input"]


def test_generate_lesson_podcast_is_user_scoped(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = _completed_lesson(pg_clean, alice)

    with pytest.raises(service.LessonNotFoundError):
        service.generate_lesson_podcast(int(lesson["id"]), bob, database_url=pg_clean)


# ── router endpoints ──────────────────────────────────────────────────────────


def test_generate_lesson_podcast_endpoint_returns_complete_lesson(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    mock_client = _mock_audio_client()
    with (
        patch("openai.OpenAI", return_value=mock_client),
        _api_client(user_id) as client,
    ):
        response = client.post(f"/api/learn/lessons/{lesson['id']}/podcast")

    assert response.status_code == 200
    body = response.json()
    assert body["podcast_status"] == "complete"


def test_generate_lesson_podcast_endpoint_404s_for_missing_lesson(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.post("/api/learn/lessons/999999/podcast")

    assert response.status_code == 404


def test_generate_lesson_podcast_endpoint_409s_when_lesson_not_ready(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(
        user_id, "https://example.com/story", database_url=pg_clean, extract=False
    )

    with _api_client(user_id) as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/podcast")

    assert response.status_code == 409


def test_generate_lesson_podcast_endpoint_503s_when_not_configured(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with _api_client(user_id) as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/podcast")

    assert response.status_code == 503


def test_get_lesson_podcast_endpoint_404s_before_generation(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    with _api_client(user_id) as client:
        response = client.get(f"/api/learn/lessons/{lesson['id']}/podcast")

    assert response.status_code == 404


def test_get_lesson_podcast_endpoint_serves_generated_audio(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    mock_client = _mock_audio_client()
    with patch("openai.OpenAI", return_value=mock_client):
        service.generate_lesson_podcast(int(lesson["id"]), user_id, database_url=pg_clean)

    with _api_client(user_id) as client:
        response = client.get(f"/api/learn/lessons/{lesson['id']}/podcast")

    assert response.status_code == 200
    assert response.content == b"fake-mp3-data"


def test_get_lesson_podcast_endpoint_404s_for_other_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = _completed_lesson(pg_clean, alice)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    mock_client = _mock_audio_client()
    with patch("openai.OpenAI", return_value=mock_client):
        service.generate_lesson_podcast(int(lesson["id"]), alice, database_url=pg_clean)

    with _api_client(bob, username="bob") as client:
        response = client.get(f"/api/learn/lessons/{lesson['id']}/podcast")

    assert response.status_code == 404
