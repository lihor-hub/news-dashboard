from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from contextvars import ContextVar
from typing import Any, Literal, TypedDict

from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.auth import require_scopes
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.rate_limiting import RateLimitError, TokenBucketRateLimiter
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware
from fastmcp.tools.base import ToolResult
from mcp import McpError
from mcp.types import CallToolRequestParams, ErrorData
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from news_dashboard.ingest.service import search_articles
from news_dashboard.mcp import service
from news_dashboard.mcp.auth import NewsDashboardTokenVerifier
from news_dashboard.mcp.models import (
    MAX_FILTER_VALUE_LENGTH,
    MAX_RESULT_LIMIT,
    DateRange,
    FilterValues,
    SearchLimit,
    SearchOffset,
    SearchQuery,
    WorkflowStates,
)
from news_dashboard.sources.service import list_sources_for_user

MCP_RATE_PER_SECOND = 2.0
MCP_BURST_CAPACITY = 10
MCP_MAX_RESPONSE_BYTES = 16_384
MCP_STRUCTURED_CONTENT_BYTES = 4_800
MCP_MAX_RATE_LIMIT_IDENTITIES = 4_096
_INTERNAL_ERROR_MESSAGE = "Internal server error"

logger = logging.getLogger("news_dashboard.mcp")
_mcp_transport_logging = ContextVar("mcp_transport_logging", default=False)


class _DropFastMcpToolExceptionLogs(logging.Filter):
    """Prevent FastMCP's exception logger from recording private tool data."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not message.startswith(("Error calling tool", "Invalid arguments for tool"))


logging.getLogger("fastmcp.server.server").addFilter(_DropFastMcpToolExceptionLogs())


class _DropMcpSsePayloadLogs(logging.Filter):
    """Drop raw SSE chunks only while this app is serving an MCP request."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (_mcp_transport_logging.get() and record.getMessage().startswith("chunk:"))


logging.getLogger("sse_starlette.sse").addFilter(_DropMcpSsePayloadLogs())


def _rate_limit_client_id(_context: MiddlewareContext[Any]) -> str:
    token = get_access_token()
    if token is None or not token.client_id:
        return "unauthenticated"
    rate_limit_id = token.claims.get("rate_limit_id")
    if isinstance(rate_limit_id, str) and rate_limit_id.startswith("mcp-rate:"):
        return rate_limit_id
    message = "Authorization required"
    raise AuthorizationError(message)


class _BoundedTokenBuckets:
    def __init__(self, *, max_identities: int, capacity: int, refill_rate: float) -> None:
        self._max_identities = max_identities
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._buckets: OrderedDict[str, TokenBucketRateLimiter] = OrderedDict()

    def __len__(self) -> int:
        return len(self._buckets)

    def for_client(self, client_id: str) -> TokenBucketRateLimiter:
        bucket = self._buckets.pop(client_id, None)
        if bucket is None:
            bucket = TokenBucketRateLimiter(self._capacity, self._refill_rate)
        self._buckets[client_id] = bucket
        if len(self._buckets) > self._max_identities:
            self._buckets.popitem(last=False)
        return bucket


class _BoundedRateLimitingMiddleware(Middleware):
    def __init__(self) -> None:
        self._buckets = _BoundedTokenBuckets(
            max_identities=MCP_MAX_RATE_LIMIT_IDENTITIES,
            capacity=MCP_BURST_CAPACITY,
            refill_rate=MCP_RATE_PER_SECOND,
        )

    async def on_request(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
    ) -> Any:
        client_id = _rate_limit_client_id(context)
        if not await self._buckets.for_client(client_id).consume():
            message = "Rate limit exceeded"
            raise RateLimitError(message)
        return await call_next(context)


class _SafeToolTelemetryMiddleware(Middleware):
    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        started_at = time.perf_counter()
        status = "success"
        try:
            result = await call_next(context)
            if result.is_error:
                status = "error"
                return ToolResult(
                    content=_INTERNAL_ERROR_MESSAGE,
                    is_error=True,
                )
            return result
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
mcp.add_middleware(_BoundedRateLimitingMiddleware())
mcp.add_middleware(ResponseLimitingMiddleware(max_size=MCP_MAX_RESPONSE_BYTES))


class ArticleListResult(TypedDict):
    articles: list[dict[str, Any]]
    truncated: bool


class SourceListResult(TypedDict):
    sources: list[dict[str, str]]
    truncated: bool
    next_offset: int | None


def _bounded_articles(articles: list[dict[str, Any]]) -> ArticleListResult:
    accepted: list[dict[str, Any]] = []
    for article in articles:
        candidate: ArticleListResult = {
            "articles": [*accepted, _compact_article(article)],
            "truncated": False,
        }
        serialized = json.dumps(
            candidate,
            default=str,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode()
        if len(serialized) > MCP_STRUCTURED_CONTENT_BYTES:
            return {"articles": accepted, "truncated": True}
        accepted = candidate["articles"]
    return {"articles": accepted, "truncated": False}


def _bounded_sources(
    sources: list[dict[str, Any]], *, limit: SearchLimit, offset: SearchOffset
) -> SourceListResult:
    accepted: list[dict[str, str]] = []
    cursor = offset
    page_end = min(len(sources), offset + limit)
    truncated = False
    while cursor < page_end:
        source = sources[cursor]
        candidate_cursor = cursor + 1
        candidate: SourceListResult = {
            "sources": [*accepted, _compact_source(source)],
            "truncated": False,
            "next_offset": candidate_cursor if candidate_cursor < len(sources) else None,
        }
        serialized = json.dumps(candidate, ensure_ascii=True, separators=(",", ":")).encode()
        if len(serialized) > MCP_STRUCTURED_CONTENT_BYTES:
            truncated = True
            if accepted:
                break
            message = "Compact source exceeds structured content budget"
            raise ValueError(message)
        accepted = candidate["sources"]
        cursor = candidate_cursor
    return {
        "sources": accepted,
        "truncated": truncated,
        "next_offset": cursor if cursor < len(sources) else None,
    }


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
        "url": article.get("canonical_url") or article["url"],
        "source_slug": article["source_slug"],
        "source_name": article["source_name"],
        "category": article["category"],
        "published_at": article["published_at"],
        "summary": article["summary"],
        "state": article["state"],
        "starred": bool(article.get("starred", False)),
    }


def _compact_source(source: dict[str, Any]) -> dict[str, str]:
    return {
        "slug": str(source["slug"]),
        "name": str(source["name"])[:MAX_FILTER_VALUE_LENGTH],
        "category": str(source["category"]),
        "kind": str(source["kind"])[:MAX_FILTER_VALUE_LENGTH],
    }


def _has_valid_filter_value(source: dict[str, Any], key: str) -> bool:
    value = source.get(key)
    return (
        isinstance(value, str)
        and value == value.strip()
        and 0 < len(value) <= MAX_FILTER_VALUE_LENGTH
    )


@mcp.tool(auth=require_scopes("search"))
def list_latest_news(
    limit: int = 10,
    sources: FilterValues | None = None,
    categories: FilterValues | None = None,
    states: FilterValues | None = None,
    date_range: Literal["all", "day", "week", "month"] = "all",
    include_archived: bool = False,
) -> ArticleListResult:
    """List recent articles visible to the authenticated token owner."""
    bounded_limit = max(1, min(limit, MAX_RESULT_LIMIT))
    articles = search_articles(
        q="",
        limit=bounded_limit,
        states=list(states) if states is not None else None,
        categories=categories,
        sources=sources,
        include_archived=include_archived,
        date_range="today" if date_range == "day" else date_range,
        user_id=_current_user_id(),
    )
    return _bounded_articles(articles)


@mcp.tool(auth=require_scopes("search"))
def list_news_sources(
    limit: SearchLimit = 25,
    offset: SearchOffset = 0,
) -> SourceListResult:
    """Page through searchable sources in canonical order.

    Use limit 1..25 and offset 0..10000. Continue from next_offset until it is null.
    Whole compact records fit a 4,800-byte budget; truncation means the size budget
    ended a page early. Exact slug and category values are always returned. Sources
    with invalid filter values are omitted, while display-only name and kind values
    are shortened to 120 characters so every searchable slug remains reachable.
    """
    sources = list_sources_for_user(_current_user_id())
    searchable = [
        source
        for source in sources
        if bool(source["subscribed"])
        and bool(source["enabled"])
        and _has_valid_filter_value(source, "slug")
        and _has_valid_filter_value(source, "category")
    ]
    return _bounded_sources(searchable, limit=limit, offset=offset)


@mcp.tool(auth=require_scopes("search"))
def search_news(  # noqa: PLR0913, PLR0917
    q: SearchQuery = "",
    sources: FilterValues | None = None,
    categories: FilterValues | None = None,
    date_range: DateRange = "all",
    states: WorkflowStates | None = None,
    starred_only: bool = False,
    include_archived: bool = False,
    limit: SearchLimit = 10,
    offset: SearchOffset = 0,
) -> ArticleListResult:
    """Search the authenticated owner's news without returning full bodies.

    An empty query returns a filtered recent listing in the web search's canonical order.
    Multiple values within source, category, or state filters combine with OR; distinct
    filter groups combine with AND. Date windows use discovery time: day, week, and month
    cover the trailing 1, 7, and 30 days. Archived articles are excluded unless requested;
    an explicit archived state overrides that default. Starred state belongs only to the
    authenticated owner. Page with limit 1..25 and offset 0..10000. Results contain whole
    compact records only and report truncation if the 4,800-byte structured budget fills.
    """
    articles = search_articles(
        q=q,
        sources=sources,
        categories=categories,
        date_range="today" if date_range == "day" else date_range,
        states=list(states) if states is not None else None,
        starred_only=starred_only,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        user_id=_current_user_id(),
    )
    return _bounded_articles(articles)


def _sanitize_mcp_response_body(body: bytes) -> bytes:
    marker = b"data: "
    start = body.find(marker)
    if start < 0:
        return body
    data_start = start + len(marker)
    data_end = body.find(b"\r\n", data_start)
    if data_end < 0:
        return body
    try:
        payload = json.loads(body[data_start:data_end])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("isError") is not True:
        return body
    result["content"] = [{"type": "text", "text": _INTERNAL_ERROR_MESSAGE}]
    sanitized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return body[:data_start] + sanitized + body[data_end:]


class _SanitizeMcpResponses:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def sanitized_send(message: Message) -> None:
            if message["type"] == "http.response.body" and message.get("body"):
                message = {**message, "body": _sanitize_mcp_response_body(message["body"])}
            await send(message)

        context_token = _mcp_transport_logging.set(True)
        try:
            await self.app(scope, receive, sanitized_send)
        finally:
            _mcp_transport_logging.reset(context_token)


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
mcp_http_app.add_middleware(_SanitizeMcpResponses)
