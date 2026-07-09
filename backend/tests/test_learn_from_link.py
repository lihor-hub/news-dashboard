from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

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
def _safe_url_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_validate(url: str) -> None:
        if not url.strip().lower().startswith(("http://", "https://")):
            message = f"unsafe url: {url}"
            raise UnsafeUrlError(message)

    monkeypatch.setattr(service, "validate_server_fetch_url", fake_validate)


def test_create_lesson_persists_pending_record(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)

    user_id = _make_user(pg_clean)
    lesson = service.create_lesson(
        user_id,
        "https://Example.com/story?b=2&a=1",
        database_url=pg_clean,
    )

    assert lesson["user_id"] == user_id
    assert lesson["original_url"] == "https://Example.com/story?b=2&a=1"
    assert lesson["normalized_url"] == "https://example.com/story?a=1&b=2"
    assert lesson["generation_status"] == "pending"
    assert lesson["generation_error"] is None
    assert lesson["title"] is None
    assert lesson["source_content"] is None


def test_create_lesson_rejects_unsafe_url(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    with pytest.raises(service.LessonUrlError):
        service.create_lesson(user_id, "file:///etc/passwd", database_url=pg_clean)


def test_get_lesson_is_user_scoped(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    alice = _make_user(pg_clean, "alice")
    _make_user(pg_clean, "bob")

    lesson = service.create_lesson(alice, "https://example.com/a", database_url=pg_clean)

    assert service.get_lesson(lesson["id"], alice, database_url=pg_clean) is not None
    assert service.get_lesson(lesson["id"], 2, database_url=pg_clean) is None


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
    assert second["generation_status"] == "pending"
    assert second["generation_error"] is None
    assert second["source_content"] == "old content"


def test_create_lesson_endpoint_persists_record(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

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


def test_create_lesson_endpoint_rejects_unsafe_url(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.post("/api/learn/lessons", json={"url": "file:///etc/passwd"})

    assert response.status_code == 400
    assert response.json()["detail"] == "unsafe url: file:///etc/passwd"


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
