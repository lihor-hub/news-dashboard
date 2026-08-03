from __future__ import annotations

import logging
import time
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import require_scopes
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware
from fastmcp.tools.base import ToolResult
from mcp import McpError
from mcp.types import CallToolRequestParams, ErrorData
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from news_dashboard.ingest.service import search_articles
from news_dashboard.mcp import service
from news_dashboard.mcp.auth import NewsDashboardTokenVerifier
from news_dashboard.mcp.models import MAX_RESULT_LIMIT, FilterValues

MCP_RATE_PER_SECOND = 2.0
MCP_BURST_CAPACITY = 10
MCP_MAX_RESPONSE_BYTES = 16_384
_INTERNAL_ERROR_MESSAGE = "Internal server error"

logger = logging.getLogger("news_dashboard.mcp")


class _DropFastMcpToolExceptionLogs(logging.Filter):
    """Prevent FastMCP's exception logger from recording private tool data."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Error calling tool")


logging.getLogger("fastmcp.server.server").addFilter(_DropFastMcpToolExceptionLogs())


def _rate_limit_client_id(_context: MiddlewareContext[Any]) -> str:
    token = get_access_token()
    if token is None or not token.client_id:
        return "unauthenticated"
    return token.client_id


class _SafeToolTelemetryMiddleware(Middleware):
    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        started_at = time.perf_counter()
        status = "success"
        try:
            return await call_next(context)
        except McpError:
            status = "error"
            raise
        except Exception:
            status = "error"
            raise McpError(ErrorData(code=-32603, message=_INTERNAL_ERROR_MESSAGE)) from None
        finally:
            duration_ms = (time.perf_counter() - started_at) * 1_000
            logger.info(
                "mcp tool=%s status=%s duration_ms=%.2f",
                context.message.name,
                status,
                duration_ms,
            )


mcp = FastMCP(
    "News Dashboard",
    auth=NewsDashboardTokenVerifier(),
    mask_error_details=True,
    strict_input_validation=True,
)
mcp.add_middleware(_SafeToolTelemetryMiddleware())
mcp.add_middleware(
    RateLimitingMiddleware(
        max_requests_per_second=MCP_RATE_PER_SECOND,
        burst_capacity=MCP_BURST_CAPACITY,
        get_client_id=_rate_limit_client_id,
    )
)
mcp.add_middleware(ResponseLimitingMiddleware(max_size=MCP_MAX_RESPONSE_BYTES))


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
