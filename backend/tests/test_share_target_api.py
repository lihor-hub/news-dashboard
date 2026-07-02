from __future__ import annotations

from fastapi.testclient import TestClient

from news_dashboard.db import connect
from news_dashboard.main import app


def _seed_fake_user(database_url: str) -> None:
    with connect(database_url) as conn:
        conn.execute(
            """
            INSERT INTO users(id, username, password_hash, is_admin)
            VALUES (1, 'testadmin', 'hash', true)
            ON CONFLICT (id) DO NOTHING
            """
        )


def test_save_shared_url_creates_article_for_current_user(pg_clean: str) -> None:
    _seed_fake_user(pg_clean)
    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.post(
            "/api/articles/save-url",
            json={
                "url": "https://example.com/shared-post",
                "title": "Shared Post",
                "text": "A note from the share sheet",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/shared-post"
    assert data["title"] == "Shared Post"
    assert data["state"] == "today"

    with connect(pg_clean) as conn:
        state = conn.execute(
            "SELECT state FROM user_article_state WHERE user_id = %s AND article_id = %s",
            (1, data["id"]),
        ).fetchone()
    assert state is not None
    assert state["state"] == "today"


def test_save_shared_url_rejects_unsafe_url(pg_clean: str) -> None:
    _seed_fake_user(pg_clean)
    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.post(
            "/api/articles/save-url",
            json={"url": "file:///etc/passwd", "title": "Nope"},
        )

    assert response.status_code == 422
