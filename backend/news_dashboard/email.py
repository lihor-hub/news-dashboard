"""SMTP email dispatch via Gmail SMTP (STARTTLS)."""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 587


def _smtp_credentials() -> tuple[str, str]:
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    return username, password


def send_otp_email(to_email: str, otp: str) -> None:
    """Send a 6-digit OTP to *to_email* via Gmail SMTP STARTTLS."""
    username, password = _smtp_credentials()
    if not username or not password:
        err = "SMTP_USERNAME and SMTP_PASSWORD must be set to send OTP emails"
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

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your News Dashboard sign-in code"
    msg["From"] = username
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(username, password)
        server.sendmail(username, to_email, msg.as_string())

    logger.info("OTP email sent to %s", to_email)
