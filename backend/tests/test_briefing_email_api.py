"""API tests for briefing-email unsubscribe and preview."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from news_dashboard.auth import create_user, require_auth
from news_dashboard.briefing_email import service
from news_dashboard.briefing_email.tokens import make_unsubscribe_token
from news_dashboard.db import connect
from news_dashboard.main import app


def _user(
    database_url: str,
    name: str,
    *,
    email: str | None = "reader@example.com",
    is_guest: bool = False,
) -> int:
    user_id = int(create_user(name, "password123", db_path=database_url, is_guest=is_guest)["id"])
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


def test_preview_hydrates_cited_article_links(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("NEWS_DASHBOARD_URL", "https://news.example")
    user_id = _user(pg_clean, "preview_sources")
    with connect(database_url=pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, enabled, kind)
            VALUES ('source-test', 'Source Test', 'https://source.example',
                    'tech', TRUE, 'rss_feed')
            """
        )
        article = conn.execute(
            """
            INSERT INTO articles(url, canonical_url, title, source_slug, source_name,
                                 category, kind, state)
            VALUES ('https://source.example/story', 'https://source.example/story',
                    'Source story', 'source-test', 'Source Test', 'tech', 'rss_feed', 'today')
            RETURNING id
            """
        ).fetchone()
        assert article is not None
        article_id = int(article["id"])
        briefing = conn.execute(
            """
            INSERT INTO briefings(user_id, status, title, summary, content)
            VALUES (%s, 'complete', 'Daily', 'Summary', %s::jsonb) RETURNING id
            """,
            (
                user_id,
                json.dumps(
                    {"sections": [{"title": "AI", "body": "News", "citations": [article_id]}]}
                ),
            ),
        ).fetchone()
        assert briefing is not None
        conn.execute(
            "INSERT INTO briefing_articles(briefing_id, article_id) VALUES (%s, %s)",
            (int(briefing["id"]), article_id),
        )
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(service, "send_email", lambda **kwargs: sent.append(kwargs))

    response = _client_for(pg_clean, user_id).post("/api/settings/notifications/email/preview")

    assert response.status_code == 200
    assert "https://source.example/story" in sent[0]["html_body"]


def test_preview_requires_account_email(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _user(pg_clean, "no_email", email=None)
    _complete_briefing(pg_clean, user_id)
    response = _client_for(pg_clean, user_id).post("/api/settings/notifications/email/preview")
    assert response.status_code == 400


def test_preview_rejects_guest_account_inside_service(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _user(pg_clean, "guest_preview", is_guest=True)
    _complete_briefing(pg_clean, user_id)
    response = _client_for(pg_clean, user_id).post("/api/settings/notifications/email/preview")
    assert response.status_code == 400


def test_preview_requires_complete_briefing(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    user_id = _user(pg_clean, "no_briefing")
    response = _client_for(pg_clean, user_id).post("/api/settings/notifications/email/preview")
    assert response.status_code == 404


def test_preview_has_per_user_cooldown(pg_clean: str, monkeypatch: Any) -> None:
    monkeypatch.setattr(service, "_preview_sent_at", type(service._preview_sent_at)())
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("NEWS_DASHBOARD_URL", "https://news.example")
    user_id = _user(pg_clean, "cooldown")
    _complete_briefing(pg_clean, user_id)
    monkeypatch.setattr(service, "send_email", lambda **_: None)
    client = _client_for(pg_clean, user_id)

    first = client.post("/api/settings/notifications/email/preview")
    second = client.post("/api/settings/notifications/email/preview")

    assert first.status_code == 200
    assert second.status_code == 429


def test_preview_cooldown_is_scoped_to_database_identity(monkeypatch: Any) -> None:
    monkeypatch.setattr(service, "_preview_sent_at", type(service._preview_sent_at)())
    user_id = 7
    first_database = "postgresql://localhost/first"
    second_database = "postgresql://localhost/second"

    first_key = service._claim_preview_cooldown(user_id, database_url=first_database)
    with pytest.raises(service.PreviewCooldownError):
        service._claim_preview_cooldown(user_id, database_url=first_database)

    service._claim_preview_cooldown(user_id, database_url=second_database)
    service._release_preview_cooldown(first_key)

    service._claim_preview_cooldown(user_id, database_url=first_database)
    with pytest.raises(service.PreviewCooldownError):
        service._claim_preview_cooldown(user_id, database_url=second_database)


def test_preview_cooldown_resolves_split_postgres_configuration(monkeypatch: Any) -> None:
    monkeypatch.setattr(service, "_preview_sent_at", type(service._preview_sent_at)())
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_HOST", "first-db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "news")
    monkeypatch.setenv("POSTGRES_USER", "reader")
    monkeypatch.setenv("POSTGRES_PASSWORD", "password")
    user_id = 7

    service._claim_preview_cooldown(user_id)
    monkeypatch.setenv("POSTGRES_HOST", "second-db.internal")
    service._claim_preview_cooldown(user_id)

    with pytest.raises(service.PreviewCooldownError):
        service._claim_preview_cooldown(user_id)


def test_preview_failure_releases_claim_after_database_environment_changes(
    pg_clean: str, monkeypatch: Any
) -> None:
    monkeypatch.setattr(service, "_preview_sent_at", type(service._preview_sent_at)())
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("NEWS_DASHBOARD_URL", "https://news.example")
    user_id = _user(pg_clean, "release_changed_environment")
    _complete_briefing(pg_clean, user_id)

    def fail_delivery(**_: Any) -> str:
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/changed")
        return "delivery_failed"

    monkeypatch.setattr(service, "send_email", fail_delivery)

    with pytest.raises(service.PreviewUnavailableError):
        service.send_preview(user_id)

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    service._claim_preview_cooldown(user_id)
