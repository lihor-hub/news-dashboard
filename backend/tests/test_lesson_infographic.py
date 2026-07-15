"""Tests for generating an infographic artifact from a completed lesson."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from news_dashboard.auth import require_admin, require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.learn_from_link import service
from news_dashboard.main import app


def test_generate_infographic_content_uses_native_chat_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")
    import news_dashboard.ai_client as ai_client_mod

    managed = SimpleNamespace(
        messages=[{"role": "system", "content": "managed"}], langfuse_prompt=object()
    )
    captured: dict[str, Any] = {}
    chat_captured: dict[str, Any] = {}
    monkeypatch.setattr(
        ai_client_mod,
        "get_prompt",
        lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs) or managed,
    )
    monkeypatch.setattr(
        ai_client_mod,
        "chat_create",
        lambda *_args, **kwargs: (
            chat_captured.update(kwargs)
            or SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=json.dumps(_VALID_INFOGRAPHIC)))
                ]
            )
        ),
    )

    lesson = {"title": "Lesson", "lesson_detail": {"gist": "A gist"}}
    service.generate_infographic_content(lesson, 7)

    assert captured["args"] == ("lesson-infographic",)
    assert captured["kwargs"]["prompt_type"] == "chat"
    assert captured["kwargs"]["fallback"] == [
        {"role": "system", "content": service._LESSON_INFOGRAPHIC_SYSTEM_PROMPT},
        {"role": "user", "content": "{{lesson_content}}"},
    ]
    assert captured["kwargs"]["variables"] == {
        "lesson_content": service._build_infographic_prompt(lesson)
    }
    assert chat_captured["messages"] is managed.messages


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


_VALID_INFOGRAPHIC = {
    "title": "One-screen lesson map",
    "subtitle": "What to remember before acting on the source",
    "sections": [
        {"heading": "Core idea", "body": "The source argues for a concrete implementation."},
        {"heading": "Why it matters", "body": "Readers can decide whether to go deeper."},
        {"heading": "Question", "body": "What evidence supports the central claim?"},
    ],
    "footer": "Generated from structured lesson fields.",
}


def _mock_chat_create(content: str) -> Any:
    captured: dict[str, Any] = {}

    def _fake(**_kwargs: Any) -> Any:
        def _invoke(prompt: Any, **_kwargs: Any) -> AIMessage:
            captured["messages"] = [
                {"role": message.type, "content": message.content} for message in prompt.messages
            ]
            return AIMessage(content=content)

        return RunnableLambda(_invoke)

    return _fake, captured


def test_generate_infographic_content_preserves_json_settings_and_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.callbacks import BaseCallbackHandler

    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("OPENAI_LESSON_CHAT_MODEL", "lesson-model")
    callback = BaseCallbackHandler()
    captured: dict[str, Any] = {}

    def invoke(_prompt: Any, config: Any) -> AIMessage:
        captured["config"] = config
        return AIMessage(content=json.dumps(_VALID_INFOGRAPHIC))

    def factory(**kwargs: Any) -> Any:
        captured["factory"] = kwargs
        return RunnableLambda(invoke)

    monkeypatch.setattr("news_dashboard.ai_client.get_chat_model", factory)
    monkeypatch.setattr("news_dashboard.ai_client.langfuse_enabled", lambda: True)
    monkeypatch.setattr("langfuse.langchain.CallbackHandler", lambda: callback)
    with patch("langfuse.propagate_attributes") as attributes:
        result = service.generate_infographic_content(
            {"id": 99, "title": "T", "lesson_detail": {"gist": "G"}}, 42
        )

    assert len(result["sections"]) == 3
    assert captured["factory"] == {
        "api_key": "fake-key",
        "base_url": None,
        "model": "lesson-model",
        "response_format": {"type": "json_object"},
    }
    assert callback in captured["config"]["callbacks"].handlers
    attributes.assert_called_once_with(
        user_id="42",
        session_id="lesson:42:99",
        tags=["lesson", "infographic"],
        trace_name="lesson-infographic",
    )


def test_generate_lesson_infographic_raises_not_found(pg_clean: str) -> None:
    with pytest.raises(service.LessonNotFoundError):
        service.generate_lesson_infographic(999, 1, database_url=pg_clean)


def test_generate_lesson_infographic_raises_not_ready_when_lesson_pending(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(
        user_id, "https://example.com/story", database_url=pg_clean, extract=False
    )

    with pytest.raises(service.LessonNotReadyError):
        service.generate_lesson_infographic(int(lesson["id"]), user_id, database_url=pg_clean)


def test_generate_lesson_infographic_raises_not_configured_and_persists_failure(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(service.LessonInfographicNotConfiguredError):
        service.generate_lesson_infographic(int(lesson["id"]), user_id, database_url=pg_clean)

    persisted = service.get_lesson(int(lesson["id"]), user_id, database_url=pg_clean)
    assert persisted is not None
    assert persisted["infographic_status"] == "failed"
    assert persisted["infographic_error"]


def test_generate_lesson_infographic_persists_failure_on_malformed_response(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, _captured = _mock_chat_create('{"sections": []}')
    monkeypatch.setattr(ai_client_mod, "get_chat_model", fake)

    with pytest.raises(service.LessonInfographicGenerationError):
        service.generate_lesson_infographic(int(lesson["id"]), user_id, database_url=pg_clean)

    persisted = service.get_lesson(int(lesson["id"]), user_id, database_url=pg_clean)
    assert persisted is not None
    assert persisted["infographic_status"] == "failed"
    assert persisted["infographic_error"] == "Generated infographic was malformed."


def test_generate_lesson_infographic_succeeds_and_persists_complete(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, captured = _mock_chat_create(json.dumps(_VALID_INFOGRAPHIC))
    monkeypatch.setattr(ai_client_mod, "get_chat_model", fake)

    result = service.generate_lesson_infographic(int(lesson["id"]), user_id, database_url=pg_clean)

    assert result["infographic_status"] == "complete"
    assert result["infographic_error"] is None
    assert len(result["infographic"]["sections"]) == 3
    prompt = captured["messages"][-1]["content"]
    assert result["lesson_detail"]["gist"] in prompt
    assert result["lesson_detail"]["why_it_matters"] in prompt


def test_generate_lesson_infographic_returns_cached_artifact_without_force(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, _captured = _mock_chat_create(json.dumps(_VALID_INFOGRAPHIC))
    call_count = 0

    def _counting_fake(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        return fake(*args, **kwargs)

    monkeypatch.setattr(ai_client_mod, "get_chat_model", _counting_fake)

    service.generate_lesson_infographic(int(lesson["id"]), user_id, database_url=pg_clean)
    service.generate_lesson_infographic(int(lesson["id"]), user_id, database_url=pg_clean)

    assert call_count == 1


def test_generate_lesson_infographic_regenerates_with_force(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, _captured = _mock_chat_create(json.dumps(_VALID_INFOGRAPHIC))
    call_count = 0

    def _counting_fake(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        return fake(*args, **kwargs)

    monkeypatch.setattr(ai_client_mod, "get_chat_model", _counting_fake)

    service.generate_lesson_infographic(int(lesson["id"]), user_id, database_url=pg_clean)
    service.generate_lesson_infographic(
        int(lesson["id"]), user_id, force=True, database_url=pg_clean
    )

    assert call_count == 2


def test_generate_lesson_infographic_is_user_scoped(pg_clean: str) -> None:
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = _completed_lesson(pg_clean, alice)

    with pytest.raises(service.LessonNotFoundError):
        service.generate_lesson_infographic(int(lesson["id"]), bob, database_url=pg_clean)


def test_generate_lesson_infographic_endpoint_returns_complete_lesson(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, _captured = _mock_chat_create(json.dumps(_VALID_INFOGRAPHIC))
    monkeypatch.setattr(ai_client_mod, "get_chat_model", fake)

    with _api_client(user_id) as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/infographic")

    assert response.status_code == 200
    body = response.json()
    assert body["infographic_status"] == "complete"
    assert len(body["infographic"]["sections"]) == 3


def test_generate_lesson_infographic_endpoint_404s_for_missing_lesson(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.post("/api/learn/lessons/999999/infographic")

    assert response.status_code == 404


def test_generate_lesson_infographic_endpoint_409s_when_lesson_not_ready(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(
        user_id, "https://example.com/story", database_url=pg_clean, extract=False
    )

    with _api_client(user_id) as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/infographic")

    assert response.status_code == 409


def test_generate_lesson_infographic_endpoint_503s_when_not_configured(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with _api_client(user_id) as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/infographic")

    assert response.status_code == 503


def test_generate_lesson_infographic_endpoint_404s_for_other_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = _completed_lesson(pg_clean, alice)

    with _api_client(bob, username="bob") as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/infographic")

    assert response.status_code == 404
