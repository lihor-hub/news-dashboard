"""HTTP contract tests for the ai_stats feature-module router."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from news_dashboard.auth import require_auth
from news_dashboard.main import app


def _client() -> TestClient:
    app.dependency_overrides[require_auth] = lambda: {
        "id": 42,
        "username": "reader",
        "email": None,
        "is_admin": False,
    }
    return TestClient(app, raise_server_exceptions=True)


def test_ai_stats_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    assert "/api/ai-stats/word-cloud" in paths
    assert "/api/ai-stats/embedding-map" in paths


def test_word_cloud_endpoint_passes_user_and_days(monkeypatch: Any) -> None:
    def fake_word_cloud(*, user_id: int, days: int) -> dict[str, Any]:
        assert user_id == 42
        assert days == 14
        return {"terms": [], "article_count": 0, "days": days}

    monkeypatch.setattr("news_dashboard.ai_stats.service.word_cloud", fake_word_cloud)

    response = _client().get("/api/ai-stats/word-cloud?days=14")

    assert response.status_code == 200
    assert response.json() == {"terms": [], "article_count": 0, "days": 14}


def test_embedding_map_endpoint_passes_user_and_days(monkeypatch: Any) -> None:
    def fake_embedding_map(*, user_id: int, days: int) -> dict[str, Any]:
        assert user_id == 42
        assert days == 7
        return {
            "points": [],
            "clusters": [],
            "embedded_count": 0,
            "total_count": 0,
            "days": days,
        }

    monkeypatch.setattr("news_dashboard.ai_stats.service.embedding_map", fake_embedding_map)

    response = _client().get("/api/ai-stats/embedding-map")

    assert response.status_code == 200
    assert response.json()["days"] == 7


def test_word_cloud_days_out_of_range_is_422() -> None:
    client = _client()
    assert client.get("/api/ai-stats/word-cloud?days=0").status_code == 422
    assert client.get("/api/ai-stats/word-cloud?days=31").status_code == 422


def test_embedding_map_days_out_of_range_is_422() -> None:
    client = _client()
    assert client.get("/api/ai-stats/embedding-map?days=0").status_code == 422
    assert client.get("/api/ai-stats/embedding-map?days=31").status_code == 422
