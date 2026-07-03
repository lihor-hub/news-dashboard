from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> Any:
    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    fake_user = {"id": 7, "username": "feedbackuser", "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_feedback_records_score_when_langfuse_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_create_score(trace_id: str, **kwargs: Any) -> bool:
        captured["trace_id"] = trace_id
        captured.update(kwargs)
        return True

    monkeypatch.setattr("news_dashboard.ai_client.create_score", fake_create_score)
    monkeypatch.setattr(
        "news_dashboard.ai_memory.service.record_memory_event",
        lambda *_a, **_k: {},
    )

    resp = client.post(
        "/api/feedback",
        json={"trace_id": "trace-abc", "helpful": True, "comment": "great"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"recorded": True}
    assert captured["trace_id"] == "trace-abc"
    assert captured["name"] == "user-thumbs"
    assert captured["value"] == 1
    assert captured["data_type"] == "BOOLEAN"
    assert captured["comment"] == "great"


def test_feedback_thumbs_down_sends_zero(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_create_score(trace_id: str, **kwargs: Any) -> bool:
        captured.update(kwargs)
        return True

    monkeypatch.setattr("news_dashboard.ai_client.create_score", fake_create_score)
    monkeypatch.setattr(
        "news_dashboard.ai_memory.service.record_memory_event",
        lambda *_a, **_k: {},
    )

    resp = client.post("/api/feedback", json={"trace_id": "t", "helpful": False})

    assert resp.status_code == 200
    assert captured["value"] == 0
    # Empty/omitted comment is normalised to None, not "".
    assert captured["comment"] is None


def test_feedback_noop_returns_recorded_false(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # When Langfuse is disabled create_score returns False; the endpoint surfaces
    # that without erroring.
    monkeypatch.setattr("news_dashboard.ai_client.create_score", lambda *_a, **_k: False)
    monkeypatch.setattr(
        "news_dashboard.ai_memory.service.record_memory_event",
        lambda *_a, **_k: {},
    )

    resp = client.post("/api/feedback", json={"trace_id": "t", "helpful": True})

    assert resp.status_code == 200
    assert resp.json() == {"recorded": False}


def test_feedback_persists_local_memory_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    from news_dashboard.db import connect

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setattr("news_dashboard.ai_client.create_score", lambda *_a, **_k: False)
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            "INSERT INTO users(id, username, password_hash) VALUES (%s, %s, 'hash')",
            (7, "feedbackuser"),
        )

    resp = client.post(
        "/api/feedback",
        json={"trace_id": "trace-local", "helpful": False, "comment": "missed my goal"},
    )

    assert resp.status_code == 200
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            """
            SELECT user_id, event_type, source, content, metadata
            FROM user_ai_memory_events
            WHERE user_id = %s
            """,
            (7,),
        ).fetchone()
    assert row["event_type"] == "feedback"
    assert row["source"] == "ask_feedback"
    assert row["content"] == "missed my goal"
    assert row["metadata"]["trace_id"] == "trace-local"
