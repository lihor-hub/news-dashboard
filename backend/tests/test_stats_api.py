from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from news_dashboard.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _dataset_payload() -> dict[str, Any]:
    return {
        "summary": {
            "article_count": 0,
            "oldest_discovered_at": None,
            "newest_discovered_at": None,
            "coverage_days": 0,
        },
        "storage": {
            "database_bytes": 1,
            "article_heap_bytes": 1,
            "article_auxiliary_bytes": 0,
            "article_index_bytes": 1,
            "article_total_bytes": 2,
            "median_article_bytes": 0,
            "amortized_article_bytes": 0,
        },
        "trend": [],
        "trend_granularity": "day",
        "retention_preview": {
            "enabled": False,
            "retention_days": None,
            "eligible_articles": 0,
            "protected_articles": 0,
            "estimated_payload_bytes": 0,
        },
    }


def test_dataset_stats_endpoint_accepts_supported_range(client: TestClient) -> None:
    with patch(
        "news_dashboard.stats.router.dataset_stats", return_value=_dataset_payload()
    ) as load:
        response = client.get("/api/stats/dataset", params={"range": "90d"})

    assert response.status_code == 200
    assert response.json()["summary"]["article_count"] == 0
    assert load.call_args.args[0] == "90d"


def test_dataset_stats_endpoint_rejects_unknown_range(client: TestClient) -> None:
    response = client.get("/api/stats/dataset", params={"range": "forever"})

    assert response.status_code == 422


def test_dataset_stats_endpoint_requires_admin(client: TestClient) -> None:
    from news_dashboard.auth import require_admin

    def deny_admin() -> None:
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[require_admin] = deny_admin
    try:
        response = client.get("/api/stats/dataset", params={"range": "30d"})
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 403
