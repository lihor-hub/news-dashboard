from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from fastapi.testclient import TestClient

from news_dashboard.auth import require_admin, require_auth
from news_dashboard.main import app


def test_admin_ai_quality_requires_admin(monkeypatch: Any) -> None:
    app.dependency_overrides[require_auth] = lambda: {
        "id": 2,
        "username": "reader",
        "is_admin": False,
    }
    app.dependency_overrides[require_admin] = lambda: (_ for _ in ()).throw(
        HTTPException(status_code=403, detail="admin role required")
    )

    response = TestClient(app, raise_server_exceptions=False).get("/api/admin/ai/quality")

    assert response.status_code == 403
    app.dependency_overrides.pop(require_auth, None)
    app.dependency_overrides.pop(require_admin, None)


def test_admin_ai_quality_returns_local_summary(monkeypatch: Any) -> None:
    def fake_summary(*, days: int) -> dict[str, Any]:
        assert days == 14
        return {"range_days": 14, "feedback": [], "evals": [], "recent_failures": []}

    monkeypatch.setattr("news_dashboard.ai_evals.admin_quality_summary", fake_summary)

    response = TestClient(app).get("/api/admin/ai/quality?days=14")

    assert response.status_code == 200
    assert response.json()["range_days"] == 14
