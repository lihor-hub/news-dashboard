"""Tests for the OTP email content and branding."""

from __future__ import annotations

import smtplib
from email import message_from_string
from email.message import Message
from unittest.mock import patch


def _capture_sent_message(to_email: str, otp: str) -> Message:
    """Call send_otp_email with fake SMTP and return the captured MIME message."""
    import news_dashboard.email as email_mod

    captured: list[tuple[str, str, str]] = []

    class _FakeSMTP:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

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
            captured.append((frm, to, raw))

    with (
        patch.dict(
            "os.environ",
            {"SMTP_USERNAME": "noreply@example.com", "SMTP_PASSWORD": "secret"},
        ),
        patch.object(smtplib, "SMTP", _FakeSMTP),
    ):
        email_mod.send_otp_email(to_email, otp)

    assert len(captured) == 1, "Expected exactly one email to be sent"
    return message_from_string(captured[0][2])


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
