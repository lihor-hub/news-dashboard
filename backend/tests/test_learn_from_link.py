from __future__ import annotations

import socket
from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_admin, require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.learn_from_link import service
from news_dashboard.main import app
from news_dashboard.url_safety import UnsafeUrlError


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
def _safe_url_validator(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.name == "test_create_lesson_endpoint_rejects_localhost_url":
        return

    def fake_validate(url: str) -> None:
        if not url.strip().lower().startswith(("http://", "https://")):
            message = f"unsafe url: {url}"
            raise UnsafeUrlError(message)

    monkeypatch.setattr(service, "validate_server_fetch_url", fake_validate)


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
        lambda url: (f"Body for {url}", "ok"),
        raising=False,
    )


def test_create_lesson_completes_with_extracted_content(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    monkeypatch.setattr(
        service,
        "fetch_url_metadata",
        lambda _url: {
            "title": "A careful article",
            "site_name": "Example Journal",
            "author": "Ada Writer",
            "published_at": "2026-07-09",
        },
        raising=False,
    )
    monkeypatch.setattr(
        service,
        "extract_body",
        lambda _url: ("Paragraph one.\n\nParagraph two.", "ok"),
        raising=False,
    )

    lesson = service.create_lesson(
        user_id,
        "https://Example.com/story?b=2&a=1",
        database_url=pg_clean,
    )

    assert lesson["user_id"] == user_id
    assert lesson["original_url"] == "https://Example.com/story?b=2&a=1"
    assert lesson["normalized_url"] == "https://example.com/story?a=1&b=2"
    assert lesson["generation_status"] == "complete"
    assert lesson["generation_error"] is None
    assert lesson["title"] == "A careful article"
    assert lesson["source_name"] == "Example Journal"
    assert lesson["author"] == "Ada Writer"
    assert lesson["published_at"] == "2026-07-09"
    assert lesson["source_content"] == "Paragraph one.\n\nParagraph two."
    assert lesson["lesson_detail"] == {
        "gist": "Paragraph one.",
        "explanation": "Paragraph one.\n\nParagraph two.",
        "key_claims": ["Paragraph one.", "Paragraph two."],
        "prerequisite_concepts": ["Context from Example Journal"],
        "why_it_matters": "It helps you decide whether A careful article deserves deeper reading.",
        "read_worthiness": {
            "verdict": "skim",
            "rationale": "Start with a skim: the source is short enough to inspect quickly.",
        },
        "who_should_read": ["Readers deciding whether to spend more time with this source."],
        "questions_to_keep_in_mind": [
            "What evidence does the source provide for its central claim?"
        ],
        "citations": [
            {
                "label": "1",
                "snippet": "Paragraph one.",
                "source": "A careful article",
            }
        ],
    }
    assert lesson["study_artifacts"] == {
        "comprehension_questions": [
            {
                "question": "What is the primary topic of the text?",
                "expected_answer": "The primary topic is: Paragraph one.",
            }
        ],
        "flashcards": [
            {
                "concept": "Core Claim",
                "claim": "Paragraph one.",
            }
        ],
        "quiz": [
            {
                "question": "Which of the following best summarizes the main point of the source?",
                "options": [
                    "Paragraph one.",
                    "A completely unrelated fact about the topic.",
                    "An incorrect assertion about the author.",
                    "A generic fallback option.",
                ],
                "correct_index": 0,
                "explanation": (
                    "The source content explicitly states the core claim: Paragraph one."
                ),
            }
        ],
    }


def test_create_lesson_marks_failed_when_extraction_fails(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    monkeypatch.setattr(
        service,
        "fetch_url_metadata",
        lambda _url: {"title": "Metadata title"},
        raising=False,
    )
    monkeypatch.setattr(
        service,
        "extract_body",
        lambda _url: ("", "error"),
        raising=False,
    )

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    assert lesson["generation_error"] == "Could not extract readable article content."
    assert lesson["title"] is None
    assert lesson["source_content"] is None
    assert lesson["lesson_detail"] is None


def test_create_lesson_marks_failed_when_structured_detail_is_malformed(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    monkeypatch.setattr(
        service,
        "generate_structured_lesson_detail",
        lambda _fields: {"gist": "Only one field is not enough."},
        raising=False,
    )

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    assert lesson["generation_error"] == "Generated lesson detail was malformed."
    assert lesson["lesson_detail"] is None


def test_create_lesson_marks_failed_when_structured_detail_generation_raises(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    def _boom(_fields: dict[str, object]) -> dict[str, object]:
        message = "invalid generated json"
        raise ValueError(message)

    monkeypatch.setattr(service, "generate_structured_lesson_detail", _boom, raising=False)

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    assert lesson["generation_error"] == "Generated lesson detail was malformed."
    assert lesson["lesson_detail"] is None


def test_create_lesson_rejects_citations_not_found_in_source_context(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    monkeypatch.setattr(
        service,
        "generate_structured_lesson_detail",
        lambda _fields: {
            "gist": "A gist grounded in the article.",
            "explanation": "A short explanation grounded in the article.",
            "key_claims": ["A grounded claim."],
            "prerequisite_concepts": ["Background context"],
            "why_it_matters": "It matters because the source is useful.",
            "read_worthiness": {"verdict": "read", "rationale": "The source is useful."},
            "who_should_read": ["Curious readers"],
            "questions_to_keep_in_mind": ["Which claims are supported?"],
            "citations": [
                {
                    "label": "1",
                    "snippet": "This invented quote is absent from the article.",
                    "source": "Metadata title",
                }
            ],
        },
        raising=False,
    )

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    assert lesson["generation_error"] == "Generated lesson citations did not match source content."
    assert lesson["lesson_detail"] is None


def test_create_lesson_rejects_citation_sources_not_found_in_source_context(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    monkeypatch.setattr(
        service,
        "generate_structured_lesson_detail",
        lambda _fields: {
            "gist": "Body for https://example.com/a",
            "explanation": "Body for https://example.com/a",
            "key_claims": ["Body for https://example.com/a"],
            "prerequisite_concepts": ["Background context"],
            "why_it_matters": "It matters because the source is useful.",
            "read_worthiness": {"verdict": "read", "rationale": "The source is useful."},
            "who_should_read": ["Curious readers"],
            "questions_to_keep_in_mind": ["Which claims are supported?"],
            "citations": [
                {
                    "label": "1",
                    "snippet": "Body for https://example.com/a",
                    "source": "Invented Source",
                }
            ],
        },
        raising=False,
    )

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    assert lesson["generation_error"] == "Generated lesson citations did not match source content."
    assert lesson["lesson_detail"] is None


def test_create_lesson_rejects_structured_detail_with_extra_blank_or_long_fields(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    monkeypatch.setattr(
        service,
        "generate_structured_lesson_detail",
        lambda _fields: {
            "gist": "x" * 281,
            "unexpected_extra_field": "not part of the contract",
            "explanation": "Body for https://example.com/a",
            "key_claims": [""],
            "prerequisite_concepts": ["Background context"],
            "why_it_matters": "It matters because the source is useful.",
            "read_worthiness": {"verdict": "read", "rationale": "The source is useful."},
            "who_should_read": ["Curious readers"],
            "questions_to_keep_in_mind": ["Which claims are supported?"],
            "citations": [
                {
                    "label": "1",
                    "snippet": "Body for https://example.com/a",
                    "source": "Title for https://example.com/a",
                }
            ],
        },
        raising=False,
    )

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    assert lesson["generation_error"] == "Generated lesson detail was malformed."
    assert lesson["lesson_detail"] is None


def test_create_lesson_ignores_metadata_failure_when_body_succeeds(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    def _boom(url: str) -> dict[str, str]:
        message = "metadata unavailable"
        raise RuntimeError(message)

    monkeypatch.setattr(service, "fetch_url_metadata", _boom, raising=False)
    monkeypatch.setattr(
        service,
        "extract_body",
        lambda _url: ("Useful body text.", "ok"),
        raising=False,
    )

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "complete"
    assert lesson["generation_error"] is None
    assert lesson["title"] == "https://example.com/a"
    assert lesson["source_name"] is None
    assert lesson["author"] is None
    assert lesson["published_at"] is None
    assert lesson["source_content"] == "Useful body text."


def test_create_lesson_rejects_unsafe_url(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    with pytest.raises(service.LessonUrlError):
        service.create_lesson(user_id, "file:///etc/passwd", database_url=pg_clean)


def test_get_lesson_is_user_scoped(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")

    lesson = service.create_lesson(alice, "https://example.com/a", database_url=pg_clean)

    assert service.get_lesson(lesson["id"], alice, database_url=pg_clean) is not None
    assert service.get_lesson(lesson["id"], bob, database_url=pg_clean) is None


def test_create_lesson_duplicate_resets_pending_state(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    first = service.create_lesson(user_id, "https://example.com/story", database_url=pg_clean)

    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            UPDATE lessons
            SET generation_status = 'failed', generation_error = %s, source_content = %s
            WHERE id = %s
            """,
            ("boom", "old content", first["id"]),
        )

    second = service.create_lesson(
        user_id,
        "https://example.com/story/",
        database_url=pg_clean,
    )

    assert second["id"] == first["id"]
    assert second["original_url"] == first["original_url"]
    assert second["generation_status"] == "complete"
    assert second["generation_error"] is None
    assert second["source_content"] == "Body for https://example.com/story"


def test_create_lesson_failed_retry_clears_stale_extracted_fields(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    first = service.create_lesson(user_id, "https://example.com/story", database_url=pg_clean)

    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            UPDATE lessons
            SET title = %s,
                source_name = %s,
                author = %s,
                published_at = %s,
                source_content = %s
            WHERE id = %s
            """,
            (
                "Stale title",
                "Stale source",
                "Stale author",
                "2024-01-02",
                "Stale content",
                first["id"],
            ),
        )

    monkeypatch.setattr(
        service,
        "extract_body",
        lambda _url: ("", "error"),
        raising=False,
    )

    second = service.create_lesson(
        user_id,
        "https://example.com/story/",
        database_url=pg_clean,
    )

    assert second["id"] == first["id"]
    assert second["generation_status"] == "failed"
    assert second["generation_error"] == "Could not extract readable article content."
    assert second["title"] is None
    assert second["source_name"] is None
    assert second["author"] is None
    assert second["published_at"] is None
    assert second["source_content"] is None


def test_create_lesson_marks_failed_when_extraction_raises(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    def _boom(_url: str) -> tuple[str, str]:
        message = "extract exploded"
        raise RuntimeError(message)

    monkeypatch.setattr(service, "extract_body", _boom, raising=False)

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    assert lesson["generation_error"] == "Could not extract readable article content."
    assert lesson["title"] is None
    assert lesson["source_name"] is None
    assert lesson["author"] is None
    assert lesson["published_at"] is None
    assert lesson["source_content"] is None


def test_create_lesson_endpoint_returns_completed_lesson(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    calls: list[tuple[int, int]] = []

    def fake_generate(lesson_id: int, task_user_id: int) -> dict[str, object]:
        calls.append((lesson_id, task_user_id))
        return service._update_lesson_success(
            lesson_id,
            task_user_id,
            lesson_fields={
                "title": "API article",
                "source_name": "API Source",
                "author": "Robin Reporter",
                "published_at": "2026-07-09",
                "source_content": "API body text.",
                "lesson_detail": {
                    "gist": "API body text.",
                    "explanation": "API body text.",
                    "key_claims": ["API body text."],
                    "prerequisite_concepts": ["Context from API Source"],
                    "why_it_matters": (
                        "It helps you decide whether API article deserves deeper reading."
                    ),
                    "read_worthiness": {
                        "verdict": "skim",
                        "rationale": "Start with a skim.",
                    },
                    "who_should_read": ["Curious readers"],
                    "questions_to_keep_in_mind": ["Which claim is supported?"],
                    "citations": [
                        {
                            "label": "1",
                            "snippet": "API body text.",
                            "source": "API article",
                        }
                    ],
                },
            },
            database_url=pg_clean,
        )

    monkeypatch.setattr(service, "generate_lesson_from_url", fake_generate, raising=False)

    with _api_client(user_id) as client:
        response = client.post(
            "/api/learn/lessons",
            json={"url": "https://Example.com/story?b=2&a=1"},
        )

    assert response.status_code == 201
    lesson = response.json()
    assert lesson["user_id"] == user_id
    assert lesson["original_url"] == "https://Example.com/story?b=2&a=1"
    assert lesson["normalized_url"] == "https://example.com/story?a=1&b=2"
    assert lesson["generation_status"] == "pending"
    assert lesson["generation_error"] is None
    assert lesson["title"] is None
    assert lesson["source_content"] is None
    assert calls == [(lesson["id"], user_id)]

    persisted = service.get_lesson(int(lesson["id"]), user_id, database_url=pg_clean)
    assert persisted is not None
    assert persisted["generation_status"] == "complete"
    assert persisted["title"] == "API article"
    assert persisted["source_content"] == "API body text."


def test_create_lesson_endpoint_returns_failed_lesson_on_extraction_error(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    calls: list[tuple[int, int]] = []

    def fake_generate(lesson_id: int, task_user_id: int) -> dict[str, object]:
        calls.append((lesson_id, task_user_id))
        return service._update_lesson_failure(
            lesson_id,
            task_user_id,
            "Could not extract readable article content.",
            database_url=pg_clean,
        )

    monkeypatch.setattr(service, "generate_lesson_from_url", fake_generate, raising=False)

    with _api_client(user_id) as client:
        response = client.post("/api/learn/lessons", json={"url": "https://example.com/story"})

    assert response.status_code == 201
    lesson = response.json()
    assert lesson["generation_status"] == "pending"
    assert lesson["generation_error"] is None
    assert calls == [(lesson["id"], user_id)]

    persisted = service.get_lesson(int(lesson["id"]), user_id, database_url=pg_clean)
    assert persisted is not None
    assert persisted["generation_status"] == "failed"
    assert persisted["generation_error"] == "Could not extract readable article content."


def test_create_lesson_endpoint_rejects_localhost_url(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],
    )

    with _api_client(user_id) as client:
        response = client.post("/api/learn/lessons", json={"url": "http://localhost/article"})

    assert response.status_code == 400
    assert "localhost" in response.json()["detail"]


def test_get_lesson_endpoint_returns_user_owned_lesson(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    with _api_client(user_id) as client:
        response = client.get(f"/api/learn/lessons/{lesson['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == lesson["id"]


def test_get_lesson_endpoint_404s_for_other_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = service.create_lesson(alice, "https://example.com/a", database_url=pg_clean)

    with _api_client(bob, username="bob") as client:
        response = client.get(f"/api/learn/lessons/{lesson['id']}")

    assert response.status_code == 404
    assert response.json()["detail"] == "lesson not found"


def _mock_chat_reply(reply: str) -> Any:
    captured: dict[str, Any] = {}

    def _mock_chat_create(*_args: Any, messages: list[dict[str, str]], **_kwargs: Any) -> Any:
        captured["messages"] = messages
        message = SimpleNamespace(content=reply)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])

    return _mock_chat_create, captured


def test_ask_lesson_question_returns_grounded_reply(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("FREE_LLM_API_KEY", "freellmapi-key")
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    import news_dashboard.ai_client as ai_client_mod

    mock_chat_create, captured = _mock_chat_reply("Here is a simpler explanation.")
    monkeypatch.setattr(ai_client_mod, "chat_create", mock_chat_create)

    history = [
        {"role": "user", "content": "What is this about?"},
        {"role": "assistant", "content": "It's about the article."},
    ]
    reply = service.ask_lesson_question(
        lesson["id"],
        user_id,
        "Explain this more simply.",
        history,
        database_url=pg_clean,
    )

    assert reply == "Here is a simpler explanation."
    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert "Body for https://example.com/a" in messages[0]["content"]
    assert messages[-1] == {"role": "user", "content": "Explain this more simply."}


def test_ask_lesson_question_is_user_scoped(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("FREE_LLM_API_KEY", "freellmapi-key")
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = service.create_lesson(alice, "https://example.com/a", database_url=pg_clean)

    with pytest.raises(service.LessonNotFoundError):
        service.ask_lesson_question(
            lesson["id"], bob, "What is this about?", [], database_url=pg_clean
        )


def test_ask_lesson_question_rejects_blank_question(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("FREE_LLM_API_KEY", "freellmapi-key")
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    with pytest.raises(service.LessonQuestionEmptyError):
        service.ask_lesson_question(lesson["id"], user_id, "   ", [], database_url=pg_clean)


def test_ask_lesson_question_raises_when_ai_not_configured(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    with pytest.raises(service.LessonChatNotConfiguredError):
        service.ask_lesson_question(
            lesson["id"], user_id, "What is this about?", [], database_url=pg_clean
        )


def test_ask_lesson_question_endpoint_returns_reply(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("FREE_LLM_API_KEY", "freellmapi-key")
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    import news_dashboard.ai_client as ai_client_mod

    mock_chat_create, _captured = _mock_chat_reply("Here's an example.")
    monkeypatch.setattr(ai_client_mod, "chat_create", mock_chat_create)

    with _api_client(user_id) as client:
        response = client.post(
            f"/api/learn/lessons/{lesson['id']}/questions",
            json={"question": "Give me a concrete example.", "history": []},
        )

    assert response.status_code == 200
    assert response.json() == {"reply": "Here's an example."}


def test_ask_lesson_question_endpoint_404s_for_other_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("FREE_LLM_API_KEY", "freellmapi-key")
    init_db(database_url=pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = service.create_lesson(alice, "https://example.com/a", database_url=pg_clean)

    with _api_client(bob, username="bob") as client:
        response = client.post(
            f"/api/learn/lessons/{lesson['id']}/questions",
            json={"question": "What is this about?", "history": []},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "lesson not found"


def test_ask_lesson_question_endpoint_rejects_blank_question(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    with _api_client(user_id) as client:
        response = client.post(
            f"/api/learn/lessons/{lesson['id']}/questions",
            json={"question": "   ", "history": []},
        )

    assert response.status_code == 422


def test_ask_lesson_question_endpoint_returns_503_when_ai_not_configured(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    with _api_client(user_id) as client:
        response = client.post(
            f"/api/learn/lessons/{lesson['id']}/questions",
            json={"question": "What is this about?", "history": []},
        )

    assert response.status_code == 503
