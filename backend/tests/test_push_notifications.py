"""Tests for push notification endpoints and helper functions."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from news_dashboard.db import POSTGRES_MULTIUSER_SCHEMA, init_db
from news_dashboard.main import app
from news_dashboard.push import (
    delete_push_subscriptions,
    generate_push_hook,
    get_user_push_subscriptions,
    save_push_subscription,
    send_push_for_user,
    validate_push_subscription,
)


@pytest.fixture
def client() -> Generator[TestClient]:
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


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


def test_send_push_notification_payload_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import news_dashboard.push as push_mod

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

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
            title="T",
            body="B",
        )

    payload = json.loads(mock_webpush.call_args.kwargs["data"])
    assert payload == {"title": "T", "body": "B"}
    assert "url" not in payload


def test_send_push_notification_payload_with_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import news_dashboard.push as push_mod

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

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
            title="T",
            body="B",
            target_url="/briefs/42",
        )

    payload = json.loads(mock_webpush.call_args.kwargs["data"])
    assert payload == {"title": "T", "body": "B", "url": "/briefs/42"}


def test_send_push_notification_payload_with_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    import news_dashboard.push as push_mod

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

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
            title="T",
            body="B",
            target_url="/shared",
            tag="shared-article",
        )

    payload = json.loads(mock_webpush.call_args.kwargs["data"])
    assert payload == {"title": "T", "body": "B", "url": "/shared", "tag": "shared-article"}


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


def test_notify_share_recipient_routes_push_to_shared_inbox() -> None:
    from news_dashboard.main import _notify_share_recipient

    with patch("news_dashboard.push.send_push_for_user") as mock_send:
        _notify_share_recipient(
            to_user_id=42,
            sender="alice",
            article_title="Interesting article",
        )

    mock_send.assert_called_once_with(
        42,
        "alice shared an article",
        "Interesting article",
        target_url="/shared",
        tag="shared-article",
    )


# ── API endpoints ──────────────────────────────────────────────────────────────


def test_get_notification_settings_returns_defaults(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BExampleKey==")

    fake_row: dict[str, Any] = {
        "briefing_time": "09:00",
        "briefing_push_enabled": False,
        "briefing_timezone": "UTC",
    }

    with patch("news_dashboard.main.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        resp = client.get("/api/settings/notifications")

    assert resp.status_code == 200
    data = resp.json()
    assert data["briefing_time"] == "09:00"
    assert data["briefing_timezone"] == "UTC"
    assert data["push_enabled"] is False
    assert data["vapid_public_key"] == "BExampleKey=="


def test_get_notification_settings_utc_fallback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Users without a timezone value fall back to UTC."""
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BExampleKey==")

    fake_row: dict[str, Any] = {
        "briefing_time": "09:00",
        "briefing_push_enabled": False,
        "briefing_timezone": None,
    }

    with patch("news_dashboard.main.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        resp = client.get("/api/settings/notifications")

    assert resp.status_code == 200
    assert resp.json()["briefing_timezone"] == "UTC"


def test_put_notification_settings_valid_time(client: TestClient) -> None:
    fake_row: dict[str, Any] = {
        "briefing_time": "08:30",
        "briefing_push_enabled": True,
        "briefing_timezone": "UTC",
    }

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


def test_put_notification_settings_valid_timezone(client: TestClient) -> None:
    fake_row: dict[str, Any] = {
        "briefing_time": "09:00",
        "briefing_push_enabled": False,
        "briefing_timezone": "Europe/Bucharest",
    }

    with patch("news_dashboard.main.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        resp = client.put(
            "/api/settings/notifications",
            json={"briefing_timezone": "Europe/Bucharest"},
        )

    assert resp.status_code == 200
    assert resp.json()["briefing_timezone"] == "Europe/Bucharest"


def test_put_notification_settings_invalid_timezone(client: TestClient) -> None:
    resp = client.put("/api/settings/notifications", json={"briefing_timezone": "Mars/Olympus"})
    assert resp.status_code == 422


def test_put_notification_settings_invalid_time(client: TestClient) -> None:
    resp = client.put("/api/settings/notifications", json={"briefing_time": "25:00"})
    assert resp.status_code == 422


def test_push_subscribe_endpoint(client: TestClient) -> None:
    with patch("news_dashboard.push.save_push_subscription") as mock_save:
        resp = client.post(
            "/api/notifications/subscribe",
            json={"endpoint": "https://ep.example.com", "p256dh": "abc", "auth": "xyz"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"subscribed": True}
    mock_save.assert_called_once_with(1, "https://ep.example.com", "abc", "xyz")


def test_push_unsubscribe_endpoint(client: TestClient) -> None:
    with patch("news_dashboard.push.delete_push_subscriptions") as mock_del:
        resp = client.delete("/api/notifications/subscribe")
    assert resp.status_code == 200
    assert resp.json() == {"unsubscribed": True}
    mock_del.assert_called_once_with(1)


# ── validate_push_subscription unit tests ─────────────────────────────────────


def test_validate_push_subscription_accepts_valid() -> None:
    # Real-shaped Chrome FCM and Firefox Mozilla push endpoints
    validate_push_subscription(
        "https://fcm.googleapis.com/fcm/send/abcdefgh",
        "BNQtHLiP_xyz-base64url",
        "authkeyABC",
    )
    validate_push_subscription(
        "https://updates.push.services.mozilla.com/push/v1/someid",
        "BNQtHLiP_xyz-base64url",
        "authkeyABC",
    )


def test_validate_push_subscription_rejects_http_scheme() -> None:
    with pytest.raises(ValueError, match="https"):
        validate_push_subscription("http://ep.example.com/push", "key", "auth")


def test_validate_push_subscription_rejects_relative_url() -> None:
    with pytest.raises(ValueError, match="https"):
        validate_push_subscription("/push/v1/endpoint", "key", "auth")


def test_validate_push_subscription_rejects_empty_endpoint() -> None:
    with pytest.raises(ValueError, match="https"):
        validate_push_subscription("", "key", "auth")


def test_validate_push_subscription_rejects_localhost() -> None:
    with pytest.raises(ValueError, match="non-public"):
        validate_push_subscription("https://127.0.0.1/push", "key", "auth")


def test_validate_push_subscription_rejects_loopback_ipv6() -> None:
    with pytest.raises(ValueError, match="non-public"):
        validate_push_subscription("https://[::1]/push", "key", "auth")


def test_validate_push_subscription_rejects_private_ip() -> None:
    with pytest.raises(ValueError, match="non-public"):
        validate_push_subscription("https://192.168.1.1/push", "key", "auth")


def test_validate_push_subscription_rejects_link_local() -> None:
    with pytest.raises(ValueError, match="non-public"):
        validate_push_subscription("https://169.254.1.1/push", "key", "auth")


def test_validate_push_subscription_rejects_empty_p256dh() -> None:
    with pytest.raises(ValueError, match="p256dh"):
        validate_push_subscription("https://ep.example.com/push", "", "auth")


def test_validate_push_subscription_rejects_empty_auth() -> None:
    with pytest.raises(ValueError, match="auth"):
        validate_push_subscription("https://ep.example.com/push", "key", "")


def test_validate_push_subscription_rejects_oversized_endpoint() -> None:
    with pytest.raises(ValueError, match="too long"):
        validate_push_subscription("https://ep.example.com/" + "a" * 2100, "key", "auth")


def test_validate_push_subscription_rejects_non_base64url_p256dh() -> None:
    with pytest.raises(ValueError, match="base64url"):
        validate_push_subscription("https://ep.example.com/push", "key with spaces!", "auth")


def test_validate_push_subscription_rejects_non_base64url_auth() -> None:
    with pytest.raises(ValueError, match="base64url"):
        validate_push_subscription("https://ep.example.com/push", "validkey", "auth with spaces!")


# ── Subscribe endpoint validation integration ──────────────────────────────────


def test_push_subscribe_endpoint_rejects_http_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/notifications/subscribe",
        json={"endpoint": "http://ep.example.com/push", "p256dh": "abc", "auth": "xyz"},
    )
    assert resp.status_code == 422


def test_push_subscribe_endpoint_rejects_private_ip(client: TestClient) -> None:
    resp = client.post(
        "/api/notifications/subscribe",
        json={"endpoint": "https://10.0.0.1/push", "p256dh": "abc", "auth": "xyz"},
    )
    assert resp.status_code == 422


def test_push_subscribe_endpoint_rejects_empty_keys(client: TestClient) -> None:
    resp = client.post(
        "/api/notifications/subscribe",
        json={"endpoint": "https://ep.example.com/push", "p256dh": "", "auth": "xyz"},
    )
    assert resp.status_code == 422


def test_push_subscribe_endpoint_rejects_localhost(client: TestClient) -> None:
    resp = client.post(
        "/api/notifications/subscribe",
        json={"endpoint": "https://127.0.0.1/push", "p256dh": "abc", "auth": "xyz"},
    )
    assert resp.status_code == 422


@pytest.mark.postgres
def test_send_push_for_user_prunes_expired_endpoints(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")
    init_db(database_url=pg_clean)
    from news_dashboard.auth import create_user

    user = create_user("pushuser7", "pass")
    uid = int(user["id"])

    ep_success = "https://ep-success.example.com"
    ep_gone = "https://ep-gone.example.com"
    ep_transient = "https://ep-transient.example.com"

    save_push_subscription(uid, ep_success, "k1", "a1", database_url=pg_clean)
    save_push_subscription(uid, ep_gone, "k2", "a2", database_url=pg_clean)
    save_push_subscription(uid, ep_transient, "k3", "a3", database_url=pg_clean)

    class _FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    class _FakeWebPushError(Exception):
        def __init__(self, message: str, response: Any = None) -> None:
            super().__init__(message)
            self.response = response

    def mock_webpush(subscription_info: dict[str, Any], **kwargs: Any) -> None:
        endpoint = subscription_info["endpoint"]
        if endpoint == ep_gone:
            msg = "Gone"
            raise _FakeWebPushError(msg, response=_FakeResponse(410))
        if endpoint == ep_transient:
            msg = "Server Error"
            raise _FakeWebPushError(msg, response=_FakeResponse(500))

    fake_module: dict[str, Any] = {
        "webpush": mock_webpush,
        "WebPushException": _FakeWebPushError,
    }
    with patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}):
        send_push_for_user(uid, "Title", "Body", database_url=pg_clean)

    remaining = get_user_push_subscriptions(uid, database_url=pg_clean)
    endpoints = {sub["endpoint"] for sub in remaining}
    assert ep_success in endpoints
    assert ep_transient in endpoints
    assert ep_gone not in endpoints


# ── generate_push_hook ─────────────────────────────────────────────────────────


def _make_briefing(
    title: str = "Tech Digest",
    sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": 1,
        "title": title,
        "content": {
            "sections": sections
            or [
                {"title": "Claude 4 released", "body": "...", "citations": []},
                {"title": "Markets hit record high", "body": "...", "citations": []},
            ]
        },
    }


def test_generate_push_hook_returns_llm_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    hook_text = "Claude 4 drops; markets soar — your brief awaits"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=hook_text))]
    )

    with (
        patch("news_dashboard.ai_client.get_chat_client", return_value=mock_client),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        result = generate_push_hook(_make_briefing())

    assert result == hook_text
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["max_tokens"] == 40
    assert "Claude 4 released" in call_kwargs["messages"][0]["content"]


def test_generate_push_hook_falls_back_on_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("LLM unavailable")

    with (
        patch("news_dashboard.ai_client.get_chat_client", return_value=mock_client),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        result = generate_push_hook(_make_briefing(title="Morning Brief"))

    assert result == "Your daily brief: Morning Brief"


def test_generate_push_hook_falls_back_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with patch("news_dashboard.ai_client.free_llm_config", return_value=("", None)):
        result = generate_push_hook(_make_briefing(title="Evening Digest"))

    assert result == "Your daily brief: Evening Digest"


def test_generate_push_hook_fallback_no_title() -> None:
    with patch("news_dashboard.ai_client.free_llm_config", return_value=("", None)):
        result = generate_push_hook({"title": "", "content": {"sections": []}})

    assert result == "Your daily brief is ready"


def test_generate_push_hook_uses_section_titles_in_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    captured_prompt: list[str] = []

    def fake_create(**kwargs: Any) -> Any:
        captured_prompt.append(kwargs["messages"][0]["content"])
        return MagicMock(
            choices=[MagicMock(message=MagicMock(content="Breaking: AI takes over coding"))]
        )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = fake_create

    sections = [
        {"title": "AI milestone achieved", "body": "", "citations": []},
        {"title": "Economy grows 3%", "body": "", "citations": []},
        {"title": "Sports finals tonight", "body": "", "citations": []},
        {"title": "This one should be excluded", "body": "", "citations": []},
    ]

    with (
        patch("news_dashboard.ai_client.get_chat_client", return_value=mock_client),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        generate_push_hook(_make_briefing(sections=sections))

    prompt = captured_prompt[0]
    assert "AI milestone achieved" in prompt
    assert "Economy grows 3%" in prompt
    assert "Sports finals tonight" in prompt
    assert "This one should be excluded" not in prompt
