"""Daily digest email: pick top-scored new articles and send via SMTP."""

from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from news_dashboard.db import init_db
from news_dashboard.email_theme import (
    EMAIL_COLORS,
    FONT_SERIF,
    compact_text,
    render_action_link,
    render_email_shell,
)

logger = logging.getLogger(__name__)

_TOKEN_SECRET_ENV_VARS = ("TOKEN_SECRET", "SESSION_SECRET", "TEST_SESSION_SECRET")


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _token_signing_secret() -> str | None:
    for env_var in _TOKEN_SECRET_ENV_VARS:
        secret = os.getenv(env_var)
        if secret:
            return secret
    return None


def _require_token_signing_secret() -> str:
    secret = _token_signing_secret()
    if secret is not None:
        return secret
    msg = "TOKEN_SECRET or SESSION_SECRET env var is required to sign digest mark-read tokens."
    raise RuntimeError(msg)


def _token_signature(user_id: int, article_id: int, secret: str) -> str:
    msg = f"read:{user_id}:{article_id}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:32]


def _make_token(user_id: int, article_id: int) -> str:
    """Return a signed token binding the article to the digest recipient."""
    signature = _token_signature(user_id, article_id, _require_token_signing_secret())
    return f"{user_id}.{signature}"


def verify_read_token(article_id: int, token: str) -> int | None:
    try:
        user_id_text, signature = token.split(".", 1)
        user_id = int(user_id_text)
    except ValueError:
        return None
    secret = _token_signing_secret()
    if secret is None:
        return None
    expected = _token_signature(user_id, article_id, secret)
    if not hmac.compare_digest(expected, signature):
        return None
    return user_id


# ---------------------------------------------------------------------------
# Article fetching
# ---------------------------------------------------------------------------


def _get_top_new_articles(user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    from news_dashboard.ingest.service import list_articles

    init_db()
    articles = list_articles(state="today", user_id=user_id, limit=max(limit * 5, limit))
    return sorted(
        articles,
        key=lambda article: (
            article.get("importance_score") or 0,
            article.get("discovered_at") or "",
        ),
        reverse=True,
    )[:limit]


# ---------------------------------------------------------------------------
# Email rendering
# ---------------------------------------------------------------------------


def _base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8000")


def _display_title(value: object, *, limit: int = 120) -> str:
    """Return a normalized title bounded for compact email presentation."""
    return compact_text(value, fallback="Untitled", limit=limit)


def _render_html(articles: list[dict[str, Any]], *, user_id: int) -> str:
    base = _base_url()
    rows = ""
    for a in articles:
        token = _make_token(user_id, a["id"])
        mark_read_url = f"{base}/api/articles/{a['id']}/read?token={token}"
        title = html.escape(_display_title(a.get("title")))
        url = html.escape(a.get("url") or "#", quote=True)
        source = html.escape(a.get("source_name") or "")
        summary = html.escape(a.get("summary") or "")
        score = html.escape(str(a.get("importance_score", 0)))
        summary_html = ""
        if summary:
            summary_html = f"""
            <p style="margin:9px 0 12px;color:{EMAIL_COLORS["foreground"].email_hex};
                      font-family:{FONT_SERIF};font-size:14px;line-height:1.55;">
              {summary}
            </p>"""
        rows += f"""
        <tr>
          <td style="padding:20px 0;border-bottom:1px solid
                     {EMAIL_COLORS["border"].email_hex};">
            <a href="{url}"
               style="color:{EMAIL_COLORS["primary"].email_hex};font-size:16px;
                      font-weight:700;line-height:1.35;text-decoration:none;"
            >{title}</a><br>
            <span style="display:inline-block;margin-top:6px;color:
                         {EMAIL_COLORS["muted"].email_hex};font-size:11px;
                         letter-spacing:.02em;text-transform:uppercase;">
              {source} &middot; score {score}
            </span>
            {summary_html}
            {render_action_link(url=mark_read_url, label="Move to Done")}
          </td>
        </tr>
        """
    date_str = datetime.now(timezone.utc).strftime("%A, %B %-d %Y")
    article_word = f"article{'s' if len(articles) != 1 else ''}"
    body_html = f"""
      <div style="margin:0 0 8px;padding:16px 18px;border-radius:10px;
                  background:{EMAIL_COLORS["surface_muted"].email_hex};">
        <p style="margin:0;color:{EMAIL_COLORS["muted"].email_hex};
                  font-size:13px;line-height:1.5;">Your top <strong style="color:
                  {EMAIL_COLORS["foreground"].email_hex};">{len(articles)}
        new {article_word} today</strong>, selected by importance.</p>
      </div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        {rows}
      </table>
      <p style="margin:22px 0 0;color:{EMAIL_COLORS["muted"].email_hex};
                font-size:11px;line-height:1.5;">
        You received this because you set up the News Dashboard digest.
      </p>"""
    return render_email_shell(
        preheader=f"Your top {len(articles)} {article_word} for today",
        eyebrow="Daily briefing",
        heading=f"News Digest — {date_str}",
        body_html=body_html,
    )


def _render_text(articles: list[dict[str, Any]], *, user_id: int) -> str:
    base = _base_url()
    lines = [f"News Digest — {datetime.now(timezone.utc).strftime('%A, %B %d %Y')}", ""]
    for i, a in enumerate(articles, 1):
        token = _make_token(user_id, a["id"])
        mark_read_url = f"{base}/api/articles/{a['id']}/read?token={token}"
        title = _display_title(a.get("title"))
        url = a.get("url") or ""
        source = a.get("source_name") or ""
        summary = a.get("summary") or ""
        score = a.get("importance_score", 0)
        lines.append(f"{i}. {title}")
        lines.append(f"   Source: {source} | Score: {score}")
        lines.append(f"   {url}")
        if summary:
            lines.append(f"   {summary}")
        lines.append(f"   Move to Done: {mark_read_url}")
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
    digest_user_id_raw = os.getenv("DIGEST_USER_ID", "")
    if not digest_user_id_raw:
        logger.info("DIGEST_USER_ID not set — skipping digest.")
        return False
    try:
        digest_user_id = int(digest_user_id_raw)
    except ValueError:
        logger.warning("DIGEST_USER_ID is not a valid integer — skipping digest.")
        return False

    articles = _get_top_new_articles(digest_user_id, limit=10)
    if not articles:
        logger.info("No new articles — skipping digest.")
        return False

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subject = (
        f"News Digest {date_str} — {len(articles)} new article{'s' if len(articles) != 1 else ''}"
    )
    html_body = _render_html(articles, user_id=digest_user_id)
    text_body = _render_text(articles, user_id=digest_user_id)

    _send_email(subject, html_body, text_body)
    return True
