from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import create_user, require_admin, require_auth
from news_dashboard.db import connect
from news_dashboard.ingest import sync_sources
from news_dashboard.main import app


def _make_user(database_url: str, username: str = "alice") -> int:
    user = create_user(username, "pw", db_path=database_url)
    return int(user["id"])


@contextmanager
def _api_client(user_id: int) -> Generator[TestClient]:
    fake = {"id": user_id, "username": "testuser", "email": None, "is_admin": False}
    app.dependency_overrides[require_auth] = lambda: fake
    app.dependency_overrides[require_admin] = lambda: fake
    try:
        with TestClient(app, raise_server_exceptions=True) as client:
            yield client
    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(require_admin, None)


def test_onboarding_interest_options_are_stable(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.get("/api/onboarding/interests")

    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    option_ids = {item["id"] for item in items}
    assert {"agents", "model-releases", "evals", "infra", "python", "cloud"} <= option_ids
    for item in items:
        assert "id" in item
        assert "label" in item
        assert "description" in item


def test_onboarding_status_incomplete_for_new_user(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.get("/api/onboarding/status")

    assert response.status_code == 200
    assert response.json() == {"completed": False}


def test_onboarding_status_complete_after_profile_save(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        client.post(
            "/api/onboarding/profile",
            json={"interest_ids": ["agents"], "enabled_slugs": []},
        )
        response = client.get("/api/onboarding/status")

    assert response.status_code == 200
    assert response.json() == {"completed": True}


def test_onboarding_recommendations_post_returns_ranked_sources(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.post(
            "/api/onboarding/recommendations",
            json={"interest_ids": ["agents", "python"]},
        )

    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    assert len(items) > 0
    slugs = {item["slug"] for item in items}
    assert "langgraph-releases" in slugs
    first = items[0]
    assert "slug" in first
    assert "name" in first
    assert "recommended" in first


def test_save_onboarding_profile_persists_and_marks_complete(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.post(
            "/api/onboarding/profile",
            json={"interest_ids": ["agents", "python"], "enabled_slugs": ["langgraph-releases"]},
        )

    assert response.status_code == 200
    assert response.json() == {"completed": True}
    with connect(pg_clean) as conn:
        profile = conn.execute(
            "SELECT interests, completed_at FROM user_interest_profiles WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        sub = conn.execute(
            "SELECT enabled FROM user_sources"
            " WHERE user_id = %s AND source_slug = 'langgraph-releases'",
            (user_id,),
        ).fetchone()
    assert profile is not None
    assert profile["interests"] == ["agents", "python"]
    assert profile["completed_at"] is not None
    assert sub is not None
    assert sub["enabled"] is True


def test_onboarding_recommendations_rank_matches_and_subscription_state(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    user_id = _make_user(pg_clean)
    with connect(pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO user_interest_profiles(user_id, interests)
            VALUES (%s, '["agents", "python"]'::jsonb)
            """,
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO user_sources(user_id, source_slug, enabled)
            VALUES (%s, 'langgraph-releases', TRUE)
            """,
            (user_id,),
        )

    with _api_client(user_id) as client:
        response = client.get("/api/onboarding/source-recommendations")

    assert response.status_code == 200
    items = response.json()["items"]
    langgraph = next(item for item in items if item["source_slug"] == "langgraph-releases")
    assert langgraph["recommended"] is True
    assert langgraph["subscribed"] is True
    assert langgraph["matched_interests"] == ["agents", "python"]
    assert items.index(langgraph) < 5


def test_save_onboarding_interests_persists_profile_and_source_choices(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    user_id = _make_user(pg_clean)

    with _api_client(user_id) as client:
        response = client.post(
            "/api/onboarding/interests",
            json={
                "interests": ["agents", "python"],
                "enabled_source_slugs": ["langgraph-releases"],
                "disabled_source_slugs": ["openai-blog"],
            },
        )

    assert response.status_code == 200
    assert response.json()["interests"] == ["agents", "python"]
    with connect(pg_clean) as conn:
        profile = conn.execute(
            "SELECT interests, completed_at FROM user_interest_profiles WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        subscriptions = conn.execute(
            """
            SELECT source_slug, enabled
            FROM user_sources
            WHERE user_id = %s AND source_slug IN ('langgraph-releases', 'openai-blog')
            """,
            (user_id,),
        ).fetchall()

    assert profile is not None
    assert profile["interests"] == ["agents", "python"]
    assert profile["completed_at"] is not None
    assert {row["source_slug"]: row["enabled"] for row in subscriptions} == {
        "langgraph-releases": True,
        "openai-blog": False,
    }


def test_new_user_has_no_explicit_global_source_subscriptions(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    sync_sources(pg_clean)
    user_id = _make_user(pg_clean)

    with connect(pg_clean) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM user_sources WHERE user_id = %s",
            (user_id,),
        ).fetchone()["count"]

    assert count == 0
