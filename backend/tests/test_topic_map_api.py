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


def test_topic_map_static_route_is_not_parsed_as_article_id(monkeypatch: Any) -> None:
    def fake_cluster_recent_articles(*, user_id: int) -> list[dict[str, Any]]:
        assert user_id == 42
        return [
            {
                "id": 1,
                "headline": "Topic arc",
                "trend_summary": "Related articles are moving together.",
                "x": 0.0,
                "y": 0.0,
                "article_ids": [7],
                "articles": [
                    {
                        "id": 7,
                        "title": "Article 7",
                        "source": "Example",
                        "x": 0.25,
                        "y": -0.5,
                        "category": "tech",
                    }
                ],
            }
        ]

    monkeypatch.setattr(
        "news_dashboard.insights.cluster_recent_articles",
        fake_cluster_recent_articles,
    )

    response = _client().get("/api/articles/topic-map")

    assert response.status_code == 200
    payload = response.json()
    assert payload["clusters"][0]["headline"] == "Topic arc"
    article = payload["clusters"][0]["articles"][0]
    assert article["x"] == 0.25
    assert article["y"] == -0.5
    assert article["category"] == "tech"


def test_numeric_article_detail_route_still_resolves(monkeypatch: Any) -> None:
    def fake_get_article(article_id: int, *, user_id: int) -> dict[str, Any]:
        assert article_id == 7
        assert user_id == 42
        return {"id": 7, "title": "Article 7"}

    monkeypatch.setattr("news_dashboard.main.get_article", fake_get_article)

    response = _client().get("/api/articles/7")

    assert response.status_code == 200
    assert response.json() == {"id": 7, "title": "Article 7"}
