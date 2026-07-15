"""Proactive AI watchlist matching and nudge generation.

A watchlist lets a user describe a topic or goal (free-text query) and get
notified when a newly ingested article matches it. Matching runs in two
layers:

1. Deterministic term-overlap scoring against title/summary/tags — always
   available, works with zero AI configuration.
2. Optional LLM judgment (only attempted when an AI key is configured) that
   replaces the deterministic score with a more nuanced one.

The scheduled evaluator only reads articles and writes ``user_ai_nudges``
rows (plus an optional push notification); it never mutates article state
(star/archive/etc) — see issue #755.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.5
_MAX_LABEL_LEN = 120
_MAX_QUERY_LEN = 500
_PREVIEW_LIMIT = 10
_EVAL_CANDIDATES_LIMIT = 25  # recent articles considered per watchlist per run
_AI_MAX_ARTICLE_CHARS = 2_000
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "in",
        "on",
        "for",
        "to",
        "is",
        "are",
        "about",
        "with",
        "new",
        "news",
    }
)

_AI_JUDGE_PROMPT = (
    "You judge whether a news article matches a user's watchlist topic. "
    "Given the watchlist description and the article title/summary, respond "
    "with ONLY a JSON object (no prose, no code fences) shaped "
    '{"score": <0.0-1.0>, "explanation": "<one short sentence>"}. '
    "score reflects how relevant the article is to the watchlist topic."
)


class WatchlistNotFoundError(Exception):
    """Raised when a watchlist id doesn't exist or isn't owned by the user."""


# ── matching ─────────────────────────────────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def _article_text(article: dict[str, Any]) -> str:
    parts = [
        str(article.get("title") or ""),
        str(article.get("summary") or ""),
        str(article.get("tags") or ""),
    ]
    return " ".join(p for p in parts if p)


def deterministic_match(query: str, article: dict[str, Any]) -> tuple[float, str]:
    """Score 0..1 = fraction of query terms present in the article's text."""
    query_terms = _tokenize(query)
    if not query_terms:
        return 0.0, "empty watchlist query"
    article_terms = _tokenize(_article_text(article))
    matched = sorted(query_terms & article_terms)
    score = len(matched) / len(query_terms)
    explanation = f"Matched terms: {', '.join(matched)}" if matched else "No matching terms found"
    return score, explanation


def _ai_config() -> tuple[str, str | None, str] | None:
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        return None
    model = os.getenv("OPENAI_WATCHLIST_MODEL", "gpt-4o-mini")
    return api_key, base_url, model


def _parse_ai_response(text: str) -> tuple[float, str] | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        score = float(payload.get("score", 0.0))
    except (TypeError, ValueError):
        return None
    score = max(0.0, min(1.0, score))
    explanation = str(payload.get("explanation") or "").strip()[:280]
    return score, explanation


def ai_match(
    query: str, article: dict[str, Any], *, user_id: int | None = None
) -> tuple[float, str] | None:
    """Ask the configured LLM to judge relevance.

    Returns ``None`` when no AI key is configured or the call/parse fails, so
    callers can fall back to :func:`deterministic_match`.
    """
    config = _ai_config()
    if config is None:
        return None
    api_key, base_url, model = config
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langfuse import propagate_attributes

        from news_dashboard.ai_client import (
            get_chat_model,
            get_prompt,
            langfuse_enabled,
            response_text,
        )

        prompt = get_prompt("watchlist-match", fallback=_AI_JUDGE_PROMPT)
        text = _article_text(article)[:_AI_MAX_ARTICLE_CHARS]
        chat_model = get_chat_model(api_key=api_key, base_url=base_url, model=model, max_tokens=150)
        callbacks: list[Any] = []
        if langfuse_enabled():
            from langfuse.langchain import CallbackHandler

            callbacks.append(CallbackHandler())
        template = ChatPromptTemplate.from_messages(
            [("human", "{instruction}\n\nWatchlist: {query}\n\nArticle:\n{text}")]
        )
        with propagate_attributes(
            user_id=str(user_id) if user_id is not None else None,
            tags=["watchlist"],
            trace_name="watchlist-match",
            prompt=prompt.langfuse_prompt,
        ):
            result = (template | chat_model).invoke(
                {"instruction": prompt.text, "query": query, "text": text},
                config={"callbacks": callbacks},
            )
        return _parse_ai_response(response_text(result))
    except Exception:
        logger.exception("AI watchlist match failed for query=%r", query)
        return None


AiJudge = Any  # Callable[[str, dict[str, Any]], tuple[float, str] | None]


def _score_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    threshold: float,
    ai_judge: AiJudge | None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for article in candidates:
        score, explanation = deterministic_match(query, article)
        if ai_judge is not None:
            judged = ai_judge(query, article)
            if judged is not None:
                score, explanation = judged
        if score >= threshold:
            results.append(
                {"article": article, "score": round(score, 3), "explanation": explanation}
            )
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


# ── CRUD ─────────────────────────────────────────────────────────────────────


def list_watchlists(
    user_id: int, *, db_path: Any = None, database_url: str | None = None
) -> list[dict[str, Any]]:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            "SELECT * FROM user_ai_watchlists WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_watchlist(
    user_id: int, watchlist_id: int, *, db_path: Any = None, database_url: str | None = None
) -> dict[str, Any] | None:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            "SELECT * FROM user_ai_watchlists WHERE id = %s AND user_id = %s",
            (watchlist_id, user_id),
        ).fetchone()
    return row_to_dict(row) if row else None


def create_watchlist(  # noqa: PLR0913
    user_id: int,
    label: str,
    query: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    enabled: bool = True,
    notify_push: bool = True,
    db_path: Any = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    label = label.strip()[:_MAX_LABEL_LEN]
    query = query.strip()[:_MAX_QUERY_LEN]
    if not label or not query:
        msg = "label and query are required"
        raise ValueError(msg)
    if not 0.0 <= threshold <= 1.0:
        msg = "threshold must be between 0 and 1"
        raise ValueError(msg)
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_ai_watchlists(user_id, label, query, threshold, enabled, notify_push)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user_id, label, query, threshold, enabled, notify_push),
        ).fetchone()
    return row_to_dict(row)


def update_watchlist(  # noqa: PLR0913
    user_id: int,
    watchlist_id: int,
    *,
    label: str | None = None,
    query: str | None = None,
    threshold: float | None = None,
    enabled: bool | None = None,
    notify_push: bool | None = None,
    db_path: Any = None,
    database_url: str | None = None,
) -> dict[str, Any]:
    init_db(db_path, database_url=database_url)
    fields: list[str] = []
    params: list[Any] = []
    if label is not None:
        fields.append("label = %s")
        params.append(label.strip()[:_MAX_LABEL_LEN])
    if query is not None:
        fields.append("query = %s")
        params.append(query.strip()[:_MAX_QUERY_LEN])
    if threshold is not None:
        if not 0.0 <= threshold <= 1.0:
            msg = "threshold must be between 0 and 1"
            raise ValueError(msg)
        fields.append("threshold = %s")
        params.append(threshold)
    if enabled is not None:
        fields.append("enabled = %s")
        params.append(enabled)
    if notify_push is not None:
        fields.append("notify_push = %s")
        params.append(notify_push)

    if not fields:
        existing = get_watchlist(user_id, watchlist_id, db_path=db_path, database_url=database_url)
        if existing is None:
            raise WatchlistNotFoundError(str(watchlist_id))
        return existing

    fields.append("updated_at = NOW()")
    params.extend([watchlist_id, user_id])
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            f"UPDATE user_ai_watchlists SET {', '.join(fields)} "
            "WHERE id = %s AND user_id = %s RETURNING *",
            params,
        ).fetchone()
    if row is None:
        raise WatchlistNotFoundError(str(watchlist_id))
    return row_to_dict(row)


def delete_watchlist(
    user_id: int, watchlist_id: int, *, db_path: Any = None, database_url: str | None = None
) -> bool:
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            "DELETE FROM user_ai_watchlists WHERE id = %s AND user_id = %s RETURNING id",
            (watchlist_id, user_id),
        ).fetchone()
    return row is not None


# ── preview & evaluation ─────────────────────────────────────────────────────


def preview_matches(
    user_id: int,
    query: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    limit: int = _PREVIEW_LIMIT,
    use_ai: bool = True,
    db_path: Any = None,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent articles visible to *user_id* that match *query*.

    Used by the settings UI so a user can see what a watchlist would have
    matched before saving it.
    """
    from news_dashboard.ingest.service import search_articles

    init_db(db_path, database_url=database_url)
    dsn = db_path if db_path is not None else database_url
    candidates = search_articles(
        q=query,
        limit=50,
        db_path=dsn,
        user_id=user_id,
        include_archived=False,
    )
    ai_judge = ai_match if use_ai else None
    scored = _score_candidates(query, candidates, threshold=threshold, ai_judge=ai_judge)
    return scored[:limit]


def evaluate_watchlists(
    *,
    db_path: Any = None,
    database_url: str | None = None,
    use_ai: bool = True,
    ai_judge: AiJudge | None = None,
) -> dict[str, int]:
    """Evaluate every enabled watchlist against recent visible articles.

    Creates at most one ``user_ai_nudges`` row per (user, watchlist, article)
    via a unique constraint + ``ON CONFLICT DO NOTHING``, and sends a push
    notification when the watchlist has ``notify_push`` enabled. Never
    mutates article state. A failure evaluating one watchlist does not stop
    the others.
    """
    from news_dashboard.ingest.service import search_articles
    from news_dashboard.push import send_push_for_user

    init_db(db_path, database_url=database_url)
    dsn = db_path if db_path is not None else database_url
    judge = ai_judge if ai_judge is not None else (ai_match if use_ai else None)

    with connect(db_path, database_url=database_url) as conn:
        watchlists = [
            row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM user_ai_watchlists WHERE enabled = TRUE"
            ).fetchall()
        ]

    evaluated = 0
    nudges_created = 0
    for wl in watchlists:
        evaluated += 1
        user_id = int(wl["user_id"])
        try:
            candidates = search_articles(
                q=str(wl["query"]),
                limit=_EVAL_CANDIDATES_LIMIT,
                db_path=dsn,
                user_id=user_id,
                include_archived=False,
            )
        except Exception:
            logger.exception("Watchlist evaluation: search failed for watchlist %s", wl["id"])
            continue

        threshold = float(wl["threshold"])
        matches = _score_candidates(
            str(wl["query"]), candidates, threshold=threshold, ai_judge=judge
        )
        for match in matches:
            created = _record_nudge(
                user_id=user_id,
                watchlist_id=int(wl["id"]),
                article_id=int(match["article"]["id"]),
                score=match["score"],
                explanation=match["explanation"],
                db_path=db_path,
                database_url=database_url,
            )
            if not created:
                continue
            nudges_created += 1
            if wl.get("notify_push"):
                try:
                    send_push_for_user(
                        user_id,
                        f"Watchlist: {wl['label']}",
                        str(match["article"].get("title") or ""),
                        target_url=f"/a/{match['article']['id']}",
                        database_url=dsn,
                    )
                except Exception:
                    logger.exception("Watchlist push failed for user_id=%s", user_id)

    return {"watchlists_evaluated": evaluated, "nudges_created": nudges_created}


def _record_nudge(
    *,
    user_id: int,
    watchlist_id: int,
    article_id: int,
    score: float,
    explanation: str,
    db_path: Any,
    database_url: str | None,
) -> bool:
    """Insert a nudge row; returns False when one already existed (dedup)."""
    with connect(db_path, database_url=database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO user_ai_nudges(user_id, watchlist_id, article_id, score, explanation)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, watchlist_id, article_id) DO NOTHING
            RETURNING id
            """,
            (user_id, watchlist_id, article_id, score, explanation),
        ).fetchone()
    return row is not None


def list_nudges(
    user_id: int, *, limit: int = 50, db_path: Any = None, database_url: str | None = None
) -> list[dict[str, Any]]:
    """Return recent nudges for *user_id*, most recent first."""
    init_db(db_path, database_url=database_url)
    with connect(db_path, database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT n.id, n.watchlist_id, n.article_id, n.score, n.explanation, n.created_at,
                   w.label AS watchlist_label, a.title AS article_title
            FROM user_ai_nudges n
            JOIN user_ai_watchlists w ON w.id = n.watchlist_id
            JOIN articles a ON a.id = n.article_id
            WHERE n.user_id = %s
            ORDER BY n.created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        ).fetchall()
    return [row_to_dict(r) for r in rows]
