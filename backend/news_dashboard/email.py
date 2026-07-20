"""SMTP email dispatch for one-time-password sign-in emails.

Supports a generic SMTP relay (host/port/user/pass/TLS mode/from) via
``OTP_SMTP_*`` variables, falling back to the digest email's generic
``SMTP_HOST``/``SMTP_PORT``/``SMTP_USER``/``SMTP_PASS`` variables, and finally
to the legacy Gmail-only ``SMTP_USERNAME``/``SMTP_PASSWORD`` alias for
backward compatibility with existing deployments.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from collections.abc import Mapping
from email.message import EmailMessage
from typing import NamedTuple

from news_dashboard.email_theme import EMAIL_COLORS, render_email_shell, render_highlight_panel

logger = logging.getLogger(__name__)

_GMAIL_HOST = "smtp.gmail.com"
_DEFAULT_PORT = 587
_SAFE_HEADERS = frozenset({"List-Unsubscribe", "List-Unsubscribe-Post"})


class _SmtpConfig(NamedTuple):
    host: str
    port: int
    username: str
    password: str
    tls_mode: str
    from_addr: str


def _smtp_config() -> _SmtpConfig:
    """Resolve OTP SMTP settings.

    Precedence for host/user/pass: ``OTP_SMTP_*`` > the digest email's generic
    ``SMTP_HOST``/``SMTP_USER``/``SMTP_PASS`` > the legacy Gmail-only
    ``SMTP_USERNAME``/``SMTP_PASSWORD`` compatibility alias.
    """
    legacy_username = os.environ.get("SMTP_USERNAME", "").strip()
    username = (
        os.environ.get("OTP_SMTP_USER", "").strip()
        or legacy_username
        or os.environ.get("SMTP_USER", "").strip()
    )
    password = (
        os.environ.get("OTP_SMTP_PASS", "").strip()
        or os.environ.get("SMTP_PASSWORD", "").strip()
        or os.environ.get("SMTP_PASS", "").strip()
    )

    host = os.environ.get("OTP_SMTP_HOST", "").strip() or os.environ.get("SMTP_HOST", "").strip()
    if not host and legacy_username:
        # Legacy deployments that only set SMTP_USERNAME/SMTP_PASSWORD assumed Gmail.
        host = _GMAIL_HOST

    port_raw = (
        os.environ.get("OTP_SMTP_PORT", "").strip() or os.environ.get("SMTP_PORT", "").strip()
    )
    port = int(port_raw) if port_raw else _DEFAULT_PORT

    tls_raw = (
        os.environ.get("OTP_SMTP_TLS", "").strip().lower()
        or os.environ.get("SMTP_TLS", "").strip().lower()
    )
    tls_mode = tls_raw or ("ssl" if port == 465 else "starttls")

    from_addr = (
        os.environ.get("OTP_SMTP_FROM", "").strip()
        or os.environ.get("SMTP_FROM", "").strip()
        or username
    )

    return _SmtpConfig(host, port, username, password, tls_mode, from_addr)


def smtp_configured() -> bool:
    """Return whether SMTP is usable, with either paired or no credentials."""
    try:
        config = _smtp_config()
    except ValueError:
        return False
    credentials_valid = bool(config.username) == bool(config.password)
    return bool(
        config.host
        and config.from_addr
        and credentials_valid
        and 1 <= config.port <= 65535
        and config.tls_mode in {"none", "ssl", "starttls"}
    )


def send_email(
    *,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
    headers: Mapping[str, str] | None = None,
) -> str | None:
    """Send a multipart message, returning a safe failure category on error."""
    try:
        config = _smtp_config()
    except ValueError:
        return "smtp_not_configured"
    if (
        not config.host
        or not config.from_addr
        or bool(config.username) != bool(config.password)
        or not 1 <= config.port <= 65535
        or config.tls_mode not in {"none", "ssl", "starttls"}
    ):
        return "smtp_not_configured"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.from_addr
    message["To"] = recipient
    for name, value in (headers or {}).items():
        if name in _SAFE_HEADERS:
            message[name] = value
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        if config.tls_mode == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=15) as server:
                if config.username and config.password:
                    server.login(config.username, config.password)
                server.send_message(message)
        else:
            with smtplib.SMTP(config.host, config.port, timeout=15) as server:
                server.ehlo()
                if config.tls_mode == "starttls":
                    server.starttls()
                    server.ehlo()
                if config.username and config.password:
                    server.login(config.username, config.password)
                server.send_message(message)
    except (OSError, smtplib.SMTPException):
        logger.warning("SMTP email delivery failed")
        return "smtp_error"
    return None


def send_otp_email(to_email: str, otp: str) -> None:
    """Send a 6-digit OTP to *to_email* via the configured SMTP relay."""
    if not smtp_configured():
        err = (
            "OTP SMTP is not configured. Set a host and from address; credentials may be "
            "omitted for an unauthenticated relay or supplied as a username/password pair."
        )
        raise RuntimeError(err)

    body_html = f"""
      <p style="margin:0 0 24px;color:{EMAIL_COLORS["foreground"].email_hex};
                font-size:15px;line-height:1.65;">
        Use the one-time code below to sign in to <strong>News Dashboard</strong>.
        It expires in <strong>10 minutes</strong>.
      </p>
      {render_highlight_panel(label="One-time code", value=otp)}
      <p style="margin:0;padding-top:18px;border-top:1px solid
                {EMAIL_COLORS["border"].email_hex};color:{EMAIL_COLORS["muted"].email_hex};
                font-size:12px;line-height:1.6;">
        If you did not request this code, you can safely ignore this email.
        Someone may have entered your email address by mistake.
      </p>"""
    html_body = render_email_shell(
        preheader="Your News Dashboard sign-in code expires in 10 minutes.",
        eyebrow="Secure sign-in",
        heading="Your sign-in code",
        body_html=body_html,
    )

    result = send_email(
        recipient=to_email,
        subject="Your News Dashboard sign-in code",
        text_body=f"Your News Dashboard sign-in code is {otp}. It expires in 10 minutes.",
        html_body=html_body,
    )
    if result is not None:
        err = "OTP email delivery failed"
        raise RuntimeError(err)

    logger.info("OTP email sent")
