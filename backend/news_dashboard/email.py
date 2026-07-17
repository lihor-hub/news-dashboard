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

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Your News Dashboard sign-in code</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Helvetica Neue',Arial,sans-serif">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="background:#f0f4f8;padding:32px 0">
    <tr>
      <td align="center">
        <table role="presentation" width="480" cellspacing="0" cellpadding="0"
               style="max-width:480px;width:100%;background:#ffffff;border-radius:12px;
                      overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08)">

          <!-- Branded header -->
          <tr>
            <td style="background:#1e293b;padding:28px 32px;text-align:center">
              <p style="margin:0;font-size:26px">📰</p>
              <h1 style="margin:8px 0 4px;color:#ffffff;font-size:22px;
                         font-weight:700;letter-spacing:-.3px">News Dashboard</h1>
              <p style="margin:0;color:#94a3b8;font-size:13px">
                Your personalised news intelligence platform
              </p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 32px 24px">
              <h2 style="margin:0 0 12px;color:#1e293b;font-size:20px;font-weight:700">
                Your sign-in code
              </h2>
              <p style="margin:0 0 28px;color:#475569;font-size:15px;line-height:1.6">
                Use the one-time code below to sign in to&nbsp;<strong>News&nbsp;Dashboard</strong>.
                It expires in&nbsp;<strong>10&nbsp;minutes</strong>.
              </p>

              <!-- OTP block -->
              <div style="background:#eff6ff;border:2px solid #2563eb;border-radius:10px;
                          padding:24px;text-align:center;margin-bottom:28px">
                <p style="margin:0 0 6px;color:#3b82f6;font-size:11px;
                           font-weight:600;letter-spacing:1.5px;text-transform:uppercase">
                  One-time code
                </p>
                <span style="display:inline-block;font-size:40px;font-weight:800;
                             letter-spacing:10px;color:#1e40af;line-height:1">
                  {otp}
                </span>
              </div>

              <p style="margin:0;color:#94a3b8;font-size:12px;line-height:1.6;
                         border-top:1px solid #e2e8f0;padding-top:20px">
                If you did not request this code, you can safely ignore this email.
                Someone may have entered your email address by mistake.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f8fafc;padding:16px 32px;text-align:center;
                       border-top:1px solid #e2e8f0">
              <p style="margin:0;color:#94a3b8;font-size:11px">
                This email was sent by <strong>News Dashboard</strong>.
                Do not reply to this email.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

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
