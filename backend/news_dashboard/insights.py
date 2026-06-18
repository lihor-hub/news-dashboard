"""AI-generated 'Why it matters' bullet points for articles.

Calls gpt-4o-mini with the article text and caches the result in
articles.insights (JSON) so the AI is invoked at most once per article.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .body_fetch import get_article
from .db import connect, init_db

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"
_MAX_CHARS = 8_000
_PROMPT = (
    "Given this news article, generate 3-5 concise bullet points explaining "
    "why this story matters and what impact it could have. "
    "Be specific and insightful. "
    "Return only the bullet points, one per line, starting with '•'."
)


class InsightsNotConfiguredError(Exception):
    """Raised when OPENAI_API_KEY is not set."""


def _build_text(article: dict[str, Any]) -> str:
    title = str(article.get("title") or "")
    body = str(article.get("body") or "")
    summary = str(article.get("summary") or "")
    content = body if len(body) > len(summary) else summary
    text = f"Title: {title}\n\n{content}" if title else content
    return text[:_MAX_CHARS]


def _parse_bullets(response_text: str) -> list[str]:
    bullets: list[str] = []
    for line in response_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("•"):
            bullet = stripped[1:].strip()
            if bullet:
                bullets.append(bullet)
    return bullets


def generate_insights(article: dict[str, Any]) -> list[str]:
    """Call OpenAI and return a list of bullet-point strings.

    Raises InsightsNotConfiguredError when OPENAI_API_KEY is absent.
    Raises RuntimeError on API failure.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        msg = "OPENAI_API_KEY is not configured"
        raise InsightsNotConfiguredError(msg)

    text = _build_text(article)
    if not text.strip():
        return []

    from openai import OpenAI  # lazy import — optional dep at import time

    client = OpenAI(api_key=api_key)
    logger.info("Generating insights for article %s", article.get("id"))
    result = client.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": f"{_PROMPT}\n\n{text}"}],
        max_tokens=512,
    )
    response_text = (result.choices[0].message.content or "").strip()
    bullets = _parse_bullets(response_text)
    logger.info("Insights generated for article %s: %d bullets", article.get("id"), len(bullets))
    return bullets


def get_or_generate_insights(
    article_id: int,
    user_id: int | None = None,
    database_url: str | None = None,
) -> list[str]:
    """Return cached insights or generate + cache them.

    Raises InsightsNotConfiguredError when OPENAI_API_KEY is absent and
    no cached insights exist.
    """
    init_db(database_url=database_url)

    with connect(database_url=database_url) as conn:
        row = conn.execute("SELECT insights FROM articles WHERE id = %s", (article_id,)).fetchone()

    if row is None:
        return []

    cached = row["insights"] if isinstance(row, dict) else row[0]
    if cached is not None:
        return list(json.loads(cached))

    article = get_article(article_id, user_id=user_id)
    if article is None:
        return []

    bullets = generate_insights(article)

    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE articles SET insights = %s WHERE id = %s",
            (json.dumps(bullets), article_id),
        )

    return bullets
