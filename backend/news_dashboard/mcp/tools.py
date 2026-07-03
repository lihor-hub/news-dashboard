from __future__ import annotations

from typing import Any

from news_dashboard.mcp.models import MAX_QUERY_LENGTH, MAX_RESULT_LIMIT

TOOLS: dict[str, dict[str, Any]] = {
    "search_articles": {
        "scope": "search",
        "description": "Search articles visible to the token owner.",
    },
    "get_article": {
        "scope": "read",
        "description": "Fetch a single visible article by id.",
    },
    "list_briefings": {
        "scope": "briefings",
        "description": "List the token owner's recent briefings (metadata only).",
    },
    "ask": {
        "scope": "ask",
        "description": "Ask a question answered via retrieval over the user's corpus.",
    },
}


class ToolError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _require_scope(scopes: set[str], tool_name: str) -> None:
    required = TOOLS[tool_name]["scope"]
    if required not in scopes:
        message = f"token is missing required scope '{required}' for tool '{tool_name}'"
        raise ToolError(message, status_code=403)


def _clamp_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = MAX_RESULT_LIMIT
    return max(1, min(limit, MAX_RESULT_LIMIT))


def _clean_query(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) > MAX_QUERY_LENGTH:
        message = f"query must be at most {MAX_QUERY_LENGTH} characters"
        raise ToolError(message)
    return text


def call_tool(
    tool_name: str, arguments: dict[str, Any], *, user_id: int, scopes: set[str]
) -> dict[str, Any]:
    if tool_name not in TOOLS:
        message = f"unknown tool '{tool_name}'"
        raise ToolError(message, status_code=404)
    _require_scope(scopes, tool_name)

    if tool_name == "search_articles":
        from news_dashboard.ingest import search_articles

        q = _clean_query(arguments.get("q", ""))
        limit = _clamp_limit(arguments.get("limit", MAX_RESULT_LIMIT))
        results = search_articles(q=q, limit=limit, user_id=user_id)
        return {"articles": results}

    if tool_name == "get_article":
        from news_dashboard.body_fetch import get_article

        raw_article_id = arguments.get("article_id")
        if raw_article_id is None:
            message = "article_id must be an integer"
            raise ToolError(message)
        try:
            article_id = int(raw_article_id)
        except (TypeError, ValueError) as exc:
            message = "article_id must be an integer"
            raise ToolError(message) from exc
        article = get_article(article_id, user_id=user_id)
        if article is None:
            message = "article not found"
            raise ToolError(message, status_code=404)
        return {"article": article}

    if tool_name == "list_briefings":
        from news_dashboard.briefings import list_briefings

        limit = _clamp_limit(arguments.get("limit", MAX_RESULT_LIMIT))
        briefings = list_briefings(limit=limit, user_id=user_id)
        return {"briefings": briefings}

    if tool_name == "ask":
        from news_dashboard.embeddings import ask

        query = _clean_query(arguments.get("query", ""))
        if not query:
            message = "query must not be empty"
            raise ToolError(message)
        include_all = bool(arguments.get("include_all", False))
        return ask(query, include_all=include_all, user_id=user_id)

    message = f"tool '{tool_name}' is not implemented"
    raise ToolError(message, status_code=501)
