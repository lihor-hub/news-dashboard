"""Tests for per-user saved search views."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import create_user, require_auth
from news_dashboard.main import app
from news_dashboard.saved_searches.models import SavedSearchFilters
from news_dashboard.saved_searches.service import create_saved_search, list_saved_searches


@pytest.fixture
def db(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    return pg_clean


def _make_user(db_path: str, username: str) -> int:
    return int(create_user(username, "password123", db_path=db_path)["id"])


def _authed_client(user_id: int) -> TestClient:
    client = TestClient(app, raise_server_exceptions=True)
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "username": f"user-{user_id}",
        "email": None,
        "is_admin": False,
    }
    return client


def test_create_and_list_saved_searches(db: str) -> None:
    alice = _make_user(db, "alice")
    saved = create_saved_search(
        alice,
        "AI starred",
        SavedSearchFilters(q=" agents ", states=["today"], starred_only=True),
        db_path=db,
    )

    assert saved["name"] == "AI starred"
    assert saved["filters"]["q"] == "agents"
    assert saved["filters"]["states"] == ["today"]
    assert saved["filters"]["starred_only"] is True
    assert [item["id"] for item in list_saved_searches(alice, db_path=db)] == [saved["id"]]


def test_saved_searches_are_private_per_user(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    create_saved_search(alice, "Alice view", SavedSearchFilters(q="postgres"), db_path=db)

    assert [item["name"] for item in list_saved_searches(alice, db_path=db)] == ["Alice view"]
    assert list_saved_searches(bob, db_path=db) == []


def test_saved_search_filters_are_normalized(db: str) -> None:
    alice = _make_user(db, "alice")
    saved = create_saved_search(
        alice,
        "Mixed",
        SavedSearchFilters(
            q="x" * 250,
            states=["today", "invalid", "today"],
            date_range="future",
            tag_id=-1,
        ),
        db_path=db,
    )

    assert saved["filters"]["q"] == "x" * 200
    assert saved["filters"]["states"] == ["today"]
    assert saved["filters"]["date_range"] == "all"
    assert saved["filters"]["tag_id"] is None


def test_saved_search_api_crud_and_user_scope(db: str) -> None:
    alice = _make_user(db, "alice")
    bob = _make_user(db, "bob")
    alice_client = _authed_client(alice)

    created = alice_client.post(
        "/api/search/saved",
        json={
            "name": "Kubernetes",
            "filters": {"q": "k8s", "states": ["later"], "date_range": "week"},
        },
    )
    assert created.status_code == 200
    saved_id = created.json()["id"]

    bob_client = _authed_client(bob)
    assert bob_client.get("/api/search/saved").json()["items"] == []
    bob_update = bob_client.patch(f"/api/search/saved/{saved_id}", json={"name": "Hijack"})
    assert bob_update.status_code == 404

    alice_client = _authed_client(alice)
    renamed = alice_client.patch(f"/api/search/saved/{saved_id}", json={"name": "Infra"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Infra"

    deleted = alice_client.delete(f"/api/search/saved/{saved_id}")
    assert deleted.status_code == 200
    assert alice_client.get("/api/search/saved").json()["items"] == []
