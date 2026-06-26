"""AI-generated 'Why it matters' bullet points for articles.

Calls an OpenAI-compatible chat model with the article text and caches the result in
articles.insights (JSON) so the AI is invoked at most once per article.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from news_dashboard.body_fetch import get_article
from news_dashboard.db import connect, init_db

logger = logging.getLogger(__name__)

DEFAULT_INSIGHTS_MODEL = "gpt-4o-mini"
_MAX_CHARS = 8_000
_PROMPT = (
    "You are analyzing a news article. Based ONLY on the information explicitly stated in the "
    "article text below, generate 3-5 concise bullet points explaining why this story matters "
    "and what its potential impact is. "
    "Ground every bullet strictly in what the article actually says — do not add context, "
    "speculation, or general knowledge about the topic that is not stated in the article. "
    "If the article text does not clearly support a takeaway, return fewer bullets rather than "
    "inventing one. "
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


def _insights_ai_config() -> tuple[str, str | None, str]:
    """Resolve the (api_key, base_url, model) for article insight generation.

    Insights can target any OpenAI-compatible endpoint via
    ``OPENAI_INSIGHTS_BASE_URL`` / ``OPENAI_INSIGHTS_API_KEY``, falling back to
    the shared ``OPENAI_BASE_URL`` / ``OPENAI_API_KEY``. The base URL is
    optional; when unset the official OpenAI endpoint is used.
    """
    api_key = os.getenv("OPENAI_INSIGHTS_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        msg = "OPENAI_API_KEY is not configured"
        raise InsightsNotConfiguredError(msg)
    base_url = os.getenv("OPENAI_INSIGHTS_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    model = os.getenv("OPENAI_INSIGHTS_MODEL", DEFAULT_INSIGHTS_MODEL)
    return api_key, base_url, model


def generate_insights(article: dict[str, Any], *, user_id: int | None = None) -> list[str]:
    """Call OpenAI and return a list of bullet-point strings.

    Raises InsightsNotConfiguredError when OPENAI_API_KEY is absent.
    Raises RuntimeError on API failure.
    """
    api_key, base_url, model = _insights_ai_config()

    text = _build_text(article)
    if not text.strip():
        return []

    from news_dashboard.ai_client import chat_create, get_openai_client, get_prompt

    client = get_openai_client(api_key=api_key, base_url=base_url)
    prompt = get_prompt("article-insights", fallback=_PROMPT)
    logger.info("Generating insights for article %s", article.get("id"))
    result = chat_create(
        client,
        name="article-insights",
        tags=["insights"],
        user_id=user_id,
        prompt=prompt,
        model=model,
        messages=[{"role": "user", "content": f"{prompt.text}\n\n{text}"}],
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

    # Require a fetched article body — do not generate from headline/summary alone
    if not str(article.get("body") or "").strip():
        return []

    bullets = generate_insights(article, user_id=user_id)

    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE articles SET insights = %s WHERE id = %s",
            (json.dumps(bullets), article_id),
        )

    return bullets
