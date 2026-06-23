"""PostgreSQL-backed briefings storage, read API, and generation.

Runtime SQL uses psycopg %s parameter style. No SQLite fallback.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import connect, row_to_dict

CANDIDATE_LIMIT = 40
DEFAULT_BRIEFING_MODEL = "gpt-4o-mini"
IDEMPOTENCY_WINDOW_MINUTES = 10
CURRENT_DAY_SCOPE = "current_day"

logger = logging.getLogger(__name__)

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
    WHERE discovered_at::timestamptz >= %s
      AND discovered_at::timestamptz < %s
      AND (canonical_id IS NULL OR state != 'archived')
    ORDER BY importance_score DESC NULLS LAST, discovered_at DESC
    LIMIT %s
"""

_CANDIDATES_SQL_USER = """
    SELECT a.id, a.title, a.url, a.source_name, a.category,
           a.summary, a.importance_score, a.discovered_at
    FROM articles a
    LEFT JOIN user_article_state uas ON uas.article_id = a.id AND uas.user_id = %s
    LEFT JOIN sources src ON src.slug = a.source_slug
    LEFT JOIN user_sources us_src ON us_src.user_id = %s AND us_src.source_slug = a.source_slug
    WHERE a.discovered_at::timestamptz >= %s
      AND a.discovered_at::timestamptz < %s
      AND (a.canonical_id IS NULL OR a.state != 'archived')
      AND (
        (src.owner_user_id IS NULL AND COALESCE(us_src.enabled, TRUE) IS TRUE)
        OR src.owner_user_id = %s
      )
    ORDER BY a.importance_score DESC NULLS LAST, a.discovered_at DESC
    LIMIT %s
"""


# ── Internal helpers ──────────────────────────────────────────────────────────


def _fetch_cited_articles(conn: Any, briefing_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(_CITED_ARTICLES_SQL, (briefing_id,)).fetchall()
    return [row_to_dict(row) for row in rows]


def _coerce_content(value: Any) -> Any:
    """Normalise content from JSONB rows and tolerate older string payloads."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _get_since_at(
    database_url: str | None = None,
    user_id: int | None = None,
) -> datetime:
    """Return the previous briefing's until_at for this user, or now() - 24h if none exists."""
    with connect(database_url=database_url) as conn:
        if user_id is not None:
            row = conn.execute(
                """
                SELECT until_at FROM briefings
                WHERE status = 'complete' AND until_at IS NOT NULL AND user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT until_at FROM briefings
                WHERE status = 'complete' AND until_at IS NOT NULL AND user_id IS NULL
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


def _current_day_since_at(until_at: datetime) -> datetime:
    """Return the current-day briefing lower bound using the app's rolling 24-hour convention."""
    return until_at - timedelta(hours=24)


def _briefing_ai_config() -> tuple[str, str | None]:
    """Resolve the (api_key, base_url) for briefing generation.

    Briefings can target any OpenAI-compatible endpoint (e.g. a self-hosted
    gateway) via ``OPENAI_BRIEFING_BASE_URL`` / ``OPENAI_BRIEFING_API_KEY``,
    falling back to the shared ``OPENAI_BASE_URL`` / ``OPENAI_API_KEY`` used by
    the rest of the app. The base URL is optional; when unset the official
    OpenAI endpoint is used.
    """
    api_key = os.getenv("OPENAI_BRIEFING_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        msg = (
            "Briefing generation requires an API key. Set OPENAI_BRIEFING_API_KEY "
            "(or OPENAI_API_KEY) in the app environment."
        )
        raise BriefingAINotConfiguredError(msg)
    base_url = os.getenv("OPENAI_BRIEFING_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    return api_key, base_url


def _call_openai(candidates: list[dict[str, Any]], model: str) -> dict[str, Any]:
    """Call an OpenAI-compatible API to generate structured briefing JSON."""
    from openai import OpenAI  # lazy import — optional dep at import time

    api_key, base_url = _briefing_ai_config()

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

    from openai import OpenAIError  # lazy import — optional dep at import time

    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=2048,
        )
    except OpenAIError as exc:
        # Connection refused, auth failure, or the model/gateway rejecting the
        # request (e.g. an endpoint that does not support JSON response_format).
        # Surface the upstream reason instead of an opaque 500.
        endpoint = base_url or "the default OpenAI endpoint"
        msg = f"Briefing AI request to {endpoint} failed: {exc}"
        raise BriefingGenerationError(msg) from exc
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
    user_id: int | None = None,
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
                scope, since_at, until_at, status, title, summary, content, model, user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id
            """,
            (
                CURRENT_DAY_SCOPE,
                since_at,
                until_at,
                "complete",
                title,
                summary,
                json.dumps(content_blob),
                model,
                user_id,
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

    result = get_briefing(briefing_id, database_url=database_url, user_id=user_id)
    if result is None:
        msg = f"Could not re-read briefing {briefing_id} after insert"
        raise BriefingGenerationError(msg)
    return result


def _find_recent_briefing(
    window_minutes: int,
    database_url: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent complete briefing if created within window_minutes, else None."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    with connect(database_url=database_url) as conn:
        if user_id is not None:
            row = conn.execute(
                """
                SELECT id FROM briefings
                WHERE status = 'complete' AND created_at >= %s AND user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (cutoff, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id FROM briefings
                WHERE status = 'complete' AND created_at >= %s AND user_id IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (cutoff,),
            ).fetchone()
    if row is None:
        return None
    return get_briefing(int(row_to_dict(row)["id"]), database_url=database_url, user_id=user_id)


def _save_failed_briefing(
    since_at: datetime,
    until_at: datetime,
    exc: Exception,
    model: str,
    database_url: str | None = None,
    user_id: int | None = None,
) -> None:
    """Persist a failed-status row for observability; DB errors are swallowed."""
    try:
        with connect(database_url=database_url) as conn:
            conn.execute(
                """
                INSERT INTO briefings(scope, since_at, until_at, status, model, error, user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (CURRENT_DAY_SCOPE, since_at, until_at, "failed", model, str(exc), user_id),
            )
    except Exception:
        logger.exception("Failed to persist failed-briefing row — original error follows")


# ── Public API ────────────────────────────────────────────────────────────────


def select_candidates(
    since_at: datetime,
    until_at: datetime | None = None,
    database_url: str | None = None,
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return up to CANDIDATE_LIMIT current-day articles discovered within the window.

    Workflow state is intentionally ignored so generated reports can include news
    the user has already opened, starred, postponed, skipped, or marked done.
    When user_id is provided, source subscriptions still scope the article pool.
    """
    resolved_until_at = until_at if until_at is not None else datetime.now(timezone.utc)
    with connect(database_url=database_url) as conn:
        if user_id is not None:
            rows = conn.execute(
                _CANDIDATES_SQL_USER,
                (user_id, user_id, since_at, resolved_until_at, user_id, CANDIDATE_LIMIT),
            ).fetchall()
        else:
            rows = conn.execute(
                _CANDIDATES_SQL, (since_at, resolved_until_at, CANDIDATE_LIMIT)
            ).fetchall()
        return [row_to_dict(r) for r in rows]


def generate_briefing(
    database_url: str | None = None,
    *,
    model: str | None = None,
    ai_fn: AiFn | None = None,
    idempotency_window_minutes: int = IDEMPOTENCY_WINDOW_MINUTES,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Generate and persist a briefing from eligible Today articles.

    If a complete briefing already exists within ``idempotency_window_minutes``,
    return it immediately without calling the AI again.

    Returns the saved briefing dict on success, or ``{"status": "no_candidates"}``
    when no eligible articles are found.

    Raises:
        BriefingAINotConfiguredError: OPENAI_API_KEY is not set.
        BriefingGenerationError: AI returned an invalid or unparseable response.
    """
    recent = _find_recent_briefing(idempotency_window_minutes, database_url, user_id=user_id)
    if recent is not None:
        return recent

    _env_model = os.getenv("OPENAI_BRIEFING_MODEL", DEFAULT_BRIEFING_MODEL)
    resolved_model = model if model is not None else _env_model
    until_at = datetime.now(timezone.utc)
    since_at = _current_day_since_at(until_at)

    candidates = select_candidates(
        since_at, until_at=until_at, database_url=database_url, user_id=user_id
    )
    if not candidates:
        return {"status": "no_candidates"}

    candidate_ids = {int(a["id"]) for a in candidates}
    call_ai: AiFn = ai_fn if ai_fn is not None else _call_openai
    try:
        raw_content = call_ai(candidates, resolved_model)
        content = _validate_content(raw_content, candidate_ids)
    except (BriefingAINotConfiguredError, BriefingGenerationError) as exc:
        _save_failed_briefing(
            since_at, until_at, exc, resolved_model, database_url, user_id=user_id
        )
        raise
    return _save_briefing(
        since_at, until_at, content, candidate_ids, resolved_model, database_url, user_id=user_id
    )


def get_latest_briefing(
    db_path: Path | None = None,
    database_url: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Return the most recent briefing with cited articles, or None if none exist."""
    with connect(db_path, database_url) as conn:
        if user_id is not None:
            row = conn.execute(
                """
                SELECT id, created_at, scope, since_at, until_at, status,
                       title, summary, content, model, error
                FROM briefings
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, 1),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, created_at, scope, since_at, until_at, status,
                       title, summary, content, model, error
                FROM briefings
                WHERE user_id IS NULL
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
    user_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return briefing history (no content blob, no articles)."""
    with connect(db_path, database_url) as conn:
        if user_id is not None:
            rows = conn.execute(
                """
                SELECT id, created_at, scope, since_at, until_at, status,
                       title, summary, model, error
                FROM briefings
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, created_at, scope, since_at, until_at, status,
                       title, summary, model, error
                FROM briefings
                WHERE user_id IS NULL
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
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """Return one briefing with full content and cited article metadata."""
    with connect(db_path, database_url) as conn:
        if user_id is not None:
            row = conn.execute(
                """
                SELECT id, created_at, scope, since_at, until_at, status,
                       title, summary, content, model, error
                FROM briefings
                WHERE id = %s AND user_id = %s
                """,
                (briefing_id, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, created_at, scope, since_at, until_at, status,
                       title, summary, content, model, error
                FROM briefings
                WHERE id = %s AND user_id IS NULL
                """,
                (briefing_id,),
            ).fetchone()
        if row is None:
            return None
        briefing = row_to_dict(row)
        briefing["content"] = _coerce_content(briefing.get("content"))
        briefing["articles"] = _fetch_cited_articles(conn, briefing["id"])
        return briefing
