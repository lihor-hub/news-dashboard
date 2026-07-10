"""Human-approved agent action plans for Ask AI.

Lets a user ask an actionable question ("save the top two agent stories") and
get back a proposed, allowlisted plan of article mutations. Nothing runs until
the user approves the run; approving executes only allowlisted tools against
articles visible to that user, reusing the existing workflow mutation helpers
(``transition_article_state``, ``set_article_starred``, ``send_article_later``)
rather than issuing HTTP calls internally.

Runtime SQL uses psycopg %s parameter style. No SQLite fallback.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from news_dashboard.db import connect, init_db, row_to_dict

logger = logging.getLogger(__name__)

DEFAULT_AGENT_ACTIONS_MODEL = "gpt-4o-mini"
_MAX_CANDIDATES = 25
_MAX_STEPS = 10

# Tools that mutate a single article, keyed to the (state-transition or
# helper) they map to. ``admin_only`` tools ignore ``article_id``.
_ARTICLE_TOOLS = {
    "mark_done",
    "star_article",
    "unstar_article",
    "send_later",
    "skip_article",
    "archive_article",
}
_ADMIN_TOOLS = {"refresh_feeds"}
ALLOWED_TOOLS = frozenset(_ARTICLE_TOOLS | _ADMIN_TOOLS)

_PROMPT = (
    "You are a planning assistant for a news-reading app. Given the user's "
    "request and a list of candidate articles (id, title, state, starred), "
    "decide whether the request asks for one or more concrete actions on "
    "those articles. Respond with ONLY a JSON object (no prose, no code "
    "fences) shaped exactly like: "
    '{"actionable": true|false, "steps": [{"tool": "<tool>", '
    '"article_id": <int|null>}]}. '
    "Allowed tool names: mark_done, star_article, unstar_article, "
    "send_later, skip_article, archive_article, refresh_feeds. "
    "Every tool except refresh_feeds requires an article_id taken from the "
    "candidate list; never invent an article_id. If the request is a "
    "plain question with no clear action, return "
    '{"actionable": false, "steps": []}.'
)


class AgentActionError(ValueError):
    """Raised when a plan or approval request is invalid."""


class AgentActionNotFoundError(LookupError):
    """Raised when a run is missing or not visible to the requesting user."""


def _agent_actions_ai_config() -> tuple[str, str | None, str]:
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        msg = "FREE_LLM_API_KEY (or OPENAI_API_KEY) is not configured"
        raise AgentActionError(msg)
    model = os.getenv("OPENAI_AGENT_ACTIONS_MODEL", DEFAULT_AGENT_ACTIONS_MODEL)
    return api_key, base_url, model


def _candidate_articles(query: str, user_id: int) -> list[dict[str, Any]]:
    """Return up to _MAX_CANDIDATES articles visible to *user_id* for the planner.

    Keyword search alone is unreliable for natural-language commands (its
    AND-of-tokens semantics reject something like "archive the kubernetes
    story" unless every word appears in the article), so keyword hits are
    topped up with the user's most recent visible articles.
    """
    from news_dashboard.ingest.service import list_articles, search_articles

    results = search_articles(q=query, limit=_MAX_CANDIDATES, user_id=user_id)
    seen = {r["id"] for r in results}
    if len(results) < _MAX_CANDIDATES:
        for article in list_articles(limit=_MAX_CANDIDATES, user_id=user_id):
            if article["id"] not in seen:
                results.append(article)
                seen.add(article["id"])
            if len(results) >= _MAX_CANDIDATES:
                break
    return [
        {
            "id": r["id"],
            "title": r.get("title"),
            "state": r.get("state"),
            "starred": bool(r.get("starred", False)),
        }
        for r in results
    ]


def _parse_plan_response(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    try:
        raw = json.loads(cleaned)
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _validate_steps(
    raw_steps: Any, candidate_ids: set[int], *, is_admin: bool
) -> list[dict[str, Any]]:
    """Validate and normalize planner-proposed steps, or raise AgentActionError."""
    if not isinstance(raw_steps, list):
        msg = "malformed plan: steps must be a list"
        raise AgentActionError(msg)

    steps: list[dict[str, Any]] = []
    for item in raw_steps[:_MAX_STEPS]:
        if not isinstance(item, dict):
            msg = "malformed plan: each step must be an object"
            raise AgentActionError(msg)
        tool = item.get("tool")
        if not isinstance(tool, str) or tool not in ALLOWED_TOOLS:
            msg = f"unknown tool: {tool!r}"
            raise AgentActionError(msg)
        if tool in _ADMIN_TOOLS:
            if not is_admin:
                msg = f"tool {tool!r} requires admin privileges"
                raise AgentActionError(msg)
            steps.append({"tool": tool, "article_id": None})
            continue

        article_id = item.get("article_id")
        if not isinstance(article_id, int) or isinstance(article_id, bool):
            msg = f"malformed plan: {tool!r} requires an integer article_id"
            raise AgentActionError(msg)
        if article_id not in candidate_ids:
            msg = f"invalid article id: {article_id}"
            raise AgentActionError(msg)
        steps.append({"tool": tool, "article_id": article_id})
    return steps


def plan_actions(query: str, *, user_id: int, is_admin: bool = False) -> dict[str, Any]:
    """Interpret *query* and either persist a proposed plan or report non-actionable.

    Returns ``{"actionable": False}`` when the request isn't a concrete action,
    or ``{"actionable": True, "run_id": int, "status": "proposed", "steps": [...]}``
    with a persisted, allowlisted plan. Raises AgentActionError for malformed or
    disallowed planner output; nothing is persisted in that case.
    """
    clean_query = query.strip()
    if not clean_query:
        msg = "query must not be empty"
        raise AgentActionError(msg)

    candidates = _candidate_articles(clean_query, user_id)
    candidate_ids = {c["id"] for c in candidates}

    api_key, base_url, model = _agent_actions_ai_config()
    from news_dashboard.ai_client import chat_create, get_chat_client, get_prompt

    client = get_chat_client(api_key=api_key, base_url=base_url)
    prompt = get_prompt("agent-action-planning", fallback=_PROMPT)
    user_content = f"User request: {clean_query}\n\nCandidate articles: {json.dumps(candidates)}"
    result = chat_create(
        client,
        name="agent-action-planning",
        tags=["agent-actions"],
        user_id=user_id,
        prompt=prompt,
        model=model,
        messages=[{"role": "user", "content": f"{prompt.text}\n\n{user_content}"}],
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    response_text = (result.choices[0].message.content or "").strip()
    parsed = _parse_plan_response(response_text)
    if parsed is None:
        msg = "planner returned malformed JSON"
        raise AgentActionError(msg)

    if not parsed.get("actionable"):
        return {"actionable": False}

    steps = _validate_steps(parsed.get("steps"), candidate_ids, is_admin=is_admin)
    if not steps:
        return {"actionable": False}

    articles_by_id = {c["id"]: c for c in candidates}
    init_db()
    with connect() as conn:
        run_row = conn.execute(
            """
            INSERT INTO agent_action_runs (user_id, query, plan, status)
            VALUES (%s, %s, %s::jsonb, 'proposed')
            RETURNING id, user_id, query, plan, status, created_at, updated_at
            """,
            (user_id, clean_query, json.dumps({"steps": steps})),
        ).fetchone()
        run = row_to_dict(run_row)
        run_id = run["id"]

        step_rows = []
        for ordinal, step in enumerate(steps):
            row = conn.execute(
                """
                INSERT INTO agent_action_steps
                    (run_id, ordinal, tool, article_id, args, status)
                VALUES (%s, %s, %s, %s, %s::jsonb, 'pending')
                RETURNING id, run_id, ordinal, tool, article_id, args, status,
                          result_summary, created_at, updated_at
                """,
                (run_id, ordinal, step["tool"], step["article_id"], json.dumps({})),
            ).fetchone()
            step_rows.append(row_to_dict(row))

    return {
        "actionable": True,
        "run_id": run_id,
        "status": run["status"],
        "query": clean_query,
        "steps": [
            {
                **s,
                "article_title": articles_by_id.get(s["article_id"], {}).get("title")
                if s["article_id"] is not None
                else None,
            }
            for s in step_rows
        ],
    }


def _get_run_for_user(conn: Any, run_id: int, user_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM agent_action_runs WHERE id = %s AND user_id = %s",
        (run_id, user_id),
    ).fetchone()
    return row_to_dict(row) if row is not None else None


def _get_steps(conn: Any, run_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM agent_action_steps WHERE run_id = %s ORDER BY ordinal", (run_id,)
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_run(run_id: int, *, user_id: int) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        run = _get_run_for_user(conn, run_id, user_id)
        if run is None:
            msg = f"agent action run {run_id} not found"
            raise AgentActionNotFoundError(msg)
        run["steps"] = _get_steps(conn, run_id)
    return run


def cancel_run(run_id: int, *, user_id: int) -> dict[str, Any]:
    init_db()
    with connect() as conn:
        run = _get_run_for_user(conn, run_id, user_id)
        if run is None:
            msg = f"agent action run {run_id} not found"
            raise AgentActionNotFoundError(msg)
        if run["status"] != "proposed":
            msg = f"cannot cancel a run with status {run['status']!r}"
            raise AgentActionError(msg)
        row = conn.execute(
            """
            UPDATE agent_action_runs SET status = 'cancelled', updated_at = NOW()
            WHERE id = %s
            RETURNING id, user_id, query, plan, status, created_at, updated_at
            """,
            (run_id,),
        ).fetchone()
        run = row_to_dict(row)
        run["steps"] = _get_steps(conn, run_id)
    return run


def _execute_tool(tool: str, article_id: int | None, *, user_id: int) -> str:
    """Run one allowlisted tool. Returns a concise result summary or raises."""
    from news_dashboard.ingest.service import (
        ingest_all,
        send_article_later,
        set_article_starred,
        transition_article_state,
    )

    if tool == "refresh_feeds":
        result = ingest_all()
        inserted = sum(v for v in result.results.values() if v > 0)
        return f"refreshed feeds, inserted {inserted} article(s)"

    if article_id is None:
        msg = f"tool {tool!r} requires an article_id"
        raise AgentActionError(msg)

    try:
        if tool == "mark_done":
            article = transition_article_state(article_id, "done", user_id=user_id)
        elif tool == "skip_article":
            article = transition_article_state(article_id, "skipped", user_id=user_id)
        elif tool == "archive_article":
            article = transition_article_state(article_id, "archived", user_id=user_id)
        elif tool == "star_article":
            article = set_article_starred(article_id, True, user_id=user_id)
        elif tool == "unstar_article":
            article = set_article_starred(article_id, False, user_id=user_id)
        elif tool == "send_later":
            article = send_article_later(article_id, 1, user_id=user_id)
        else:
            msg = f"unknown tool: {tool!r}"
            raise AgentActionError(msg)
    except ValueError as exc:
        raise AgentActionError(str(exc)) from exc

    if article is None:
        msg = f"article {article_id} not found or not visible"
        raise AgentActionError(msg)
    return f"{tool} applied to article {article_id}"


def approve_run(run_id: int, *, user_id: int, is_admin: bool = False) -> dict[str, Any]:
    """Approve a proposed run and execute its steps in order.

    Each step is executed independently; a failure in one step does not stop
    the remaining steps. The run's final status is 'executed' only if every
    step succeeded, otherwise 'failed'.
    """
    init_db()
    with connect() as conn:
        run = _get_run_for_user(conn, run_id, user_id)
        if run is None:
            msg = f"agent action run {run_id} not found"
            raise AgentActionNotFoundError(msg)
        if run["status"] != "proposed":
            msg = f"cannot approve a run with status {run['status']!r}"
            raise AgentActionError(msg)
        conn.execute(
            "UPDATE agent_action_runs SET status = 'approved', updated_at = NOW() WHERE id = %s",
            (run_id,),
        )
        steps = _get_steps(conn, run_id)

    all_ok = True
    for step in steps:
        tool = step["tool"]
        article_id = step["article_id"]
        if tool in _ADMIN_TOOLS and not is_admin:
            summary = f"tool {tool!r} requires admin privileges"
            status = "failed"
            all_ok = False
        else:
            try:
                summary = _execute_tool(tool, article_id, user_id=user_id)
                status = "executed"
            except AgentActionError as exc:
                summary = str(exc)
                status = "failed"
                all_ok = False
        with connect() as conn:
            conn.execute(
                "UPDATE agent_action_steps"
                " SET status = %s, result_summary = %s, updated_at = NOW()"
                " WHERE id = %s",
                (status, summary, step["id"]),
            )

    final_status = "executed" if all_ok else "failed"
    with connect() as conn:
        row = conn.execute(
            """
            UPDATE agent_action_runs SET status = %s, updated_at = NOW() WHERE id = %s
            RETURNING id, user_id, query, plan, status, created_at, updated_at
            """,
            (final_status, run_id),
        ).fetchone()
        run = row_to_dict(row)
        run["steps"] = _get_steps(conn, run_id)
    return run
