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

    resp = client.post("/api/feedback", json={"trace_id": "t", "helpful": True})

    assert resp.status_code == 200
    assert resp.json() == {"recorded": False}
