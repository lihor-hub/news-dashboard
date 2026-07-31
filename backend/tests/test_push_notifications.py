"""Tests for push notification endpoints and helper functions."""

from __future__ import annotations

import http.client
import socket
import threading
import time
import urllib.error
from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from news_dashboard.auth import create_user, require_auth
from news_dashboard.db import POSTGRES_MULTIUSER_SCHEMA, connect, init_db
from news_dashboard.email import smtp_configured
from news_dashboard.main import app
from news_dashboard.push import (
    _PinnedPushSession,
    delete_push_subscriptions,
    generate_push_hook,
    generate_recap_push_hook,
    get_user_push_subscriptions,
    save_push_subscription,
    send_push_for_user,
    send_push_notification,
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


def test_users_briefing_email_enabled_column_in_schema() -> None:
    combined = "\n".join(POSTGRES_MULTIUSER_SCHEMA)
    assert "briefing_email_enabled" in combined


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
        send_push_notification(
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


def test_push_delivery_fails_closed_without_pinned_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")
    mock_webpush = MagicMock()

    class _FakeWebPushError(Exception):
        pass

    fake_module: dict[str, Any] = {
        "webpush": mock_webpush,
        "WebPushException": _FakeWebPushError,
    }
    with patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}):
        send_push_notification(
            endpoint="https://push.example.com/delivery",
            p256dh="abc",
            auth="xyz",
            title="Test",
            body="Hello",
        )

    pinned_session = mock_webpush.call_args.kwargs.get("requests_session")
    assert pinned_session is not None

    def private_dns_answer(
        _host: str,
        port: int,
        _family: int = 0,
        _socket_type: int = 0,
        _protocol: int = 0,
        _flags: int = 0,
        **kwargs: int,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        del _family, _protocol, _flags
        socket_type = kwargs.get("type", _socket_type)
        return [(socket.AF_INET, socket_type, socket.IPPROTO_TCP, "", ("10.0.0.8", port))]

    monkeypatch.setattr("news_dashboard.url_safety.socket.getaddrinfo", private_dns_answer)
    with pytest.raises(ValueError, match="unsafe host address"):
        pinned_session.post("https://push.example.com/delivery", data=b"encrypted")


def test_push_delivery_classifies_pinned_transport_error_as_temporary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

    class _FakeWebPushError(Exception):
        pass

    def fake_webpush(**kwargs: Any) -> None:
        subscription_info = kwargs["subscription_info"]
        kwargs["requests_session"].post(
            subscription_info["endpoint"],
            data=b"encrypted",
            timeout=kwargs["timeout"],
        )

    fake_module: dict[str, Any] = {
        "webpush": fake_webpush,
        "WebPushException": _FakeWebPushError,
    }
    transport_error = urllib.error.URLError("push service unavailable")
    with (
        patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}),
        patch(
            "news_dashboard.push.open_server_fetch_url",
            side_effect=transport_error,
        ),
    ):
        result = send_push_notification(
            endpoint="https://push.example.com/delivery",
            p256dh="abc",
            auth="xyz",
            title="Test",
            body="Hello",
        )

    assert result == "temporary_failure"


class _SlowPushResponse:
    status = 201
    code = 201
    reason = "Created"

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.read_started = threading.Event()
        self.closed = threading.Event()

    def __enter__(self) -> _SlowPushResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def read(self, _size: int) -> bytes:
        self.read_started.set()
        self.closed.wait(timeout=2)
        return b""

    def close(self) -> None:
        self.closed.set()

    def geturl(self) -> str:
        return "https://push.example.com/delivery"


class _LockingPushResponse(_SlowPushResponse):
    def __init__(self) -> None:
        super().__init__()
        self.release_read = threading.Event()
        self._reader_lock = threading.Lock()

    def read(self, _size: int) -> bytes:
        with self._reader_lock:
            self.read_started.set()
            self.release_read.wait(timeout=2)
            return b""

    def close(self) -> None:
        with self._reader_lock:
            self.closed.set()


class _ImmediatePushResponse(_SlowPushResponse):
    def read(self, _size: int) -> bytes:
        self.read_started.set()
        return b""


def test_push_transport_bounds_slow_response_by_absolute_deadline() -> None:
    slow_response = _LockingPushResponse()
    started = time.monotonic()
    try:
        with (
            patch(
                "news_dashboard.push.open_server_fetch_url",
                return_value=slow_response,
            ),
            _PinnedPushSession() as session,
            pytest.raises(TimeoutError, match="deadline"),
        ):
            session.post(
                "https://push.example.com/delivery",
                data=b"encrypted",
                timeout=0.05,
            )
    finally:
        slow_response.release_read.set()

    assert slow_response.read_started.is_set()
    assert time.monotonic() - started < 0.5
    assert slow_response.closed.wait(timeout=0.5)


def test_push_transport_rejects_work_when_executor_is_saturated() -> None:
    stalled_responses = [_LockingPushResponse() for _ in range(4)]
    results: list[requests.Response] = []

    def send_stalled(response: _LockingPushResponse) -> None:
        with _PinnedPushSession() as session:
            results.append(
                session.post(
                    "https://push.example.com/delivery",
                    data=b"encrypted",
                    timeout=1,
                )
            )

    with patch(
        "news_dashboard.push.open_server_fetch_url",
        side_effect=stalled_responses,
    ) as opener:
        workers = [
            threading.Thread(target=send_stalled, args=(response,))
            for response in stalled_responses
        ]
        for worker in workers:
            worker.start()
        assert all(response.read_started.wait(timeout=0.5) for response in stalled_responses)

        started = time.monotonic()
        with (
            _PinnedPushSession() as session,
            pytest.raises(TimeoutError, match="capacity") as caught,
        ):
            session.post(
                "https://push.example.com/delivery",
                data=b"encrypted",
                headers={"Authorization": "Bearer secret-token"},
                timeout=1,
            )
        assert time.monotonic() - started < 0.2
        assert "secret-token" not in str(caught.value)
        assert opener.call_count == 4

        for response in stalled_responses:
            response.release_read.set()
        for worker in workers:
            worker.join(timeout=1)
        assert all(not worker.is_alive() for worker in workers)
        assert len(results) == 4

        opener.side_effect = None
        opener.return_value = _ImmediatePushResponse()
        with _PinnedPushSession() as session:
            recovered = session.post(
                "https://push.example.com/delivery",
                data=b"encrypted",
                timeout=1,
            )

    assert recovered.status_code == 201


def test_push_transport_bounds_response_open_by_absolute_deadline() -> None:
    open_started = threading.Event()
    release_open = threading.Event()

    def blocked_open(*_args: object, **_kwargs: object) -> _SlowPushResponse:
        open_started.set()
        release_open.wait(timeout=2)
        return _SlowPushResponse()

    started = time.monotonic()
    try:
        with (
            patch("news_dashboard.push.open_server_fetch_url", side_effect=blocked_open),
            _PinnedPushSession() as session,
            pytest.raises(TimeoutError, match="deadline"),
        ):
            session.post(
                "https://push.example.com/delivery",
                data=b"encrypted",
                timeout=0.05,
            )
    finally:
        release_open.set()

    assert open_started.is_set()
    assert time.monotonic() - started < 0.5


@pytest.mark.parametrize(
    "read_error",
    [
        TimeoutError("response read timed out"),
        http.client.IncompleteRead(b"partial", 20),
        ConnectionResetError("push service reset connection"),
    ],
)
def test_push_delivery_classifies_response_read_error_as_temporary(
    monkeypatch: pytest.MonkeyPatch,
    read_error: BaseException,
) -> None:
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

    class _ReadFailureResponse(_SlowPushResponse):
        def read(self, _size: int) -> bytes:
            raise read_error

    class _FakeWebPushError(Exception):
        pass

    def fake_webpush(**kwargs: Any) -> None:
        subscription_info = kwargs["subscription_info"]
        kwargs["requests_session"].post(
            subscription_info["endpoint"],
            data=b"encrypted",
            timeout=kwargs["timeout"],
        )

    fake_module: dict[str, Any] = {
        "webpush": fake_webpush,
        "WebPushException": _FakeWebPushError,
    }
    with (
        patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}),
        patch(
            "news_dashboard.push.open_server_fetch_url",
            return_value=_ReadFailureResponse(),
        ),
    ):
        result = send_push_notification(
            endpoint="https://push.example.com/delivery",
            p256dh="abc",
            auth="xyz",
            title="Test",
            body="Hello",
        )

    assert result == "temporary_failure"


def test_send_push_notification_payload_without_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

    mock_webpush = MagicMock()

    class _FakeWebPushError(Exception):
        pass

    fake_module: dict[str, Any] = {
        "webpush": mock_webpush,
        "WebPushException": _FakeWebPushError,
    }
    with patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}):
        send_push_notification(
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

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

    mock_webpush = MagicMock()

    class _FakeWebPushError(Exception):
        pass

    fake_module: dict[str, Any] = {
        "webpush": mock_webpush,
        "WebPushException": _FakeWebPushError,
    }
    with patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}):
        send_push_notification(
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

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

    mock_webpush = MagicMock()

    class _FakeWebPushError(Exception):
        pass

    fake_module: dict[str, Any] = {
        "webpush": mock_webpush,
        "WebPushException": _FakeWebPushError,
    }
    with patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}):
        send_push_notification(
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
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "fake-private-key")

    class _FakeWebPushError(Exception):
        pass

    mock_webpush = MagicMock(side_effect=_FakeWebPushError("push failed"))
    fake_module: dict[str, Any] = {
        "webpush": mock_webpush,
        "WebPushException": _FakeWebPushError,
    }
    with patch.dict("sys.modules", {"pywebpush": MagicMock(**fake_module)}):
        send_push_notification(
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
    from news_dashboard.shares.router import _notify_share_recipient

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
        "recap_enabled": True,
        "recap_day": "mon",
        "briefing_include_reading_list": False,
        "briefing_reading_list_limit": 3,
        "briefing_email_enabled": False,
        "email": "reader@example.com",
        "is_guest": False,
    }

    with (
        patch("news_dashboard.user_settings.service.connect") as mock_connect,
        patch("news_dashboard.user_settings.service.smtp_configured", return_value=False),
    ):
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        resp = client.get("/api/settings/notifications")

    assert resp.status_code == 200
    data = resp.json()
    assert data["briefing_time"] == "09:00"
    assert data["briefing_timezone"] == "UTC"
    assert data["push_enabled"] is False
    assert data["recap_enabled"] is True
    assert data["recap_day"] == "mon"
    assert data["vapid_public_key"] == "BExampleKey=="
    assert data["email_enabled"] is False
    assert data["email_address"] == "reader@example.com"
    assert data["email_available"] is True
    assert data["email_delivery_configured"] is False


def test_get_notification_settings_utc_fallback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Users without a timezone value fall back to UTC."""
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BExampleKey==")

    fake_row: dict[str, Any] = {
        "briefing_time": "09:00",
        "briefing_push_enabled": False,
        "briefing_timezone": None,
        "recap_enabled": True,
        "recap_day": "mon",
        "briefing_include_reading_list": False,
        "briefing_reading_list_limit": 3,
        "briefing_email_enabled": False,
        "email": None,
        "is_guest": False,
    }

    with patch("news_dashboard.user_settings.service.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        resp = client.get("/api/settings/notifications")

    assert resp.status_code == 200
    assert resp.json()["briefing_timezone"] == "UTC"


def test_get_notification_settings_whitespace_email_is_unavailable(client: TestClient) -> None:
    fake_row: dict[str, Any] = {
        "briefing_time": "09:00",
        "briefing_push_enabled": False,
        "briefing_timezone": "UTC",
        "recap_enabled": True,
        "recap_day": "mon",
        "briefing_include_reading_list": False,
        "briefing_reading_list_limit": 3,
        "briefing_email_enabled": False,
        "email": "   ",
        "is_guest": False,
    }
    with patch("news_dashboard.user_settings.service.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        response = client.get("/api/settings/notifications")

    assert response.status_code == 200
    assert response.json()["email_address"] is None
    assert response.json()["email_available"] is False


def test_put_notification_settings_valid_time(client: TestClient) -> None:
    fake_row: dict[str, Any] = {
        "briefing_time": "08:30",
        "briefing_push_enabled": True,
        "briefing_timezone": "UTC",
        "recap_enabled": True,
        "recap_day": "mon",
        "briefing_include_reading_list": False,
        "briefing_reading_list_limit": 3,
        "briefing_email_enabled": True,
        "email": "reader@example.com",
        "is_guest": False,
    }

    with patch("news_dashboard.user_settings.service.connect") as mock_connect:
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


def test_put_notification_settings_enables_email(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTP_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("OTP_SMTP_USER", "mailer@example.com")
    monkeypatch.setenv("OTP_SMTP_PASS", "secret")
    monkeypatch.setenv("NEWS_DASHBOARD_URL", "https://news.example")
    fake_row: dict[str, Any] = {
        "briefing_time": "09:00",
        "briefing_push_enabled": False,
        "briefing_timezone": "UTC",
        "recap_enabled": True,
        "recap_day": "mon",
        "briefing_include_reading_list": False,
        "briefing_reading_list_limit": 3,
        "briefing_email_enabled": True,
        "email": "reader@example.com",
        "is_guest": False,
    }
    with patch("news_dashboard.user_settings.service.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        response = client.put("/api/settings/notifications", json={"email_enabled": True})

    assert response.status_code == 200
    assert response.json()["email_enabled"] is True
    update = ctx.execute.call_args_list[1]
    assert "briefing_email_enabled = %s" in update.args[0]
    assert update.args[1] == [True, 1]


@pytest.mark.parametrize(
    ("email", "is_guest"),
    [(None, False), ("   ", False), ("guest@example.com", True)],
)
def test_notification_email_requires_account_email(
    client: TestClient, email: str | None, is_guest: bool
) -> None:
    fake_row = {"email": email, "is_guest": is_guest}
    with patch("news_dashboard.user_settings.service.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        response = client.put("/api/settings/notifications", json={"email_enabled": True})

    assert response.status_code == 422
    assert response.json()["detail"] == "account email is required"


def test_notification_email_requires_smtp_configuration(client: TestClient) -> None:
    fake_row = {"email": "reader@example.com", "is_guest": False}
    with (
        patch("news_dashboard.user_settings.service.connect") as mock_connect,
        patch("news_dashboard.user_settings.service.smtp_configured", return_value=False),
    ):
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        response = client.put("/api/settings/notifications", json={"email_enabled": True})

    assert response.status_code == 422
    assert response.json()["detail"] == "email delivery is not configured"


def test_notification_email_requires_public_application_url(client: TestClient) -> None:
    fake_row = {"email": "reader@example.com", "is_guest": False}
    with (
        patch("news_dashboard.user_settings.service.connect") as mock_connect,
        patch("news_dashboard.user_settings.service.smtp_configured", return_value=True),
        patch(
            "news_dashboard.user_settings.service.public_base_url_configured",
            return_value=False,
        ),
    ):
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row
        response = client.put("/api/settings/notifications", json={"email_enabled": True})

    assert response.status_code == 422
    assert response.json()["detail"] == "public application URL is not configured"


@pytest.mark.parametrize(
    "unsafe_url",
    ["https://news.example:bad", "https://user:pass@news.example", "https://news.example?q=1"],
)
def test_notification_email_opt_in_rejects_unsafe_public_origin(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, unsafe_url: str
) -> None:
    monkeypatch.setenv("APP_BASE_URL", unsafe_url)
    fake_row = {"email": "reader@example.com", "is_guest": False}
    with (
        patch("news_dashboard.user_settings.service.connect") as mock_connect,
        patch("news_dashboard.user_settings.service.smtp_configured", return_value=True),
    ):
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row
        response = client.put("/api/settings/notifications", json={"email_enabled": True})

    assert response.status_code == 422
    assert response.json()["detail"] == "public application URL is not configured"


def test_smtp_configured_returns_false_for_malformed_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTP_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("OTP_SMTP_USER", "mailer@example.com")
    monkeypatch.setenv("OTP_SMTP_PASS", "secret")
    monkeypatch.setenv("OTP_SMTP_PORT", "not-a-port")

    assert smtp_configured() is False


@pytest.mark.postgres
def test_put_notification_settings_persists_email_opt_in(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("OTP_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("OTP_SMTP_USER", "mailer@example.com")
    monkeypatch.setenv("OTP_SMTP_PASS", "secret")
    monkeypatch.setenv("NEWS_DASHBOARD_URL", "https://news.example")
    user = create_user(
        "email_settings_integration",
        "password123",
        email="reader@example.com",
        db_path=pg_clean,
    )
    user_id = int(user["id"])
    app.dependency_overrides[require_auth] = lambda: user
    try:
        with TestClient(app, raise_server_exceptions=True) as postgres_client:
            response = postgres_client.put(
                "/api/settings/notifications", json={"email_enabled": True}
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    with connect(database_url=pg_clean) as conn:
        row = conn.execute(
            "SELECT briefing_email_enabled FROM users WHERE id = %s", (user_id,)
        ).fetchone()
    assert row is not None
    assert row["briefing_email_enabled"] is True


def test_put_notification_settings_valid_timezone(client: TestClient) -> None:
    fake_row: dict[str, Any] = {
        "briefing_time": "09:00",
        "briefing_push_enabled": False,
        "briefing_timezone": "Europe/Bucharest",
        "recap_enabled": True,
        "recap_day": "mon",
        "briefing_include_reading_list": False,
        "briefing_reading_list_limit": 3,
        "briefing_email_enabled": False,
        "email": "reader@example.com",
        "is_guest": False,
    }

    with patch("news_dashboard.user_settings.service.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        resp = client.put(
            "/api/settings/notifications",
            json={"briefing_timezone": "Europe/Bucharest"},
        )

    assert resp.status_code == 200
    assert resp.json()["briefing_timezone"] == "Europe/Bucharest"


def test_put_notification_settings_valid_reading_list_opt_in(client: TestClient) -> None:
    fake_row: dict[str, Any] = {
        "briefing_time": "09:00",
        "briefing_push_enabled": False,
        "briefing_timezone": "UTC",
        "recap_enabled": True,
        "recap_day": "mon",
        "briefing_include_reading_list": True,
        "briefing_reading_list_limit": 5,
        "briefing_email_enabled": False,
        "email": "reader@example.com",
        "is_guest": False,
    }

    with patch("news_dashboard.user_settings.service.connect") as mock_connect:
        ctx = mock_connect.return_value.__enter__.return_value
        ctx.execute.return_value.fetchone.return_value = fake_row

        resp = client.put(
            "/api/settings/notifications",
            json={"briefing_include_reading_list": True, "briefing_reading_list_limit": 5},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["briefing_include_reading_list"] is True
    assert data["briefing_reading_list_limit"] == 5


def test_put_notification_settings_invalid_reading_list_limit(client: TestClient) -> None:
    resp = client.put("/api/settings/notifications", json={"briefing_reading_list_limit": 0})
    assert resp.status_code == 422

    resp = client.put("/api/settings/notifications", json={"briefing_reading_list_limit": 21})
    assert resp.status_code == 422


def test_put_notification_settings_invalid_timezone(client: TestClient) -> None:
    resp = client.put("/api/settings/notifications", json={"briefing_timezone": "Mars/Olympus"})
    assert resp.status_code == 422


def test_put_notification_settings_invalid_time(client: TestClient) -> None:
    resp = client.put("/api/settings/notifications", json={"briefing_time": "25:00"})
    assert resp.status_code == 422


def test_push_subscribe_endpoint(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def public_dns_answer(
        _host: str,
        port: int,
        _family: int = 0,
        _socket_type: int = 0,
        _protocol: int = 0,
        _flags: int = 0,
        **kwargs: int,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        del _family, _protocol, _flags
        socket_type = kwargs.get("type", _socket_type)
        return [(socket.AF_INET, socket_type, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    monkeypatch.setattr("news_dashboard.url_safety.socket.getaddrinfo", public_dns_answer)
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
        resp = client.request(
            "DELETE",
            "/api/notifications/subscribe",
            json={"endpoint": "https://ep.example.com"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"unsubscribed": True}
    mock_del.assert_called_once_with(1, endpoint="https://ep.example.com")


def test_push_unsubscribe_without_endpoint_preserves_all_endpoint_cleanup(
    client: TestClient,
) -> None:
    with patch("news_dashboard.push.delete_push_subscriptions") as mock_del:
        resp = client.delete("/api/notifications/subscribe")
    assert resp.status_code == 200
    assert resp.json() == {"unsubscribed": True}
    mock_del.assert_called_once_with(1)


# ── validate_push_subscription unit tests ─────────────────────────────────────


def test_validate_push_subscription_accepts_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    def public_dns_answer(
        _host: str,
        port: int,
        _family: int = 0,
        _socket_type: int = 0,
        _protocol: int = 0,
        _flags: int = 0,
        **kwargs: int,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        del _family, _protocol, _flags
        socket_type = kwargs.get("type", _socket_type)
        return [(socket.AF_INET, socket_type, socket.IPPROTO_TCP, "", ("93.184.216.34", port))]

    monkeypatch.setattr("news_dashboard.url_safety.socket.getaddrinfo", public_dns_answer)
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


def test_push_subscription_rejects_hostname_that_resolves_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def private_dns_answer(
        _host: str,
        port: int,
        _family: int = 0,
        _socket_type: int = 0,
        _protocol: int = 0,
        _flags: int = 0,
        **kwargs: int,
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        del _family, _protocol, _flags
        socket_type = kwargs.get("type", _socket_type)
        return [(socket.AF_INET, socket_type, socket.IPPROTO_TCP, "", ("192.168.1.20", port))]

    monkeypatch.setattr("news_dashboard.url_safety.socket.getaddrinfo", private_dns_answer)

    with pytest.raises(ValueError, match="non-public"):
        validate_push_subscription(
            "https://push.example.com/delivery",
            "BNQtHLiP_xyz-base64url",
            "authkeyABC",
        )


@pytest.mark.parametrize(
    ("endpoint", "p256dh", "auth", "match"),
    [
        ("http://ep.example.com/push", "key", "auth", "https"),
        ("/push/v1/endpoint", "key", "auth", "https"),
        ("", "key", "auth", "https"),
        ("https://127.0.0.1/push", "key", "auth", "non-public"),
        ("https://[::1]/push", "key", "auth", "non-public"),
        ("https://192.168.1.1/push", "key", "auth", "non-public"),
        ("https://169.254.1.1/push", "key", "auth", "non-public"),
        ("https://ep.example.com/push", "", "auth", "p256dh"),
        ("https://ep.example.com/push", "key", "", "auth"),
        ("https://ep.example.com/" + "a" * 2100, "key", "auth", "too long"),
        ("https://ep.example.com/push", "key with spaces!", "auth", "base64url"),
        ("https://ep.example.com/push", "validkey", "auth with spaces!", "base64url"),
    ],
    ids=[
        "http-scheme",
        "relative-url",
        "empty-endpoint",
        "localhost",
        "loopback-ipv6",
        "private-ip",
        "link-local",
        "empty-p256dh",
        "empty-auth",
        "oversized-endpoint",
        "non-base64url-p256dh",
        "non-base64url-auth",
    ],
)
def test_validate_push_subscription_rejects_invalid_input(
    endpoint: str, p256dh: str, auth: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        validate_push_subscription(endpoint, p256dh, auth)


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
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.messages import AIMessage

    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("OPENAI_FREE_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_BRIEFING_MODEL", "gpt-4o-mini")

    hook_text = "Claude 4 drops; markets soar — your brief awaits"
    model = MagicMock()
    model.invoke.return_value = AIMessage(content=hook_text)
    callback = BaseCallbackHandler()

    with (
        patch("news_dashboard.ai_client.get_chat_model", return_value=model) as get_model,
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
        patch("news_dashboard.ai_client.langfuse_enabled", return_value=True),
        patch("langfuse.langchain.CallbackHandler", return_value=callback),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        result = generate_push_hook(_make_briefing())

    assert result == hook_text
    assert get_model.call_args.kwargs == {
        "api_key": "fake-key",
        "base_url": None,
        "model": "gpt-4o-mini",
        "max_tokens": 40,
        "temperature": 0.7,
    }
    assert callback in model.invoke.call_args.kwargs["config"]["callbacks"]
    attributes.assert_called_once_with(tags=["push"], trace_name="push-hook")


def test_generate_recap_push_hook_uses_langchain_settings_and_trace_config() -> None:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.messages import AIMessage

    model = MagicMock()
    model.invoke.return_value = AIMessage(content="Seven thoughtful reads made your week")
    callback = BaseCallbackHandler()
    recap = {
        "articles_read": 7,
        "categories": [{"category": "AI"}],
        "current_streak_days": 3,
    }

    with (
        patch("news_dashboard.ai_client.get_chat_model", return_value=model) as get_model,
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
        patch("news_dashboard.ai_client.langfuse_enabled", return_value=True),
        patch("langfuse.langchain.CallbackHandler", return_value=callback),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        result = generate_recap_push_hook(recap)

    assert result == "Seven thoughtful reads made your week"
    assert get_model.call_args.kwargs["max_tokens"] == 40
    assert get_model.call_args.kwargs["temperature"] == 0.7
    assert callback in model.invoke.call_args.kwargs["config"]["callbacks"]
    attributes.assert_called_once_with(tags=["push", "recap"], trace_name="recap-push-hook")


def test_generate_push_hook_falls_back_on_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    with (
        patch(
            "news_dashboard.ai_client.get_chat_model",
            side_effect=RuntimeError("LLM unavailable"),
        ),
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
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import RunnableLambda

    monkeypatch.setenv("FREE_LLM_API_KEY", "fake-key")

    captured_prompt: list[str] = []

    def fake_invoke(messages: Any) -> AIMessage:
        captured_prompt.append(messages[0]["content"])
        return AIMessage(content="Breaking: AI takes over coding")

    model: RunnableLambda[Any, AIMessage] = RunnableLambda(fake_invoke)

    sections = [
        {"title": "AI milestone achieved", "body": "", "citations": []},
        {"title": "Economy grows 3%", "body": "", "citations": []},
        {"title": "Sports finals tonight", "body": "", "citations": []},
        {"title": "This one should be excluded", "body": "", "citations": []},
    ]

    with (
        patch("news_dashboard.ai_client.get_chat_model", return_value=model),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("fake-key", None)),
    ):
        generate_push_hook(_make_briefing(sections=sections))

    prompt = captured_prompt[0]
    assert "AI milestone achieved" in prompt
    assert "Economy grows 3%" in prompt
    assert "Sports finals tonight" in prompt
    assert "This one should be excluded" not in prompt
