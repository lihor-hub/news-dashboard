"""AI-generated fact-checking and perspective analysis for articles.

Calls an OpenAI-compatible chat model with the article text and related
articles from the DB, then caches the structured result in
articles.perspective_analysis (JSONB) so the AI is invoked at most once.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from news_dashboard.body_fetch import get_article
from news_dashboard.db import connect, init_db

logger = logging.getLogger(__name__)

DEFAULT_PERSPECTIVES_MODEL = "gpt-4o-mini"
_MAX_CHARS = 8_000
_MAX_RELATED = 3
_MAX_RELATED_CHARS = 1_000

_PROMPT = """\
You are an impartial media analyst. Given a news article and optionally some \
related articles from the same database, produce a structured JSON analysis with \
exactly three keys:
  "verified_facts": a list of strings — key claims in the article that are \
  widely corroborated or can be taken as factual based on the source material.
  "omissions": a list of strings — important context, background, or caveats \
  that the article leaves out but are relevant to a balanced understanding.
  "alternative_perspectives": a list of strings — differing viewpoints, \
  counter-arguments, or competing narratives found in the related articles or \
  widely known on this topic.

Rules:
- Base every point strictly on what the article(s) say. Do not invent facts.
- Each list must have 1-4 items. If a category has nothing to add, return an \
  empty list.
- Return ONLY the JSON object, no prose before or after.
"""


class PerspectivesNotConfiguredError(Exception):
    """Raised when OPENAI_API_KEY is not set."""


def _build_text(article: dict[str, Any], related: list[dict[str, Any]]) -> str:
    title = str(article.get("title") or "")
    body = str(article.get("body") or "")
    summary = str(article.get("summary") or "")
    content = body if len(body) > len(summary) else summary
    main_text = f"Title: {title}\n\n{content}" if title else content
    main_text = main_text[:_MAX_CHARS]

    if not related:
        return main_text

    related_parts: list[str] = []
    for r in related:
        r_title = str(r.get("title") or "")
        r_body = str(r.get("body") or "")
        r_summary = str(r.get("summary") or "")
        r_content = r_body if len(r_body) > len(r_summary) else r_summary
        snippet = f"- {r_title}: {r_content}"[:_MAX_RELATED_CHARS]
        related_parts.append(snippet)

    related_block = "\n\nRelated articles:\n" + "\n".join(related_parts)
    return main_text + related_block


def _perspectives_ai_config() -> tuple[str, str | None, str]:
    """Resolve (api_key, base_url, model) for perspective analysis.

    Can target any OpenAI-compatible endpoint via
    ``OPENAI_PERSPECTIVES_BASE_URL`` / ``OPENAI_PERSPECTIVES_API_KEY``, falling
    back to the shared ``OPENAI_BASE_URL`` / ``OPENAI_API_KEY``.
    """
    api_key = os.getenv("OPENAI_PERSPECTIVES_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        msg = "OPENAI_API_KEY is not configured"
        raise PerspectivesNotConfiguredError(msg)
    base_url = os.getenv("OPENAI_PERSPECTIVES_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    model = os.getenv("OPENAI_PERSPECTIVES_MODEL", DEFAULT_PERSPECTIVES_MODEL)
    return api_key, base_url, model


def _parse_analysis(response_text: str) -> dict[str, list[str]]:
    """Parse the JSON response from the LLM into a typed dict."""
    empty: dict[str, list[str]] = {
        "verified_facts": [],
        "omissions": [],
        "alternative_perspectives": [],
    }
    text = response_text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("perspectives: failed to parse LLM JSON response")
        return empty

    result: dict[str, list[str]] = {}
    for key in ("verified_facts", "omissions", "alternative_perspectives"):
        raw = data.get(key, [])
        result[key] = [str(item) for item in raw if str(item).strip()]
    return result


def _fetch_related_articles(
    article_id: int, *, database_url: str | None = None
) -> list[dict[str, Any]]:
    """Return up to _MAX_RELATED articles that share the same source/category."""
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT a.title, a.body, a.summary
            FROM articles a
            JOIN articles pivot ON pivot.id = %s
            WHERE a.id <> %s
              AND a.category = pivot.category
              AND (a.body IS NOT NULL OR a.summary IS NOT NULL)
            ORDER BY a.discovered_at DESC
            LIMIT %s
            """,
            (article_id, article_id, _MAX_RELATED),
        ).fetchall()
    return [dict(r) for r in rows]


def generate_perspectives(
    article: dict[str, Any],
    related: list[dict[str, Any]] | None = None,
    *,
    user_id: int | None = None,
) -> dict[str, list[str]]:
    """Call the LLM and return structured perspective analysis.

    Raises PerspectivesNotConfiguredError when OPENAI_API_KEY is absent.
    """
    api_key, base_url, model = _perspectives_ai_config()

    text = _build_text(article, related or [])
    if not text.strip():
        return {"verified_facts": [], "omissions": [], "alternative_perspectives": []}

    from news_dashboard.ai_client import chat_create, get_openai_client, get_prompt

    client = get_openai_client(api_key=api_key, base_url=base_url)
    prompt = get_prompt("article-perspectives", fallback=_PROMPT)
    logger.info("Generating perspectives for article %s", article.get("id"))
    result = chat_create(
        client,
        name="article-perspectives",
        tags=["perspectives"],
        user_id=user_id,
        prompt=prompt,
        model=model,
        messages=[{"role": "user", "content": f"{prompt.text}\n\n{text}"}],
        max_tokens=1024,
    )
    response_text = (result.choices[0].message.content or "").strip()
    analysis = _parse_analysis(response_text)
    logger.info("Perspectives generated for article %s", article.get("id"))
    return analysis


def get_or_generate_perspectives(
    article_id: int,
    user_id: int | None = None,
    database_url: str | None = None,
) -> dict[str, list[str]] | None:
    """Return cached perspective analysis or generate and cache it.

    Returns None if the article does not exist.
    Raises PerspectivesNotConfiguredError when OPENAI_API_KEY is absent and
    no cached analysis exists.
    """
    init_db(database_url=database_url)

    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "SELECT perspective_analysis FROM articles WHERE id = %s", (article_id,)
        ).fetchone()

    if row is None:
        return None

    cached = row["perspective_analysis"] if isinstance(row, dict) else row[0]
    if cached is not None:
        if isinstance(cached, str):
            parsed: dict[str, list[str]] = json.loads(cached)
            return parsed
        return dict(cached)

    article = get_article(article_id, user_id=user_id)
    if article is None:
        return None

    if not str(article.get("body") or "").strip():
        return {"verified_facts": [], "omissions": [], "alternative_perspectives": []}

    related = _fetch_related_articles(article_id, database_url=database_url)
    analysis = generate_perspectives(article, related, user_id=user_id)

    with connect(database_url=database_url) as conn:
        conn.execute(
            "UPDATE articles SET perspective_analysis = %s WHERE id = %s",
            (json.dumps(analysis), article_id),
        )

    return analysis
