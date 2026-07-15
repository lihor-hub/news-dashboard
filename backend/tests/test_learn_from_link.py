from __future__ import annotations

import socket
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
from news_dashboard.learn_from_link import agent_runs, service
from news_dashboard.learn_from_link.models import LessonDepth
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
    assert lesson["depth"] == "normal"
    assert lesson["persona"] == "developer"
    assert lesson["lesson_detail"] == {
        "gist": "Paragraph one.",
        "explanation": "Paragraph one.\n\nParagraph two.",
        "key_claims": ["Paragraph one.", "Paragraph two."],
        "prerequisite_concepts": ["Context from Example Journal"],
        "why_it_matters": (
            "It helps you decide whether A careful article deserves deeper reading, "
            "for developers weighing implementation details."
        ),
        "read_worthiness": {
            "verdict": "skim",
            "rationale": "Start with a skim: the source is short enough to inspect quickly.",
        },
        "who_should_read": [
            "Readers deciding whether to spend more time with this source, "
            "for developers weighing implementation details."
        ],
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
        lambda _fields, **_kwargs: {"gist": "Only one field is not enough."},
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
        lambda _fields, **_kwargs: {
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
        lambda _fields, **_kwargs: {
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
        lambda _fields, **_kwargs: {
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


def test_list_lessons_orders_newest_first_and_scopes_to_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")

    first = service.create_lesson(alice, "https://example.com/first", database_url=pg_clean)
    second = service.create_lesson(alice, "https://example.com/second", database_url=pg_clean)
    service.create_lesson(bob, "https://example.com/bobs", database_url=pg_clean)

    lessons = service.list_lessons(alice, database_url=pg_clean)

    assert [lesson["id"] for lesson in lessons] == [second["id"], first["id"]]


def test_list_lessons_filters_by_status(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    completed = service.create_lesson(user_id, "https://example.com/ok", database_url=pg_clean)
    monkeypatch.setattr(service, "extract_body", lambda _url: ("", "error"), raising=False)
    failed = service.create_lesson(user_id, "https://example.com/bad", database_url=pg_clean)

    complete_only = service.list_lessons(user_id, status="complete", database_url=pg_clean)
    failed_only = service.list_lessons(user_id, status="failed", database_url=pg_clean)

    assert [lesson["id"] for lesson in complete_only] == [completed["id"]]
    assert [lesson["id"] for lesson in failed_only] == [failed["id"]]


def test_list_lessons_filters_by_verdict(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/short", database_url=pg_clean)
    assert lesson["lesson_detail"]["read_worthiness"]["verdict"] == "skim"

    skim_matches = service.list_lessons(user_id, verdict="skim", database_url=pg_clean)
    study_matches = service.list_lessons(user_id, verdict="study", database_url=pg_clean)

    assert [item["id"] for item in skim_matches] == [lesson["id"]]
    assert study_matches == []


def test_list_lessons_searches_title_url_source_and_concepts(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/story", database_url=pg_clean)

    by_title = service.list_lessons(user_id, q="Title for", database_url=pg_clean)
    by_url = service.list_lessons(user_id, q="example.com/story", database_url=pg_clean)
    by_source = service.list_lessons(user_id, q="Example Source", database_url=pg_clean)
    by_concept = service.list_lessons(
        user_id, q=lesson["lesson_detail"]["prerequisite_concepts"][0], database_url=pg_clean
    )
    no_match = service.list_lessons(user_id, q="no such thing anywhere", database_url=pg_clean)

    assert [item["id"] for item in by_title] == [lesson["id"]]
    assert [item["id"] for item in by_url] == [lesson["id"]]
    assert [item["id"] for item in by_source] == [lesson["id"]]
    assert [item["id"] for item in by_concept] == [lesson["id"]]
    assert no_match == []


def test_list_lessons_endpoint_is_user_scoped(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    alice = _make_user(pg_clean, "alice")
    bob = _make_user(pg_clean, "bob")
    lesson = service.create_lesson(alice, "https://example.com/a", database_url=pg_clean)
    service.create_lesson(bob, "https://example.com/b", database_url=pg_clean)

    with _api_client(alice) as client:
        response = client.get("/api/learn/lessons")

    assert response.status_code == 200
    body = response.json()["lessons"]
    assert [item["id"] for item in body] == [lesson["id"]]


def test_list_lessons_endpoint_supports_query_params(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)
    service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    with _api_client(user_id) as client:
        response = client.get(
            "/api/learn/lessons", params={"status": "complete", "verdict": "skim", "q": "example"}
        )

    assert response.status_code == 200
    assert len(response.json()["lessons"]) == 1


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
            SET generation_status = 'failed',
                generation_error = %s,
                source_content = %s,
                podcast_status = 'complete',
                podcast_error = %s,
                slide_deck = %s::jsonb,
                slide_deck_status = 'complete',
                slide_deck_error = %s,
                study_artifacts = %s::jsonb,
                personal_relevance = %s::jsonb,
                relevance_feedback = true
            WHERE id = %s
            """,
            (
                "boom",
                "old content",
                "old podcast error",
                '{"slides":[{"title":"Old slide","bullets":["Old bullet"]}]}',
                "old slide error",
                '{"flashcards":[{"concept":"Old","claim":"Old claim"}]}',
                (
                    '{"summary":"Old relevance","reasons":["Old reason"],'
                    '"suggested_actions":["Old action"]}'
                ),
                first["id"],
            ),
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
    assert second["podcast_status"] is None
    assert second["podcast_error"] is None
    assert second["slide_deck"] is None
    assert second["slide_deck_status"] is None
    assert second["slide_deck_error"] is None
    assert second["relevance_feedback"] is None


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
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("FREE_LLM_API_KEY", "freellmapi-key")
    source_body = 'Example JSON: {"framework": "LangChain", "ready": true}'
    monkeypatch.setattr(service, "extract_body", lambda _url: (source_body, "ok"))
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    import news_dashboard.ai_client as ai_client_mod

    captured: dict[str, Any] = {}

    def fake_invoke(prompt_value: Any, config: Any) -> AIMessage:
        captured["messages"] = prompt_value.to_messages()
        captured["config"] = config
        return AIMessage(content="Here is a simpler explanation.")

    @contextmanager
    def fake_propagate_attributes(**kwargs: Any) -> Generator[None]:
        captured["attributes"] = kwargs
        yield

    callback = BaseCallbackHandler()
    monkeypatch.setattr(
        ai_client_mod, "get_chat_model", lambda **_kwargs: RunnableLambda(fake_invoke)
    )
    monkeypatch.setattr(ai_client_mod, "langfuse_enabled", lambda: True)
    monkeypatch.setattr("langfuse.propagate_attributes", fake_propagate_attributes)
    monkeypatch.setattr("langfuse.langchain.CallbackHandler", lambda: callback)

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
    assert [message.type for message in messages] == ["system", "human", "ai", "human"]
    assert source_body in messages[0].content
    assert [message.content for message in messages[1:]] == [
        "What is this about?",
        "It's about the article.",
        "Explain this more simply.",
    ]
    assert captured["config"]["callbacks"].handlers == [callback]
    assert captured["attributes"] == {
        "user_id": str(user_id),
        "session_id": f"lesson:{user_id}:{lesson['id']}",
        "tags": ["lesson", "chat"],
        "trace_name": "lesson-chat",
        "prompt": None,
    }


def test_ask_lesson_question_inserts_history_after_managed_system(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)
    import news_dashboard.ai_client as ai_client_mod

    managed = SimpleNamespace(
        messages=[
            {"role": "system", "content": "compiled system"},
            {"role": "user", "content": "compiled question"},
        ],
        langfuse_prompt=object(),
    )
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        ai_client_mod,
        "get_prompt",
        lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs) or managed,
    )
    chat_capture: dict[str, Any] = {}
    monkeypatch.setattr(
        ai_client_mod,
        "get_chat_model",
        lambda **_kwargs: RunnableLambda(
            lambda prompt: (
                chat_capture.update(messages=prompt.messages) or AIMessage(content="answer")
            )
        ),
    )
    history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]

    service.ask_lesson_question(lesson["id"], user_id, "question", history, database_url=pg_clean)

    assert captured["args"] == ("lesson-chat",)
    assert captured["kwargs"]["prompt_type"] == "chat"
    assert captured["kwargs"]["variables"]["question"] == "question"
    assert captured["kwargs"]["fallback"] == [
        {
            "role": "system",
            "content": service._LESSON_CHAT_SYSTEM_PROMPT.replace(
                "{lesson_context}", "{{lesson_context}}"
            ).replace("{source_context}", "{{source_context}}"),
        },
        {"role": "user", "content": "{{question}}"},
    ]
    assert all(message not in captured["kwargs"]["fallback"] for message in history)
    assert [message.content for message in chat_capture["messages"]] == [
        "compiled system",
        "earlier",
        "reply",
        "compiled question",
    ]


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

    monkeypatch.setattr(
        ai_client_mod,
        "get_chat_model",
        lambda **_kwargs: RunnableLambda(lambda _prompt: AIMessage(content="Here's an example.")),
    )

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


def test_create_lesson_persists_depth_and_persona(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    lesson = service.create_lesson(
        user_id,
        "https://example.com/a",
        depth="deep",
        persona="new_to_ai",
        database_url=pg_clean,
    )

    assert lesson["depth"] == "deep"
    assert lesson["persona"] == "new_to_ai"

    persisted = service.get_lesson(int(lesson["id"]), user_id, database_url=pg_clean)
    assert persisted is not None
    assert persisted["depth"] == "deep"
    assert persisted["persona"] == "new_to_ai"


@pytest.mark.parametrize(
    ("depth", "expected_claim_count", "max_explanation_length"),
    [
        ("tiny", 1, 150),
        ("normal", 3, 600),
        ("deep", 5, 1500),
        ("expert", 8, 4000),
    ],
)
def test_generate_structured_lesson_detail_shapes_output_by_depth(
    depth: LessonDepth, expected_claim_count: int, max_explanation_length: int
) -> None:
    sentences = " ".join(f"Sentence number {i}." for i in range(1, 10))
    lesson_fields = {
        "original_url": "https://example.com/a",
        "title": "A deep dive",
        "source_name": "Example Source",
        "source_content": sentences,
    }

    detail = service.generate_structured_lesson_detail(
        lesson_fields,
        depth=depth,
        persona="developer",
    )

    assert len(detail["key_claims"]) == expected_claim_count
    assert len(detail["explanation"]) <= max_explanation_length


def test_generate_structured_lesson_detail_frames_content_by_persona() -> None:
    lesson_fields = {
        "original_url": "https://example.com/a",
        "title": "A talk-worthy piece",
        "source_name": "Example Source",
        "source_content": "A single sentence to summarize.",
    }

    detail = service.generate_structured_lesson_detail(
        lesson_fields, depth="normal", persona="preparing_talk"
    )

    assert "preparing a talk" in detail["why_it_matters"]
    assert "preparing a talk" in detail["who_should_read"][0]


def test_regenerate_lesson_updates_controls_and_marks_pending(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)
    assert lesson["generation_status"] == "complete"
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            UPDATE lessons
            SET podcast_status = 'complete',
                podcast_error = %s,
                slide_deck = %s::jsonb,
                slide_deck_status = 'complete',
                slide_deck_error = %s,
                study_artifacts = %s::jsonb,
                personal_relevance = %s::jsonb,
                relevance_feedback = false
            WHERE id = %s
            """,
            (
                "old podcast error",
                '{"slides":[{"title":"Old slide","bullets":["Old bullet"]}]}',
                "old slide error",
                '{"flashcards":[{"concept":"Old","claim":"Old claim"}]}',
                (
                    '{"summary":"Old relevance","reasons":["Old reason"],'
                    '"suggested_actions":["Old action"]}'
                ),
                lesson["id"],
            ),
        )

    updated = service.regenerate_lesson(
        int(lesson["id"]),
        user_id,
        depth="expert",
        persona="product_builder",
        database_url=pg_clean,
    )

    assert updated["generation_status"] == "pending"
    assert updated["generation_error"] is None
    assert updated["depth"] == "expert"
    assert updated["persona"] == "product_builder"
    assert updated["podcast_status"] is None
    assert updated["podcast_error"] is None
    assert updated["slide_deck"] is None
    assert updated["slide_deck_status"] is None
    assert updated["slide_deck_error"] is None
    assert updated["study_artifacts"] is None
    assert updated["personal_relevance"] is None
    assert updated["relevance_feedback"] is None


def test_regenerate_lesson_raises_not_found_for_missing_lesson(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)

    with pytest.raises(service.LessonNotFoundError):
        service.regenerate_lesson(
            999_999,
            user_id,
            depth="normal",
            persona="developer",
            database_url=pg_clean,
        )


def test_regenerate_lesson_raises_not_found_for_other_users_lesson(pg_clean: str) -> None:
    owner_id = _make_user(pg_clean, username="owner")
    other_id = _make_user(pg_clean, username="other")
    lesson = service.create_lesson(owner_id, "https://example.com/a", database_url=pg_clean)

    with pytest.raises(service.LessonNotFoundError):
        service.regenerate_lesson(
            int(lesson["id"]),
            other_id,
            depth="normal",
            persona="developer",
            database_url=pg_clean,
        )


def test_recover_stale_pending_lessons_marks_old_pending_failed(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)
    stale = service.create_lesson(
        user_id, "https://example.com/stale", database_url=pg_clean, extract=False
    )
    fresh = service.create_lesson(
        user_id, "https://example.com/fresh", database_url=pg_clean, extract=False
    )
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            UPDATE lessons
            SET updated_at = NOW() - INTERVAL '20 minutes'
            WHERE id = %s
            """,
            (stale["id"],),
        )

    recovered = service.recover_stale_pending_lessons(stale_after_minutes=15, database_url=pg_clean)

    assert recovered == 1
    stale_after = service.get_lesson(int(stale["id"]), user_id, database_url=pg_clean)
    fresh_after = service.get_lesson(int(fresh["id"]), user_id, database_url=pg_clean)
    assert stale_after is not None
    assert stale_after["generation_status"] == "failed"
    assert stale_after["generation_error"] == service.STALE_PENDING_LESSON_ERROR
    assert fresh_after is not None
    assert fresh_after["generation_status"] == "pending"
    assert fresh_after["generation_error"] is None


def test_recover_stale_pending_lessons_fails_interrupted_agent_run(pg_clean: str) -> None:
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(
        user_id, "https://example.com/interrupted", database_url=pg_clean, extract=False
    )
    run_id = agent_runs.start_run(
        pg_clean,
        lesson_id=int(lesson["id"]),
        user_id=user_id,
        prompt_version=agent_runs.SYNTHESIS_PROMPT_VERSION,
        model_version=service.DEFAULT_LESSON_CHAT_MODEL,
        config={"depth": lesson["depth"], "persona": lesson["persona"]},
    )
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            UPDATE lessons
            SET updated_at = NOW() - INTERVAL '16 minutes'
            WHERE id = %s
            """,
            (lesson["id"],),
        )

    recovered = service.recover_stale_pending_lessons(stale_after_minutes=15, database_url=pg_clean)

    assert recovered == 1
    with connect(database_url=pg_clean) as conn:
        run = conn.execute(
            "SELECT status, failed_step, error FROM learning_agent_runs WHERE id = %s",
            (run_id,),
        ).fetchone()
    assert run is not None
    assert run["status"] == "failed"
    assert run["failed_step"] == "recovery"
    assert run["error"] == service.STALE_PENDING_LESSON_ERROR


def test_generate_lesson_from_url_records_generation_history(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(
        user_id, "https://example.com/a", depth="tiny", persona="developer", database_url=pg_clean
    )

    service.regenerate_lesson(
        int(lesson["id"]),
        user_id,
        depth="deep",
        persona="preparing_talk",
        database_url=pg_clean,
    )
    service.generate_lesson_from_url(int(lesson["id"]), user_id, database_url=pg_clean)

    generations = service.list_lesson_generations(int(lesson["id"]), user_id, database_url=pg_clean)
    assert len(generations) == 2
    assert generations[0]["depth"] == "deep"
    assert generations[0]["persona"] == "preparing_talk"
    assert generations[0]["generation_status"] == "complete"
    assert generations[1]["depth"] == "tiny"
    assert generations[1]["persona"] == "developer"


def test_generate_lesson_from_url_records_failed_generation_history(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)
    monkeypatch.setattr(service, "extract_body", lambda _url: ("", "error"), raising=False)

    lesson = service.create_lesson(user_id, "https://example.com/a", database_url=pg_clean)

    generations = service.list_lesson_generations(int(lesson["id"]), user_id, database_url=pg_clean)
    assert len(generations) == 1
    assert generations[0]["generation_status"] == "failed"
    assert generations[0]["lesson_detail"] is None
    assert generations[0]["generation_error"] == "Could not extract readable article content."


def test_list_lesson_generations_raises_not_found_for_other_users_lesson(pg_clean: str) -> None:
    owner_id = _make_user(pg_clean, username="owner")
    other_id = _make_user(pg_clean, username="other")
    lesson = service.create_lesson(owner_id, "https://example.com/a", database_url=pg_clean)

    with pytest.raises(service.LessonNotFoundError):
        service.list_lesson_generations(int(lesson["id"]), other_id, database_url=pg_clean)


def test_create_lesson_endpoint_accepts_depth_and_persona(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.post(
            "/api/learn/lessons",
            json={"url": "https://example.com/a", "depth": "expert", "persona": "product_builder"},
        )

    assert response.status_code == 201
    lesson = response.json()
    assert lesson["depth"] == "expert"
    assert lesson["persona"] == "product_builder"


def test_regenerate_lesson_endpoint_reruns_generation_with_new_controls(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        create_response = client.post("/api/learn/lessons", json={"url": "https://example.com/a"})
        lesson_id = create_response.json()["id"]

        regenerate_response = client.post(
            f"/api/learn/lessons/{lesson_id}/regenerate",
            json={"depth": "deep", "persona": "new_to_ai"},
        )

    assert regenerate_response.status_code == 200
    body = regenerate_response.json()
    assert body["depth"] == "deep"
    assert body["persona"] == "new_to_ai"

    persisted = service.get_lesson(int(lesson_id), user_id, database_url=pg_clean)
    assert persisted is not None
    assert persisted["generation_status"] == "complete"
    assert persisted["depth"] == "deep"
    assert persisted["persona"] == "new_to_ai"

    generations = service.list_lesson_generations(int(lesson_id), user_id, database_url=pg_clean)
    assert len(generations) == 2


def test_regenerate_lesson_endpoint_404s_for_missing_lesson(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.post(
            "/api/learn/lessons/999999/regenerate",
            json={"depth": "normal", "persona": "developer"},
        )

    assert response.status_code == 404


def test_list_lesson_generations_endpoint_returns_history(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        create_response = client.post("/api/learn/lessons", json={"url": "https://example.com/a"})
        lesson_id = create_response.json()["id"]

        response = client.get(f"/api/learn/lessons/{lesson_id}/generations")

    assert response.status_code == 200
    generations = response.json()
    assert len(generations) == 1
    assert generations[0]["depth"] == "normal"
    assert generations[0]["persona"] == "developer"
    assert generations[0]["generation_status"] == "complete"


def test_list_lesson_generations_endpoint_404s_for_other_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    owner_id = _make_user(pg_clean, username="owner")
    other_id = _make_user(pg_clean, username="other")

    with _api_client(owner_id) as client:
        create_response = client.post("/api/learn/lessons", json={"url": "https://example.com/a"})
        lesson_id = create_response.json()["id"]

    with _api_client(other_id, username="other") as client:
        response = client.get(f"/api/learn/lessons/{lesson_id}/generations")

    assert response.status_code == 404


def test_lesson_includes_fallback_personal_relevance_without_profile(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    lesson = service.create_lesson(user_id, "https://example.com/relevance", database_url=pg_clean)

    assert lesson["personal_relevance"] == {
        "explanation": (
            "No personalization data is available yet. "
            "Start reading articles to see custom relevance explanations."
        ),
        "signals": [],
    }


def test_lesson_relevance_uses_profile_and_llm_response(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from langchain_core.callbacks import BaseCallbackHandler

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("FREE_LLM_BASE_URL", "https://free.example/v1")
    monkeypatch.setenv("OPENAI_LESSON_CHAT_MODEL", "lesson-relevance-model")
    user_id = _make_user(pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO user_interest_profiles (user_id, interests) VALUES (%s, %s::jsonb)",
            (user_id, '["technology", "AI"]'),
        )

    callback = BaseCallbackHandler()
    captured: dict[str, Any] = {}

    def invoke(prompt: Any, config: Any) -> AIMessage:
        captured.update(prompt=prompt, config=config)
        return AIMessage(
            content=(
                '{"explanation": "Relevant to your AI interests.", "signals": ["Interest: AI"]}'
            )
        )

    def factory(**kwargs: Any) -> Any:
        captured["factory"] = kwargs
        return RunnableLambda(invoke)

    monkeypatch.setattr("news_dashboard.ai_client.get_chat_model", factory)
    monkeypatch.setattr("news_dashboard.ai_client.langfuse_enabled", lambda: True)
    monkeypatch.setattr("langfuse.langchain.CallbackHandler", lambda: callback)

    with patch("langfuse.propagate_attributes") as attributes:
        lesson = service.create_lesson(user_id, "https://example.com/ai", database_url=pg_clean)

    assert lesson["personal_relevance"] == {
        "explanation": "Relevant to your AI interests.",
        "signals": ["Interest: AI"],
    }
    assert captured["factory"] == {
        "api_key": "fake-key",
        "base_url": "https://free.example/v1",
        "model": "lesson-relevance-model",
        "response_format": {"type": "json_object"},
    }
    rendered = captured["prompt"].messages[-1].content
    assert "Lesson title: Title for https://example.com/ai" in rendered
    assert "Interests: ['technology', 'AI']" in rendered
    assert "Lesson gist:" in rendered
    assert callback in captured["config"]["callbacks"].handlers
    attributes.assert_any_call(
        user_id=str(user_id),
        session_id="lesson-run:1",
        tags=["lesson", "generation"],
        trace_name="lesson-generation",
    )
    attributes.assert_any_call(
        user_id=str(user_id),
        session_id=f"lesson:{user_id}:{lesson['id']}",
        tags=["lesson", "relevance"],
        trace_name="lesson-relevance",
        prompt=None,
    )


def test_lesson_relevance_uses_native_chat_prompt(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")
    user_id = _make_user(pg_clean)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO user_interest_profiles (user_id, interests) VALUES (%s, %s::jsonb)",
            (user_id, '["technology"]'),
        )
    import news_dashboard.ai_client as ai_client_mod

    captured: dict[str, Any] = {}
    chat_captured: dict[str, Any] = {}
    managed = SimpleNamespace(
        messages=[{"role": "system", "content": "managed"}], langfuse_prompt=object()
    )
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
                or AIMessage(content='{"explanation":"why","signals":[]}')
            )
        ),
    )

    service.create_lesson(user_id, "https://example.com/relevance", database_url=pg_clean)

    assert captured["args"] == ("lesson-relevance",)
    assert captured["kwargs"]["prompt_type"] == "chat"
    assert captured["kwargs"]["fallback"] == [
        {
            "role": "system",
            "content": (
                "Explain why a lesson is relevant using only the user's provided reading profile. "
                "Return JSON with non-empty explanation and a signals array."
            ),
        },
        {"role": "user", "content": "{{lesson_context}}\n{{profile_context}}"},
    ]
    assert set(captured["kwargs"]["variables"]) == {"lesson_context", "profile_context"}
    assert [message.content for message in chat_captured["messages"]] == ["managed"]


def test_relevance_feedback_endpoint_is_owned_by_lesson_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    owner_id = _make_user(pg_clean)
    other_id = _make_user(pg_clean, username="bob")
    lesson = service.create_lesson(owner_id, "https://example.com/a", database_url=pg_clean)

    with _api_client(owner_id) as client:
        owner_response = client.post(
            f"/api/learn/lessons/{lesson['id']}/relevance/feedback",
            json={"helpful": True},
        )
    with _api_client(other_id, username="bob") as client:
        other_response = client.post(
            f"/api/learn/lessons/{lesson['id']}/relevance/feedback",
            json={"helpful": False},
        )

    assert owner_response.status_code == 200
    assert owner_response.json()["relevance_feedback"] is True
    assert other_response.status_code == 404
