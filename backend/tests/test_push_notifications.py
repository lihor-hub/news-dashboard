"""Tests for push notification endpoints and helper functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.db import POSTGRES_MULTIUSER_SCHEMA, init_db
from news_dashboard.main import app
from news_dashboard.push import (
    delete_push_subscriptions,
    get_user_push_subscriptions,
    save_push_subscription,
    send_push_for_user,
)

client = TestClient(app, raise_server_exceptions=True)

# ── Schema ─────────────────────────────────────────────────────────────────────


def test_user_push_subscriptions_table_in_schema() -> None:
    combined = "\n".join(POSTGRES_MULTIUSER_SCHEMA)
    assert "user_push_subscriptions" in combined


def test_users_briefing_time_column_in_schema() -> None:
    combined = "\n".join(POSTGRES_MULTIUSER_SCHEMA)
    assert "briefing_time" in combined


def test_users_briefing_push_enabled_column_in_schema() -> None:
    combined = "\n".join(POSTGRES_MULTIUSER_SCHEMA)
    assert "briefing_push_enabled" in combined


# ── Push subscription CRUD (integration) ──────────────────────────────────────


@pytest.mark.postgres
def test_save_and_retrieve_push_subscription(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    from news_dashboard.auth import create_user

    user = create_user("pushuser1", "pass")
    uid = int(user["id"])

    save_push_subscription(
        uid,
        "https://example.com/push/abc",
        "p256dh_key_value",
        "auth_key_value",
        database_url=pg_clean,
    )

    subs = get_user_push_subscriptions(uid, database_url=pg_clean)
    assert len(subs) == 1
    assert subs[0]["endpoint"] == "https://example.com/push/abc"
    assert subs[0]["p256dh_key"] == "p256dh_key_value"
    assert subs[0]["auth_key"] == "auth_key_value"


@pytest.mark.postgres
def test_upsert_push_subscription_updates_on_conflict(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    from news_dashboard.auth import create_user

    user = create_user("pushuser2", "pass")
    uid = int(user["id"])

    save_push_subscription(
        uid, "https://example.com/ep", "old_key", "old_auth", database_url=pg_clean
    )
    save_push_subscription(
        uid, "https://example.com/ep", "new_key", "new_auth", database_url=pg_clean
    )

    subs = get_user_push_subscriptions(uid, database_url=pg_clean)
    assert len(subs) == 1
    assert subs[0]["p256dh_key"] == "new_key"


@pytest.mark.postgres
def test_delete_push_subscriptions_removes_all(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    from news_dashboard.auth import create_user

    user = create_user("pushuser3", "pass")
    uid = int(user["id"])

    save_push_subscription(uid, "https://ep1.example.com", "k1", "a1", database_url=pg_clean)
    save_push_subscription(uid, "https://ep2.example.com", "k2", "a2", database_url=pg_clean)

    delete_push_subscriptions(uid, database_url=pg_clean)
    assert get_user_push_subscriptions(uid, database_url=pg_clean) == []


@pytest.mark.postgres
def test_delete_push_subscription_by_endpoint(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    from news_dashboard.auth import create_user

    user = create_user("pushuser4", "pass")
    uid = int(user["id"])

    save_push_subscription(uid, "https://ep1.example.com", "k1", "a1", database_url=pg_clean)
    save_push_subscription(uid, "https://ep2.example.com", "k2", "a2", database_url=pg_clean)

    delete_push_subscriptions(uid, endpoint="https://ep1.example.com", database_url=pg_clean)
    subs = get_user_push_subscriptions(uid, database_url=pg_clean)
    assert len(subs) == 1
    assert subs[0]["endpoint"] == "https://ep2.example.com"


# ── send_push_notification ─────────────────────────────────────────────────────


def test_send_push_notification_calls_webpush(monkeypatch: pytest.MonkeyPatch) -> None:
    import news_dashboard.push as push_mod

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")
    monkeypatch.setenv("VAPID_EMAIL", "test@example.com")

    mock_webpush = MagicMock()

    class _FakeWebPushError(Exception):
        pass

    fake_module: dict[str, Any] = {
        "webpush": mock_webpush,
        "WebPushException": _FakeWebPushError,
    }
    with patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}):
        push_mod.send_push_notification(
            endpoint="https://ep.example.com",
            p256dh="abc",
            auth="xyz",
            title="Test",
            body="Hello",
        )

    mock_webpush.assert_called_once()
    call_kwargs = mock_webpush.call_args.kwargs
    assert call_kwargs["subscription_info"]["endpoint"] == "https://ep.example.com"
    assert call_kwargs["vapid_claims"]["sub"] == "mailto:test@example.com"


def test_send_push_notification_logs_on_webpush_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import news_dashboard.push as push_mod

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

    class _FakeWebPushError(Exception):
        pass

    mock_webpush = MagicMock(side_effect=_FakeWebPushError("push failed"))
    fake_module: dict[str, Any] = {
        "webpush": mock_webpush,
        "WebPushException": _FakeWebPushError,
    }
    with patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}):
        push_mod.send_push_notification(
            endpoint="https://ep.example.com",
            p256dh="abc",
            auth="xyz",
            title="T",
            body="B",
        )


@pytest.mark.postgres
def test_send_push_for_user_with_no_subscriptions(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    from news_dashboard.auth import create_user

    user = create_user("pushuser5", "pass")
    uid = int(user["id"])

    with patch("news_dashboard.push.send_push_notification") as mock_send:
        send_push_for_user(uid, "Title", "Body", database_url=pg_clean)
    mock_send.assert_not_called()


@pytest.mark.postgres
def test_send_push_for_user_calls_send_for_each_sub(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    init_db(database_url=pg_clean)
    from news_dashboard.auth import create_user

    user = create_user("pushuser6", "pass")
    uid = int(user["id"])

    save_push_subscription(uid, "https://ep1.example.com", "k1", "a1", database_url=pg_clean)
    save_push_subscription(uid, "https://ep2.example.com", "k2", "a2", database_url=pg_clean)

    with patch("news_dashboard.push.send_push_notification") as mock_send:
        send_push_for_user(uid, "Brief ready", "", database_url=pg_clean)

    assert mock_send.call_count == 2


# ── API endpoints ──────────────────────────────────────────────────────────────


def test_get_notification_settings_returns_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BExampleKey==")

    fake_row: dict[str, Any] = {"briefing_time": "09:00", "briefing_push_enabled": False}

    with patch("news_dashboard.main.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        resp = client.get("/api/settings/notifications")

    assert resp.status_code == 200
    data = resp.json()
    assert data["briefing_time"] == "09:00"
    assert data["push_enabled"] is False
    assert data["vapid_public_key"] == "BExampleKey=="


def test_put_notification_settings_valid_time() -> None:
    fake_row: dict[str, Any] = {"briefing_time": "08:30", "briefing_push_enabled": True}

    with patch("news_dashboard.main.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        resp = client.put(
            "/api/settings/notifications",
            json={"briefing_time": "08:30", "push_enabled": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["briefing_time"] == "08:30"
    assert data["push_enabled"] is True


def test_put_notification_settings_invalid_time() -> None:
    resp = client.put("/api/settings/notifications", json={"briefing_time": "25:00"})
    assert resp.status_code == 422


def test_push_subscribe_endpoint() -> None:
    with patch("news_dashboard.push.save_push_subscription") as mock_save:
        resp = client.post(
            "/api/notifications/subscribe",
            json={"endpoint": "https://ep.example.com", "p256dh": "abc", "auth": "xyz"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"subscribed": True}
    mock_save.assert_called_once_with(1, "https://ep.example.com", "abc", "xyz")


def test_push_unsubscribe_endpoint() -> None:
    with patch("news_dashboard.push.delete_push_subscriptions") as mock_del:
        resp = client.delete("/api/notifications/subscribe")
    assert resp.status_code == 200
    assert resp.json() == {"unsubscribed": True}
    mock_del.assert_called_once_with(1)
