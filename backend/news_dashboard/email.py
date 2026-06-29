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
<html>
<body style="font-family:sans-serif;color:#1a1a1a;max-width:480px;margin:0 auto;padding:24px">
  <h2 style="margin-bottom:8px">Your sign-in code</h2>
  <p style="color:#555;margin-bottom:24px">
    Use the code below to sign in. It expires in&nbsp;10&nbsp;minutes.
  </p>
  <div style="font-size:36px;font-weight:700;letter-spacing:8px;text-align:center;
              padding:20px;background:#f5f5f5;border-radius:8px">
    {otp}
  </div>
  <p style="color:#888;font-size:12px;margin-top:24px">
    If you did not request this code, you can safely ignore this email.
  </p>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your sign-in code"
    msg["From"] = username
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(username, password)
        server.sendmail(username, to_email, msg.as_string())

    logger.info("OTP email sent to %s", to_email)
