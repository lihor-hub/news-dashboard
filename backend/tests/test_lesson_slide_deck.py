"""Tests for generating a slide deck artifact from a completed lesson."""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace
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


def test_generate_slide_deck_content_uses_native_chat_prompt(
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
        "get_chat_model",
        lambda **_kwargs: RunnableLambda(
            lambda prompt: (
                chat_captured.update(messages=prompt.messages)
                or AIMessage(content=json.dumps(_VALID_SLIDE_DECK))
            )
        ),
    )

    lesson = {"id": 9, "title": "Lesson", "lesson_detail": {"gist": "A gist"}}
    service.generate_slide_deck_content(lesson, 7)

    assert captured["args"] == ("lesson-slide-deck",)
    assert captured["kwargs"]["prompt_type"] == "chat"
    assert captured["kwargs"]["fallback"] == [
        {"role": "system", "content": service._LESSON_SLIDE_DECK_SYSTEM_PROMPT},
        {"role": "user", "content": "{{lesson_content}}"},
    ]
    assert captured["kwargs"]["variables"] == {
        "lesson_content": service._build_slide_deck_prompt(lesson)
    }
    assert [message.content for message in chat_captured["messages"]] == ["managed"]


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


_VALID_SLIDE_DECK = {
    "slides": [
        {"title": f"Slide {i}", "bullets": [f"Bullet {i}.1", f"Bullet {i}.2"]} for i in range(1, 7)
    ]
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


def test_generate_slide_deck_content_preserves_json_settings_and_tracing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from langchain_core.callbacks import BaseCallbackHandler

    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("OPENAI_LESSON_CHAT_MODEL", "lesson-model")
    callback = BaseCallbackHandler()
    captured: dict[str, Any] = {}

    def invoke(_prompt: Any, config: Any) -> AIMessage:
        captured["config"] = config
        return AIMessage(content=json.dumps(_VALID_SLIDE_DECK))

    def factory(**kwargs: Any) -> Any:
        captured["factory"] = kwargs
        return RunnableLambda(invoke)

    monkeypatch.setattr("news_dashboard.ai_client.get_chat_model", factory)
    monkeypatch.setattr("news_dashboard.ai_client.langfuse_enabled", lambda: True)
    monkeypatch.setattr("langfuse.langchain.CallbackHandler", lambda: callback)
    with patch("langfuse.propagate_attributes") as attributes:
        result = service.generate_slide_deck_content(
            {"id": 99, "title": "T", "lesson_detail": {"gist": "G"}}, 42
        )

    assert len(result["slides"]) == 6
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
        tags=["lesson", "slide-deck"],
        trace_name="lesson-slide-deck",
        prompt=None,
    )


# ── service.generate_lesson_slide_deck ─────────────────────────────────────────


def test_generate_lesson_slide_deck_raises_not_found(pg_clean: str) -> None:
    with pytest.raises(service.LessonNotFoundError):
        service.generate_lesson_slide_deck(999, 1, database_url=pg_clean)


def test_generate_lesson_slide_deck_raises_not_ready_when_lesson_pending(
    pg_clean: str,
) -> None:
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(
        user_id, "https://example.com/story", database_url=pg_clean, extract=False
    )

    with pytest.raises(service.LessonNotReadyError):
        service.generate_lesson_slide_deck(int(lesson["id"]), user_id, database_url=pg_clean)


def test_generate_lesson_slide_deck_raises_not_configured_and_persists_failure(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(service.LessonSlideDeckNotConfiguredError):
        service.generate_lesson_slide_deck(int(lesson["id"]), user_id, database_url=pg_clean)

    persisted = service.get_lesson(int(lesson["id"]), user_id, database_url=pg_clean)
    assert persisted is not None
    assert persisted["slide_deck_status"] == "failed"
    assert persisted["slide_deck_error"]


def test_generate_lesson_slide_deck_persists_failure_on_malformed_response(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, _captured = _mock_chat_create('{"slides": []}')
    monkeypatch.setattr(ai_client_mod, "get_chat_model", fake)

    with pytest.raises(service.LessonSlideDeckGenerationError):
        service.generate_lesson_slide_deck(int(lesson["id"]), user_id, database_url=pg_clean)

    persisted = service.get_lesson(int(lesson["id"]), user_id, database_url=pg_clean)
    assert persisted is not None
    assert persisted["slide_deck_status"] == "failed"
    assert persisted["slide_deck_error"] == "Generated slide deck was malformed."


def test_generate_lesson_slide_deck_succeeds_and_persists_complete(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, captured = _mock_chat_create(json.dumps(_VALID_SLIDE_DECK))
    monkeypatch.setattr(ai_client_mod, "get_chat_model", fake)

    result = service.generate_lesson_slide_deck(int(lesson["id"]), user_id, database_url=pg_clean)

    assert result["slide_deck_status"] == "complete"
    assert result["slide_deck_error"] is None
    assert len(result["slide_deck"]["slides"]) == 6
    # Slide content is derived from the structured lesson detail fields.
    prompt = captured["messages"][-1]["content"]
    assert result["lesson_detail"]["gist"] in prompt
    assert result["lesson_detail"]["why_it_matters"] in prompt


def test_generate_lesson_slide_deck_returns_cached_deck_without_force(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, _captured = _mock_chat_create(json.dumps(_VALID_SLIDE_DECK))
    call_count = 0

    def _counting_fake(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        return fake(*args, **kwargs)

    monkeypatch.setattr(ai_client_mod, "get_chat_model", _counting_fake)

    service.generate_lesson_slide_deck(int(lesson["id"]), user_id, database_url=pg_clean)
    service.generate_lesson_slide_deck(int(lesson["id"]), user_id, database_url=pg_clean)

    assert call_count == 1


def test_generate_lesson_slide_deck_regenerates_with_force(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, _captured = _mock_chat_create(json.dumps(_VALID_SLIDE_DECK))
    call_count = 0

    def _counting_fake(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        return fake(*args, **kwargs)

    monkeypatch.setattr(ai_client_mod, "get_chat_model", _counting_fake)

    service.generate_lesson_slide_deck(int(lesson["id"]), user_id, database_url=pg_clean)
    service.generate_lesson_slide_deck(
        int(lesson["id"]), user_id, force=True, database_url=pg_clean
    )

    assert call_count == 2


def test_generate_lesson_slide_deck_is_user_scoped(pg_clean: str) -> None:
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = _completed_lesson(pg_clean, alice)

    with pytest.raises(service.LessonNotFoundError):
        service.generate_lesson_slide_deck(int(lesson["id"]), bob, database_url=pg_clean)


# ── router endpoint ─────────────────────────────────────────────────────────────


def test_generate_lesson_slide_deck_endpoint_returns_complete_lesson(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    import news_dashboard.ai_client as ai_client_mod

    fake, _captured = _mock_chat_create(json.dumps(_VALID_SLIDE_DECK))
    monkeypatch.setattr(ai_client_mod, "get_chat_model", fake)

    with _api_client(user_id) as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/slides")

    assert response.status_code == 200
    body = response.json()
    assert body["slide_deck_status"] == "complete"
    assert len(body["slide_deck"]["slides"]) == 6


def test_generate_lesson_slide_deck_endpoint_404s_for_missing_lesson(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.post("/api/learn/lessons/999999/slides")

    assert response.status_code == 404


def test_generate_lesson_slide_deck_endpoint_409s_when_lesson_not_ready(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(
        user_id, "https://example.com/story", database_url=pg_clean, extract=False
    )

    with _api_client(user_id) as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/slides")

    assert response.status_code == 409


def test_generate_lesson_slide_deck_endpoint_503s_when_not_configured(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = _completed_lesson(pg_clean, user_id)
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with _api_client(user_id) as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/slides")

    assert response.status_code == 503


def test_generate_lesson_slide_deck_endpoint_404s_for_other_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = _completed_lesson(pg_clean, alice)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    with _api_client(bob, username="bob") as client:
        response = client.post(f"/api/learn/lessons/{lesson['id']}/slides")

    assert response.status_code == 404
