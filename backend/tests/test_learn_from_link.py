from __future__ import annotations

import json
import socket
from collections.abc import Generator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import require_admin, require_auth
from news_dashboard.db import connect, init_db
from news_dashboard.learn_from_link import service
from news_dashboard.learn_from_link.models import LessonCitation, LessonContent
from news_dashboard.main import app
from news_dashboard.url_safety import UnsafeUrlError


def _fake_chat_response(content: str) -> SimpleNamespace:
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _stub_lesson_content(source_content: str = "") -> LessonContent:
    has_paragraph = "Paragraph one." in source_content
    citations = [LessonCitation(text="Paragraph one.")] if has_paragraph else []
    return LessonContent(
        gist="A 30-second gist.",
        explanation="A short explanation of the core idea.",
        key_claims=["The article makes a key claim."],
        prerequisites=[],
        why_it_matters="It matters because it affects readers.",
        verdict="skim",
        verdict_rationale="Skim it for the headline claim.",
        intended_readers=["Curious generalists"],
        guiding_questions=["Is the claim well supported?"],
        citations=citations,
    )


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


_GENERATE_LESSON_CONTENT_TESTS = {
    "test_generate_lesson_content_parses_and_validates_ai_json",
    "test_generate_lesson_content_raises_on_malformed_json",
    "test_generate_lesson_content_raises_on_schema_violation",
}


@pytest.fixture(autouse=True)
def _lesson_content_stub(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.name in _GENERATE_LESSON_CONTENT_TESTS:
        return
    monkeypatch.setattr(
        service,
        "generate_lesson_content",
        lambda *, user_id, title, source_content: _stub_lesson_content(source_content),  # noqa: ARG005
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


def test_create_lesson_persists_structured_lesson_content(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    lesson = service.create_lesson(user_id, "https://example.com/story", database_url=pg_clean)

    assert lesson["generation_status"] == "complete"
    content = lesson["lesson_content"]
    assert content["gist"] == "A 30-second gist."
    assert content["verdict"] == "skim"
    assert content["verdict_rationale"] == "Skim it for the headline claim."
    assert content["key_claims"] == ["The article makes a key claim."]
    assert content["intended_readers"] == ["Curious generalists"]
    assert content["guiding_questions"] == ["Is the claim well supported?"]


def test_generate_lesson_content_parses_and_validates_ai_json(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setattr(service, "_lesson_ai_config", lambda: ("test-key", None, "gpt-4o-mini"))

    payload = {
        "gist": "Gist text.",
        "explanation": "Explanation text.",
        "key_claims": ["Claim one."],
        "prerequisites": [],
        "why_it_matters": "Because reasons.",
        "verdict": "read",
        "verdict_rationale": "Worth reading.",
        "intended_readers": [],
        "guiding_questions": [],
        "citations": [{"text": "quoted snippet"}],
    }

    response = _fake_chat_response(json.dumps(payload))
    monkeypatch.setattr("news_dashboard.ai_client.get_chat_client", lambda **_kwargs: object())
    monkeypatch.setattr("news_dashboard.ai_client.chat_create", lambda *_args, **_kwargs: response)

    content = service.generate_lesson_content(
        user_id=1,
        title="Some article",
        source_content="Body text with a quoted snippet inside it.",
    )

    assert content.gist == "Gist text."
    assert content.verdict == "read"
    assert content.citations[0].text == "quoted snippet"


def test_generate_lesson_content_raises_on_malformed_json(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setattr(service, "_lesson_ai_config", lambda: ("test-key", None, "gpt-4o-mini"))

    response = _fake_chat_response("not json")
    monkeypatch.setattr("news_dashboard.ai_client.get_chat_client", lambda **_kwargs: object())
    monkeypatch.setattr("news_dashboard.ai_client.chat_create", lambda *_args, **_kwargs: response)

    with pytest.raises(service.LessonGenerationError):
        service.generate_lesson_content(
            user_id=1,
            title="Some article",
            source_content="Body text.",
        )


def test_generate_lesson_content_raises_on_schema_violation(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setattr(service, "_lesson_ai_config", lambda: ("test-key", None, "gpt-4o-mini"))

    bad_payload = {"gist": "Only a gist, missing every other required field."}

    response = _fake_chat_response(json.dumps(bad_payload))
    monkeypatch.setattr("news_dashboard.ai_client.get_chat_client", lambda **_kwargs: object())
    monkeypatch.setattr("news_dashboard.ai_client.chat_create", lambda *_args, **_kwargs: response)

    with pytest.raises(service.LessonGenerationError):
        service.generate_lesson_content(
            user_id=1,
            title="Some article",
            source_content="Body text.",
        )


def test_create_lesson_marks_failed_when_ai_generation_raises(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    def _boom(*, user_id: int, title: str, source_content: str) -> LessonContent:
        message = "AI unavailable"
        raise service.LessonGenerationError(message)

    monkeypatch.setattr(service, "generate_lesson_content", _boom, raising=False)

    lesson = service.create_lesson(user_id, "https://example.com/story", database_url=pg_clean)

    assert lesson["generation_status"] == "failed"
    expected_error = "Could not generate a structured lesson from this article."
    assert lesson["generation_error"] == expected_error
    assert lesson["title"] is None
    assert lesson["source_content"] is None
    assert lesson["lesson_content"] is None


def test_verify_citations_drops_citations_not_found_in_source() -> None:
    content = LessonContent(
        gist="Gist.",
        explanation="Explanation.",
        key_claims=["Claim."],
        why_it_matters="Matters.",
        verdict="skim",
        verdict_rationale="Rationale.",
        citations=[
            LessonCitation(text="This is quoted directly from the source."),
            LessonCitation(text="This snippet was never actually said."),
        ],
    )
    source_content = "Intro. This is quoted directly from the source. Outro."

    verified = service._verify_citations(content, source_content)

    assert len(verified.citations) == 1
    assert verified.citations[0].text == "This is quoted directly from the source."


def test_get_lesson_endpoint_exposes_structured_lesson_content(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    with _api_client(user_id) as client:
        response = client.get(f"/api/learn/lessons/{lesson['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["lesson_content"]["verdict"] == "skim"
    assert body["lesson_content"]["gist"] == "A 30-second gist."
