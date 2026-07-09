"""Tests for the OTP email content, branding, and SMTP configuration."""

from __future__ import annotations

import smtplib
from email import message_from_string
from email.message import Message
from typing import ClassVar
from unittest.mock import patch

import pytest


class _FakeSMTP:
    """Records constructor args and calls; captures the sent envelope."""

    captured: ClassVar[list[tuple[str, str, str]]] = []
    init_args: ClassVar[list[tuple[object, ...]]] = []
    init_kwargs: ClassVar[list[dict[str, object]]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        type(self).init_args.append(args)
        type(self).init_kwargs.append(kwargs)

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def ehlo(self) -> None:
        pass

    def starttls(self) -> None:
        pass

    def login(self, user: str, _pw: str) -> None:
        pass

    def sendmail(self, frm: str, to: str, raw: str) -> None:
        type(self).captured.append((frm, to, raw))


def _fresh_fake_smtp() -> type[_FakeSMTP]:
    """Return a _FakeSMTP subclass with its own capture buffers."""

    class _Fake(_FakeSMTP):
        captured: ClassVar[list[tuple[str, str, str]]] = []
        init_args: ClassVar[list[tuple[object, ...]]] = []
        init_kwargs: ClassVar[list[dict[str, object]]] = []

    return _Fake


def _capture_sent_message(
    to_email: str,
    otp: str,
    env: dict[str, str] | None = None,
    fake_cls: type[_FakeSMTP] | None = None,
    patch_target: str = "SMTP",
) -> Message:
    """Call send_otp_email with fake SMTP and return the captured MIME message."""
    import news_dashboard.email as email_mod

    fake_cls = fake_cls or _fresh_fake_smtp()
    if env is None:
        env = {"SMTP_USERNAME": "noreply@example.com", "SMTP_PASSWORD": "secret"}

    with (
        patch.dict("os.environ", env, clear=True),
        patch.object(smtplib, patch_target, fake_cls),
    ):
        email_mod.send_otp_email(to_email, otp)

    assert len(fake_cls.captured) == 1, "Expected exactly one email to be sent"
    return message_from_string(fake_cls.captured[0][2])


def _extract_html_body(msg: Message) -> str | None:
    """Return the decoded text of the first text/html part, or None."""
    parts: list[Message] = list(msg.walk()) if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() == "text/html":
            raw = part.get_payload(decode=True)
            if isinstance(raw, bytes):
                return raw.decode("utf-8")
    return None


def test_otp_email_subject_contains_news_dashboard() -> None:
    """Subject must clearly identify the News Dashboard application."""
    msg = _capture_sent_message("user@example.com", "123456")
    subject = msg["Subject"]
    assert subject is not None
    assert "News Dashboard" in subject, f"Subject missing 'News Dashboard': {subject!r}"


def test_otp_email_html_body_contains_news_dashboard() -> None:
    """HTML body must reference the application name so the user knows where the OTP came from."""
    msg = _capture_sent_message("user@example.com", "654321")
    html_body = _extract_html_body(msg)
    assert html_body is not None, "No HTML part found in the email"
    assert "News Dashboard" in html_body, f"HTML body missing 'News Dashboard': {html_body[:300]!r}"


def test_otp_email_html_body_contains_otp_code() -> None:
    """The OTP code must appear in the HTML body."""
    otp = "789012"
    msg = _capture_sent_message("user@example.com", otp)
    html_body = _extract_html_body(msg)
    assert html_body is not None, "No HTML part found in the email"
    assert otp in html_body, f"OTP code {otp!r} not found in HTML body"


def test_otp_email_from_header_uses_smtp_username() -> None:
    """From header must equal the configured SMTP_USERNAME."""
    msg = _capture_sent_message("user@example.com", "111222")
    assert msg["From"] == "noreply@example.com"


def test_otp_email_generic_host_and_port_used() -> None:
    """OTP_SMTP_HOST/OTP_SMTP_PORT should be honored over the Gmail default."""
    fake_cls = _fresh_fake_smtp()
    env = {
        "OTP_SMTP_HOST": "smtp.example.net",
        "OTP_SMTP_PORT": "2525",
        "OTP_SMTP_USER": "relay-user",
        "OTP_SMTP_PASS": "relay-pass",
    }
    _capture_sent_message("user@example.com", "333444", env=env, fake_cls=fake_cls)
    assert fake_cls.init_args[0][:2] == ("smtp.example.net", 2525)


def test_otp_email_falls_back_to_digest_generic_smtp_vars() -> None:
    """When OTP_SMTP_* is unset, the digest email's generic SMTP_HOST/USER/PASS apply."""
    fake_cls = _fresh_fake_smtp()
    env = {
        "SMTP_HOST": "relay.internal",
        "SMTP_PORT": "2526",
        "SMTP_USER": "digest-user",
        "SMTP_PASS": "digest-pass",
    }
    msg = _capture_sent_message("user@example.com", "555666", env=env, fake_cls=fake_cls)
    assert fake_cls.init_args[0][:2] == ("relay.internal", 2526)
    assert msg["From"] == "digest-user"


def test_otp_email_gmail_alias_still_works() -> None:
    """Legacy SMTP_USERNAME/SMTP_PASSWORD deployments keep defaulting to Gmail."""
    fake_cls = _fresh_fake_smtp()
    env = {"SMTP_USERNAME": "noreply@example.com", "SMTP_PASSWORD": "secret"}
    _capture_sent_message("user@example.com", "777888", env=env, fake_cls=fake_cls)
    assert fake_cls.init_args[0][:2] == ("smtp.gmail.com", 587)


def test_otp_email_tls_mode_ssl_uses_smtp_ssl() -> None:
    """OTP_SMTP_TLS=ssl should dispatch via smtplib.SMTP_SSL."""
    fake_cls = _fresh_fake_smtp()
    env = {
        "OTP_SMTP_HOST": "smtp.example.net",
        "OTP_SMTP_PORT": "465",
        "OTP_SMTP_USER": "relay-user",
        "OTP_SMTP_PASS": "relay-pass",
        "OTP_SMTP_TLS": "ssl",
    }
    _capture_sent_message(
        "user@example.com",
        "999000",
        env=env,
        fake_cls=fake_cls,
        patch_target="SMTP_SSL",
    )
    assert fake_cls.init_args[0][:2] == ("smtp.example.net", 465)


def test_otp_email_missing_config_raises_clear_error() -> None:
    """Missing SMTP configuration should raise a RuntimeError explaining how to fix it."""
    import news_dashboard.email as email_mod

    with (
        patch.dict("os.environ", {}, clear=True),
        pytest.raises(RuntimeError, match="OTP SMTP is not configured"),
    ):
        email_mod.send_otp_email("user@example.com", "123123")
