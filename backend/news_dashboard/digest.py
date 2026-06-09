"""Daily digest email: pick top-scored new articles and send via SMTP."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from .db import connect, init_db, row_to_dict

logger = logging.getLogger(__name__)

# Secret used to sign one-click mark-read tokens.
# Override with TOKEN_SECRET env var in production.
_TOKEN_SECRET = os.getenv("TOKEN_SECRET", "news-dashboard-default-secret-change-me")


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _make_token(article_id: int) -> str:
    """Return a short HMAC token for the given article id."""
    msg = f"read:{article_id}".encode()
    return hmac.new(_TOKEN_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]


def verify_read_token(article_id: int, token: str) -> bool:
    expected = _make_token(article_id)
    return hmac.compare_digest(expected, token)


# ---------------------------------------------------------------------------
# Article fetching
# ---------------------------------------------------------------------------


def _get_top_new_articles(limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM articles
            WHERE status = 'new'
            ORDER BY importance_score DESC, discovered_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Email rendering
# ---------------------------------------------------------------------------


def _base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8000")


def _render_html(articles: list[dict[str, Any]]) -> str:
    base = _base_url()
    rows = ""
    for a in articles:
        token = _make_token(a["id"])
        mark_read_url = f"{base}/api/articles/{a['id']}/read?token={token}"
        title = a.get("title") or "Untitled"
        url = a.get("url") or "#"
        source = a.get("source_name") or ""
        summary = a.get("summary") or ""
        score = a.get("importance_score", 0)
        rows += f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #eee;">
            <a href="{url}"
               style="font-size:15px;font-weight:bold;color:#1a1a1a;text-decoration:none;"
            >{title}</a><br>
            <span style="font-size:12px;color:#888;">{source} &middot; score {score}</span><br>
            <p style="margin:6px 0;font-size:13px;color:#444;">{summary}</p>
            <a href="{mark_read_url}" style="font-size:12px;color:#0066cc;">Mark as read &rarr;</a>
          </td>
        </tr>
        """
    date_str = datetime.now(timezone.utc).strftime("%A, %B %-d %Y")
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:640px;margin:auto;padding:24px;">
      <h2 style="color:#1a1a1a;">News Digest &mdash; {date_str}</h2>
      <p style="color:#555;">Your top {len(articles)}
        new article{"s" if len(articles) != 1 else ""} today:</p>
      <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
      <p style="margin-top:24px;font-size:12px;color:#aaa;">
        You received this because you set up the News Dashboard digest.
      </p>
    </body></html>
    """


def _render_text(articles: list[dict[str, Any]]) -> str:
    base = _base_url()
    lines = [f"News Digest — {datetime.now(timezone.utc).strftime('%A, %B %d %Y')}", ""]
    for i, a in enumerate(articles, 1):
        token = _make_token(a["id"])
        mark_read_url = f"{base}/api/articles/{a['id']}/read?token={token}"
        title = a.get("title") or "Untitled"
        url = a.get("url") or ""
        source = a.get("source_name") or ""
        summary = a.get("summary") or ""
        score = a.get("importance_score", 0)
        lines.append(f"{i}. {title}")
        lines.append(f"   Source: {source} | Score: {score}")
        lines.append(f"   {url}")
        if summary:
            lines.append(f"   {summary}")
        lines.append(f"   Mark read: {mark_read_url}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SMTP sending
# ---------------------------------------------------------------------------


def _send_email(subject: str, html_body: str, text_body: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    digest_to = os.getenv("DIGEST_TO", "")

    if not smtp_host or not digest_to:
        logger.warning(
            "SMTP_HOST or DIGEST_TO not configured — digest email skipped. "
            "Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, DIGEST_TO env vars."
        )
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user or f"noreply@{smtp_host}"
    msg["To"] = digest_to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(msg["From"], [digest_to], msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls(context=context)
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(msg["From"], [digest_to], msg.as_string())

    logger.info("Digest email sent to %s", digest_to)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def send_digest() -> bool:
    """Fetch top new articles and send digest email. Returns True if email sent."""
    digest_to = os.getenv("DIGEST_TO", "")
    if not digest_to:
        logger.info("DIGEST_TO not set — skipping digest.")
        return False

    articles = _get_top_new_articles(limit=10)
    if not articles:
        logger.info("No new articles — skipping digest.")
        return False

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = (
        f"News Digest {date_str} — {len(articles)} new article{'s' if len(articles) != 1 else ''}"
    )
    html_body = _render_html(articles)
    text_body = _render_text(articles)

    _send_email(subject, html_body, text_body)
    return True
