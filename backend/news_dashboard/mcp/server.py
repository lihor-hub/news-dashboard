from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import require_scopes
from fastmcp.server.dependencies import get_access_token
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from news_dashboard.ingest.service import search_articles
from news_dashboard.mcp import service
from news_dashboard.mcp.auth import NewsDashboardTokenVerifier
from news_dashboard.mcp.models import MAX_RESULT_LIMIT, FilterValues

mcp = FastMCP(
    "News Dashboard",
    auth=NewsDashboardTokenVerifier(),
    mask_error_details=True,
    strict_input_validation=True,
)


def _current_user_id() -> int:
    token = get_access_token()
    if token is None:
        message = "Authorization required"
        raise AuthorizationError(message)
    user_id = token.claims.get("user_id")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        message = "Authorization required"
        raise AuthorizationError(message)
    return user_id


def _compact_article(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": article["id"],
        "title": article["title"],
        "url": article["url"],
        "source_slug": article["source_slug"],
        "source_name": article["source_name"],
        "category": article["category"],
        "published_at": article["published_at"],
        "discovered_at": article["discovered_at"],
        "summary": article["summary"],
        "state": article["state"],
    }


@mcp.tool(auth=require_scopes("search"))
def list_latest_news(
    limit: int = 10,
    sources: FilterValues | None = None,
    categories: FilterValues | None = None,
    states: FilterValues | None = None,
    date_range: Literal["all", "day", "week", "month"] = "all",
    include_archived: bool = False,
) -> dict[str, Any]:
    """List recent articles visible to the authenticated token owner."""
    bounded_limit = max(1, min(limit, MAX_RESULT_LIMIT))
    articles = search_articles(
        q="",
        limit=bounded_limit,
        states=states,
        categories=categories,
        sources=sources,
        include_archived=include_archived,
        date_range="today" if date_range == "day" else date_range,
        user_id=_current_user_id(),
    )
    return {"articles": [_compact_article(article) for article in articles]}


class _RequireMcpEnabled:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not service.mcp_enabled():
            await PlainTextResponse("Not Found", status_code=404)(scope, receive, send)
            return
        await self.app(scope, receive, send)


mcp_http_app = mcp.http_app(path="/", stateless_http=True, transport="http")
mcp_http_app.add_middleware(_RequireMcpEnabled)
