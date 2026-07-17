"""API tests for briefing-email unsubscribe and preview."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from news_dashboard.auth import create_user, require_auth
from news_dashboard.briefing_email import service
from news_dashboard.briefing_email.tokens import make_unsubscribe_token
from news_dashboard.db import connect
from news_dashboard.main import app


def _user(database_url: str, name: str, *, email: str | None = "reader@example.com") -> int:
    user_id = int(create_user(name, "password123", db_path=database_url)["id"])
    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE users SET email = %s, briefing_email_enabled = TRUE WHERE id = %s",
            (email, user_id),
        )
    return user_id


def _complete_briefing(database_url: str, user_id: int) -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(user_id, status, title, summary, content)
            VALUES (%s, 'complete', 'Morning news', 'What matters', %s::jsonb)
            RETURNING id
            """,
            (user_id, '{"sections": []}'),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def _client_for(database_url: str, user_id: int) -> TestClient:
    app.dependency_overrides[require_auth] = lambda: {
        "id": user_id,
        "email": "reader@example.com",
        "is_admin": False,
    }
    return TestClient(app)


def test_unsubscribe_get_and_post_are_idempotent(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _user(pg_clean, "unsubscribe")
    token = make_unsubscribe_token(user_id)
    client = _client_for(pg_clean, user_id)

    first = client.get("/email/briefing/unsubscribe", params={"token": token})
    second = client.get("/email/briefing/unsubscribe", params={"token": token})
    one_click = client.post(
        "/email/briefing/unsubscribe",
        params={"token": token},
        data={"List-Unsubscribe": "One-Click"},
    )

    assert first.status_code == second.status_code == one_click.status_code == 200
    assert "unsubscribed" in first.text.lower()
    assert one_click.content == b""
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT briefing_email_enabled FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    assert row is not None
    assert row["briefing_email_enabled"] is False


def test_unsubscribe_rejects_invalid_token(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    response = TestClient(app).get("/email/briefing/unsubscribe", params={"token": "not-a-token"})
    assert response.status_code == 400


def test_preview_sends_latest_complete_briefing_without_changing_state(
    pg_clean: str, monkeypatch: Any
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("NEWS_DASHBOARD_URL", "https://news.example")
    user_id = _user(pg_clean, "preview")
    briefing_id = _complete_briefing(pg_clean, user_id)
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(service, "send_email", lambda **kwargs: sent.append(kwargs))

    response = _client_for(pg_clean, user_id).post("/api/settings/notifications/email/preview")

    assert response.status_code == 200
    assert response.json() == {"sent": True}
    assert sent[0]["recipient"] == "reader@example.com"
    assert "unsubscribe?token=" in sent[0]["html_body"]
    assert sent[0]["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    with connect(database_url=pg_clean) as conn:
        enabled = conn.execute(
            "SELECT briefing_email_enabled FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        deliveries = conn.execute(
            "SELECT count(*) AS count FROM briefing_email_deliveries WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    assert enabled is not None
    assert enabled["briefing_email_enabled"] is True
    assert deliveries is not None
    assert deliveries["count"] == 0
    assert f"/briefings/{briefing_id}" in sent[0]["html_body"]


def test_preview_requires_account_email(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _user(pg_clean, "no_email", email=None)
    _complete_briefing(pg_clean, user_id)
    response = _client_for(pg_clean, user_id).post("/api/settings/notifications/email/preview")
    assert response.status_code == 400


def test_preview_requires_complete_briefing(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _user(pg_clean, "no_briefing")
    response = _client_for(pg_clean, user_id).post("/api/settings/notifications/email/preview")
    assert response.status_code == 404


def test_preview_has_per_user_cooldown(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _user(pg_clean, "cooldown")
    _complete_briefing(pg_clean, user_id)
    monkeypatch.setattr(service, "send_email", lambda **_: None)
    client = _client_for(pg_clean, user_id)

    first = client.post("/api/settings/notifications/email/preview")
    second = client.post("/api/settings/notifications/email/preview")

    assert first.status_code == 200
    assert second.status_code == 429
