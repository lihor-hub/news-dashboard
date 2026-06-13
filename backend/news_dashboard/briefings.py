"""PostgreSQL-backed briefings storage, read API, and generation.

Runtime SQL uses psycopg %s parameter style. No SQLite fallback.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import connect, row_to_dict

CANDIDATE_LIMIT = 40
DEFAULT_BRIEFING_MODEL = "gpt-4o-mini"

# ── Error types ───────────────────────────────────────────────────────────────


class BriefingAINotConfiguredError(RuntimeError):
    """Raised when OPENAI_API_KEY is absent and generation is attempted."""


class BriefingGenerationError(RuntimeError):
    """Raised when the AI returns a structurally invalid or unparseable briefing."""


# ── Type alias for the injectable AI function ─────────────────────────────────

AiFn = Callable[[list[dict[str, Any]], str], dict[str, Any]]

# ── SQL constants ─────────────────────────────────────────────────────────────

_CITED_ARTICLES_SQL = """
    SELECT
        a.id,
        a.title,
        a.url,
        a.canonical_url,
        a.source_name,
        a.category,
        a.kind,
        a.published_at,
        a.summary,
        a.importance_score,
        ba.section_index,
        ba.citation_index
    FROM briefing_articles ba
    JOIN articles a ON a.id = ba.article_id
    WHERE ba.briefing_id = %s
    ORDER BY ba.section_index NULLS LAST, ba.citation_index NULLS LAST, a.id
"""

_CANDIDATES_SQL = """
    SELECT id, title, url, source_name, category, summary, importance_score, discovered_at
    FROM articles
    WHERE state = 'today'
      AND discovered_at >= %s
    ORDER BY importance_score DESC NULLS LAST, discovered_at DESC
    LIMIT %s
"""


# ── Internal helpers ──────────────────────────────────────────────────────────


def _fetch_cited_articles(conn: Any, briefing_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(_CITED_ARTICLES_SQL, (briefing_id,)).fetchall()
    return [row_to_dict(row) for row in rows]


def _coerce_content(value: Any) -> Any:
    """Normalise content: psycopg returns jsonb as dict already; SQLite TEXT needs decoding."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _get_since_at(database_url: str | None = None) -> datetime:
    """Return the previous briefing's until_at, or now() - 24h if none exists."""
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            SELECT until_at FROM briefings
            WHERE status = 'complete' AND until_at IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
        ).fetchone()
    if row is not None:
        val = row_to_dict(row)["until_at"]
        if val is not None:
            # psycopg returns TIMESTAMPTZ as an aware datetime; normalise just in case
            if isinstance(val, datetime):
                return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
            # fallback: parse ISO string
            return datetime.fromisoformat(str(val))
    return datetime.now(timezone.utc) - timedelta(hours=24)


def _call_openai(candidates: list[dict[str, Any]], model: str) -> dict[str, Any]:
    """Call OpenAI to generate structured briefing JSON from a candidate article list."""
    from openai import OpenAI  # lazy import — optional dep at import time

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        msg = "Briefing generation requires OPENAI_API_KEY. Set it in the app environment."
        raise BriefingAINotConfiguredError(msg)

    article_lines = []
    for a in candidates:
        snippet = (a.get("summary") or "")[:200]
        article_lines.append(
            f"[{a['id']}] {a['title']} "
            f"({a.get('source_name', '')} / {a.get('category', '')})\n  {snippet}"
        )

    system = (
        "You are a briefing editor. Given a list of news articles (each with a numeric ID), "
        "produce a JSON object with these exact keys:\n"
        "  title     — short, punchy headline for the briefing (max 10 words)\n"
        "  summary   — 1-2 sentence overview of the day's themes\n"
        "  sections  — array of section objects, each with:\n"
        "                title     — section heading\n"
        "                body      — 2-4 sentence narrative\n"
        "                citations — array of integer article IDs cited in body\n"
        "  worth_opening — flat array of integer article IDs most worth reading in full\n"
        "Only use IDs from the provided list. Return valid JSON only, no markdown wrapper."
    )
    user = "Articles:\n\n" + "\n\n".join(article_lines)

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        max_tokens=2048,
    )
    text = response.choices[0].message.content or "{}"
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        msg = f"AI returned invalid JSON: {exc}"
        raise BriefingGenerationError(msg) from exc


def _validate_content(raw: dict[str, Any], candidate_ids: set[int]) -> dict[str, Any]:
    """Validate structure and strip citations that reference unknown article IDs."""
    required = {"title", "summary", "sections"}
    missing = required - raw.keys()
    if missing:
        msg = f"AI response missing required keys: {missing}"
        raise BriefingGenerationError(msg)

    sections = raw.get("sections") or []
    if not isinstance(sections, list):
        msg = "AI response 'sections' must be a list"
        raise BriefingGenerationError(msg)

    clean_sections = []
    for section in sections:
        citations = [c for c in (section.get("citations") or []) if int(c) in candidate_ids]
        clean_sections.append(
            {
                "title": section.get("title", ""),
                "body": section.get("body", ""),
                "citations": citations,
            }
        )

    worth_opening = [int(c) for c in (raw.get("worth_opening") or []) if int(c) in candidate_ids]

    return {
        "title": str(raw.get("title", "")),
        "summary": str(raw.get("summary", "")),
        "sections": clean_sections,
        "worth_opening": worth_opening,
    }


def _save_briefing(
    since_at: datetime,
    until_at: datetime,
    content: dict[str, Any],
    candidate_ids: set[int],
    model: str,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Insert briefing + article links; return the full briefing dict."""
    title = content.get("title") or ""
    summary = content.get("summary") or ""
    content_blob = {
        "sections": content.get("sections", []),
        "worth_opening": content.get("worth_opening", []),
    }

    with connect(database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO briefings(
                scope, since_at, until_at, status, title, summary, content, model
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
            """,
            (
                "since_last_briefing",
                since_at,
                until_at,
                "complete",
                title,
                summary,
                json.dumps(content_blob),
                model,
            ),
        ).fetchone()
        if row is None:
            msg = "INSERT INTO briefings returned no row"
            raise BriefingGenerationError(msg)
        briefing_id = int(row_to_dict(row)["id"])

        cited_ids: set[int] = set()
        for s_idx, section in enumerate(content.get("sections", [])):
            for c_idx, article_id in enumerate(section.get("citations", [])):
                aid = int(article_id)
                if aid in candidate_ids:
                    conn.execute(
                        """
                        INSERT INTO briefing_articles(
                            briefing_id, article_id, section_index, citation_index
                        )
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (briefing_id, aid, s_idx, c_idx),
                    )
                    cited_ids.add(aid)

        for article_id in content.get("worth_opening", []):
            aid = int(article_id)
            if aid in candidate_ids and aid not in cited_ids:
                conn.execute(
                    """
                    INSERT INTO briefing_articles(briefing_id, article_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (briefing_id, aid),
                )

    result = get_briefing(briefing_id, database_url=database_url)
    if result is None:
        msg = f"Could not re-read briefing {briefing_id} after insert"
        raise BriefingGenerationError(msg)
    return result


# ── Public API ────────────────────────────────────────────────────────────────


def select_candidates(
    since_at: datetime,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    """Return up to CANDIDATE_LIMIT today-state articles discovered after since_at."""
    with connect(database_url=database_url) as conn:
        rows = conn.execute(_CANDIDATES_SQL, (since_at, CANDIDATE_LIMIT)).fetchall()
        return [row_to_dict(r) for r in rows]


def generate_briefing(
    database_url: str | None = None,
    *,
    model: str | None = None,
    ai_fn: AiFn | None = None,
) -> dict[str, Any]:
    """Generate and persist a briefing from eligible Today articles.

    Returns the saved briefing dict on success, or ``{"status": "no_candidates"}``
    when no eligible articles are found.

    Raises:
        BriefingAINotConfiguredError: OPENAI_API_KEY is not set.
        BriefingGenerationError: AI returned an invalid or unparseable response.
    """
    _env_model = os.getenv("OPENAI_BRIEFING_MODEL", DEFAULT_BRIEFING_MODEL)
    resolved_model = model if model is not None else _env_model
    since_at = _get_since_at(database_url)
    until_at = datetime.now(timezone.utc)

    candidates = select_candidates(since_at, database_url=database_url)
    if not candidates:
        return {"status": "no_candidates"}

    candidate_ids = {int(a["id"]) for a in candidates}
    call_ai: AiFn = ai_fn if ai_fn is not None else _call_openai
    raw_content = call_ai(candidates, resolved_model)

    content = _validate_content(raw_content, candidate_ids)
    return _save_briefing(since_at, until_at, content, candidate_ids, resolved_model, database_url)


def get_latest_briefing(
    db_path: Path | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Return the most recent briefing with cited articles, or None if none exist."""
    with connect(db_path, database_url) as conn:
        row = conn.execute(
            """
            SELECT id, created_at, scope, since_at, until_at, status,
                   title, summary, content, model, error
            FROM briefings
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (1,),
        ).fetchone()
        if row is None:
            return None
        briefing = row_to_dict(row)
        briefing["content"] = _coerce_content(briefing.get("content"))
        briefing["articles"] = _fetch_cited_articles(conn, briefing["id"])
        return briefing


def list_briefings(
    limit: int = 50,
    offset: int = 0,
    db_path: Path | None = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    """Return briefing history (no content blob, no articles)."""
    with connect(db_path, database_url) as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, scope, since_at, until_at, status,
                   title, summary, model, error
            FROM briefings
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ).fetchall()
        return [row_to_dict(r) for r in rows]


def get_briefing(
    briefing_id: int,
    db_path: Path | None = None,
    database_url: str | None = None,
) -> dict[str, Any] | None:
    """Return one briefing with full content and cited article metadata."""
    with connect(db_path, database_url) as conn:
        row = conn.execute(
            """
            SELECT id, created_at, scope, since_at, until_at, status,
                   title, summary, content, model, error
            FROM briefings
            WHERE id = %s
            """,
            (briefing_id,),
        ).fetchone()
        if row is None:
            return None
        briefing = row_to_dict(row)
        briefing["content"] = _coerce_content(briefing.get("content"))
        briefing["articles"] = _fetch_cited_articles(conn, briefing["id"])
        return briefing
