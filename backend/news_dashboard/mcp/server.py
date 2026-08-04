from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime
from functools import partial
from typing import Any, Literal, TypedDict, cast

from anyio import fail_after, to_thread
from fastmcp import FastMCP
from fastmcp.exceptions import AuthorizationError, ToolError
from fastmcp.server.auth import require_scopes
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.http import StarletteWithLifespan
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.server.middleware.rate_limiting import RateLimitError, TokenBucketRateLimiter
from fastmcp.server.middleware.response_limiting import ResponseLimitingMiddleware
from fastmcp.tools.base import ToolResult
from mcp import McpError
from mcp.types import CallToolRequestParams, ErrorData
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
)
from openai import (
    RateLimitError as OpenAIRateLimitError,
)
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from news_dashboard.assistant.service import AskExecutionPolicy
from news_dashboard.body_fetch import fetch_and_cache_body
from news_dashboard.briefings import service as briefing_service
from news_dashboard.embeddings import EmbeddingUnavailableError, MissingAICredentialsError
from news_dashboard.ingest.service import clean_html, search_articles
from news_dashboard.mcp import service
from news_dashboard.mcp.ask import AskNewsResult, shape_ask_result
from news_dashboard.mcp.auth import NewsDashboardTokenVerifier
from news_dashboard.mcp.briefings import (
    BriefingGetResult,
    BriefingListResult,
    build_briefing_get_result,
    build_briefing_list_result,
)
from news_dashboard.mcp.config import McpHttpConfig
from news_dashboard.mcp.models import (
    MAX_FILTER_VALUE_LENGTH,
    MAX_RESULT_LIMIT,
    AskCorpus,
    AskQuestion,
    BriefingId,
    BriefingLimit,
    BriefingOffset,
    DateRange,
    FilterValues,
    PositiveArticleId,
    SearchLimit,
    SearchOffset,
    SearchQuery,
    SourceCursor,
    WorkflowStates,
)
from news_dashboard.sources.service import list_sources_for_user

MCP_RATE_PER_SECOND = 2.0
MCP_BURST_CAPACITY = 10
MCP_MAX_RESPONSE_BYTES = 16_384
MCP_STRUCTURED_CONTENT_BYTES = 4_800
MCP_MAX_RATE_LIMIT_IDENTITIES = 4_096
MCP_ASK_BURST_CAPACITY = 2
MCP_ASK_REFILL_SECONDS = 30.0
MCP_ASK_FOREGROUND_TIMEOUT_SECONDS = 30.0
MCP_ASK_EXECUTION_POLICY = AskExecutionPolicy.mcp()
_INTERNAL_ERROR_MESSAGE = "Internal server error"
_ARTICLE_FIELD_BYTE_CAPS = {
    "title": 512,
    "canonical_url": 2_048,
    "source_slug": 256,
    "source_name": 512,
    "category": 128,
    "kind": 128,
    "published_at": 64,
    "discovered_at": 64,
    "summary": 2_048,
    "body": 8_192,
}
_ARTICLE_REDUCTION_ORDER = (
    "body",
    "summary",
    "title",
    "canonical_url",
    "source_name",
    "source_slug",
    "category",
    "kind",
    "published_at",
    "discovered_at",
)
_BRIEFING_NOT_FOUND_MESSAGE = "Briefing not found"

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


class _DropExtractionDetailsDuringMcp(logging.Filter):
    """Keep extraction diagnostics out of MCP while preserving other callers' logs."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: ARG002 - logging override
        return not _mcp_transport_logging.get()


for _extraction_logger_name in (
    "news_dashboard.body_fetch",
    "news_dashboard.selenium_client",
    "news_dashboard.ai_client",
    "news_dashboard.embeddings",
):
    logging.getLogger(_extraction_logger_name).addFilter(_DropExtractionDetailsDuringMcp())


def _rate_limit_client_id(_context: MiddlewareContext[Any]) -> str:
    token = get_access_token()
    if token is None or not token.client_id:
        return "unauthenticated"
    rate_limit_id = token.claims.get("rate_limit_id")
    if _valid_rate_limit_identity(rate_limit_id):
        return cast("str", rate_limit_id)
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


class _AskBucket(TypedDict):
    tokens: float
    updated_at: float


def _valid_rate_limit_identity(identity: object) -> bool:
    if not isinstance(identity, str) or not identity.startswith("mcp-rate:"):
        return False
    digest = identity.removeprefix("mcp-rate:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


class _AskRateLimiter:
    """Small deterministic LRU token bucket dedicated to generation."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_identities: int = MCP_MAX_RATE_LIMIT_IDENTITIES,
    ) -> None:
        self._clock = clock
        self._max_identities = max_identities
        self._buckets: OrderedDict[str, _AskBucket] = OrderedDict()

    def __len__(self) -> int:
        return len(self._buckets)

    def consume(self, identity: object) -> bool:
        if not _valid_rate_limit_identity(identity):
            message = "Authorization required"
            raise AuthorizationError(message)
        identity = cast("str", identity)
        now = self._clock()
        bucket = self._buckets.pop(identity, None)
        if bucket is None:
            bucket = _AskBucket(tokens=float(MCP_ASK_BURST_CAPACITY), updated_at=now)
        else:
            elapsed = max(0.0, now - bucket["updated_at"])
            bucket["tokens"] = min(
                float(MCP_ASK_BURST_CAPACITY),
                bucket["tokens"] + elapsed / MCP_ASK_REFILL_SECONDS,
            )
            bucket["updated_at"] = now
        allowed = bucket["tokens"] >= 1.0
        if allowed:
            bucket["tokens"] -= 1.0
        self._buckets[identity] = bucket
        if len(self._buckets) > self._max_identities:
            self._buckets.popitem(last=False)
        return allowed


_ASK_PUBLIC_ERRORS = {
    "ask_not_configured": "News answering is not configured.",
    "embedding_unavailable": "News retrieval is temporarily unavailable.",
    "provider_authentication_failed": "News answering provider authentication failed.",
    "provider_rate_limited": "News answering provider is rate limited; retry later.",
    "ask_timeout": "News answering timed out; retry later.",
    "ask_rate_limited": "News answering rate limit exceeded; retry later.",
    "ask_unavailable": "News answering is temporarily unavailable.",
}
_ASK_ERROR_PROVENANCE_KEY = secrets.token_bytes(32)
_ASK_ERROR_MARKER = "ndask-error:"


class _PrivateAskError(ToolError):
    """Internal provenance-bearing error converted to public text at transport."""


def _signed_ask_error_text(code: str) -> str:
    public_text = f"{code}: {_ASK_PUBLIC_ERRORS[code]}"
    signature = hmac.new(
        _ASK_ERROR_PROVENANCE_KEY,
        public_text.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{_ASK_ERROR_MARKER}{signature}:{public_text}"


def _verified_public_ask_error(value: object) -> str | None:
    if not isinstance(value, str) or not value.startswith(_ASK_ERROR_MARKER):
        return None
    signed_value = value.removeprefix(_ASK_ERROR_MARKER)
    signature, separator, public_text = signed_value.partition(":")
    if not separator or len(signature) != 64:
        return None
    expected_signature = hmac.new(
        _ASK_ERROR_PROVENANCE_KEY,
        public_text.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None
    if public_text not in {f"{code}: {message}" for code, message in _ASK_PUBLIC_ERRORS.items()}:
        return None
    return public_text


def _fixed_ask_error(code: str) -> _PrivateAskError:
    return _PrivateAskError(_signed_ask_error_text(code))


def _public_ask_error(exc: Exception) -> _PrivateAskError:
    if isinstance(exc, MissingAICredentialsError):
        code = "ask_not_configured"
    elif isinstance(exc, EmbeddingUnavailableError):
        code = "embedding_unavailable"
    elif isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        code = "provider_authentication_failed"
    elif isinstance(exc, OpenAIRateLimitError):
        code = "provider_rate_limited"
    elif isinstance(exc, (TimeoutError, APITimeoutError)):
        code = "ask_timeout"
    elif isinstance(exc, (APIConnectionError, APIStatusError)):
        code = "ask_unavailable"
    else:
        code = "ask_unavailable"
    return _fixed_ask_error(code)


def _ask_rate_limit_identity() -> str:
    token = get_access_token()
    identity = token.claims.get("rate_limit_id") if token is not None else None
    if not _valid_rate_limit_identity(identity):
        message = "Authorization required"
        raise AuthorizationError(message)
    return cast("str", identity)


def _safe_trace_id(result: object) -> str | None:
    if not isinstance(result, dict):
        return None
    trace_id = result.get("trace_id")
    if (
        not isinstance(trace_id, str)
        or len(trace_id) != 32
        or any(character not in "0123456789abcdefABCDEF" for character in trace_id)
    ):
        return None
    return trace_id.lower()


def _record_ask_result(
    trace_id: str,
    *,
    citation_count: int,
    truncated: bool,
    status: Literal["ok", "error"],
) -> None:
    from news_dashboard.ai_client import record_mcp_ask_result

    record_mcp_ask_result(
        trace_id,
        citation_count=citation_count,
        truncated=truncated,
        status=status,
    )


class _AskRateLimitingMiddleware(Middleware):
    def __init__(self, *, limiter: _AskRateLimiter | None = None) -> None:
        self._limiter = limiter or _AskRateLimiter()

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        if context.message.name != "ask_news":
            return await call_next(context)
        if not self._limiter.consume(_ask_rate_limit_identity()):
            code = "ask_rate_limited"
            raise _fixed_ask_error(code)
        return await call_next(context)


def _is_safe_ask_tool_error(result: ToolResult) -> bool:
    if len(result.content) != 1:
        return False
    text = getattr(result.content[0], "text", None)
    return _verified_public_ask_error(text) is not None


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
                if context.message.name == "ask_news" and _is_safe_ask_tool_error(result):
                    return result
                return ToolResult(
                    content=_INTERNAL_ERROR_MESSAGE,
                    is_error=True,
                )
            return result
        except _PrivateAskError:
            status = "error"
            if context.message.name == "ask_news":
                raise
            raise McpError(ErrorData(code=-32603, message=_INTERNAL_ERROR_MESSAGE)) from None
        except ToolError as exc:
            status = "error"
            if str(exc) == _BRIEFING_NOT_FOUND_MESSAGE:
                raise
            raise McpError(ErrorData(code=-32603, message=_INTERNAL_ERROR_MESSAGE)) from None
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
mcp.add_middleware(_AskRateLimitingMiddleware())
mcp.add_middleware(ResponseLimitingMiddleware(max_size=MCP_MAX_RESPONSE_BYTES))


class ArticleListResult(TypedDict):
    articles: list[dict[str, Any]]
    truncated: bool


class SourceListResult(TypedDict):
    sources: list[dict[str, str]]
    truncated: bool
    next_cursor: str | None


class NewsArticleBody(TypedDict):
    id: int
    title: str
    canonical_url: str
    source_slug: str
    source_name: str
    category: str
    kind: str
    published_at: str | None
    discovered_at: str | None
    summary: str
    body: str
    body_truncated: bool


class GetNewsArticleResult(TypedDict):
    found: bool
    article: NewsArticleBody | None
    truncated: bool


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
            "next_cursor": str(candidate_cursor) if candidate_cursor < len(sources) else None,
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
        "next_cursor": str(cursor) if cursor < len(sources) else None,
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
    compact = {
        "slug": str(source["slug"]),
        "name": str(source["name"])[:MAX_FILTER_VALUE_LENGTH],
        "category": str(source["category"]),
        "kind": str(source["kind"])[:MAX_FILTER_VALUE_LENGTH],
    }
    while _single_source_result_size(compact) > MCP_STRUCTURED_CONTENT_BYTES:
        name_bytes = len(json.dumps(compact["name"], ensure_ascii=True).encode())
        kind_bytes = len(json.dumps(compact["kind"], ensure_ascii=True).encode())
        if name_bytes >= kind_bytes and compact["name"]:
            compact["name"] = compact["name"][:-1]
        elif compact["kind"]:
            compact["kind"] = compact["kind"][:-1]
        else:
            message = "Exact source filter values exceed structured content budget"
            raise ValueError(message)
    return compact


def _single_source_result_size(source: dict[str, str]) -> int:
    envelope: SourceListResult = {
        "sources": [source],
        "truncated": False,
        "next_cursor": "9" * 20,
    }
    return len(json.dumps(envelope, ensure_ascii=True, separators=(",", ":")).encode())


def _has_valid_filter_value(source: dict[str, Any], key: str) -> bool:
    value = source.get(key)
    return (
        isinstance(value, str)
        and value == value.strip()
        and 0 < len(value) <= MAX_FILTER_VALUE_LENGTH
    )


def _serialized_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    rendered = str(value)
    try:
        return datetime.fromisoformat(rendered).isoformat()
    except ValueError:
        return rendered


def _escaped_plain_text(value: object) -> str:
    """Return canonical whitespace-normalized text safe to embed in any markup."""
    return html.escape(clean_html(str(value or "")), quote=True)


def _utf8_prefix(value: str, max_bytes: int) -> str:
    """Take a deterministic prefix without splitting a UTF-8 code point."""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _structured_size(value: GetNewsArticleResult) -> int:
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))


def _largest_fitting_prefix(
    result: GetNewsArticleResult, article: dict[str, Any], field: str
) -> str | None:
    current = article[field]
    if current is None:
        return None
    value = cast("str", current)
    low = 0
    high = len(value)
    best = ""
    while low <= high:
        middle = (low + high) // 2
        candidate = value[:middle]
        article[field] = candidate
        if _structured_size(result) <= MCP_STRUCTURED_CONTENT_BYTES:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    article[field] = best
    return best


def _bounded_news_article(raw_article: dict[str, Any]) -> GetNewsArticleResult:
    """Build a sanitized required-key article result under the structured limit."""
    published_at = _serialized_timestamp(raw_article.get("published_at"))
    discovered_at = _serialized_timestamp(raw_article.get("discovered_at"))
    raw_text = {
        "title": _escaped_plain_text(raw_article.get("title")),
        "canonical_url": str(raw_article.get("canonical_url") or raw_article.get("url") or ""),
        "source_slug": _escaped_plain_text(raw_article.get("source_slug")),
        "source_name": _escaped_plain_text(raw_article.get("source_name")),
        "category": _escaped_plain_text(raw_article.get("category")),
        "kind": _escaped_plain_text(raw_article.get("kind")),
        "published_at": _escaped_plain_text(published_at) if published_at is not None else None,
        "discovered_at": (
            _escaped_plain_text(discovered_at) if discovered_at is not None else None
        ),
        "summary": _escaped_plain_text(raw_article.get("summary")),
        "body": _escaped_plain_text(raw_article.get("body")),
    }
    bounded_text = {
        field: _utf8_prefix(value, _ARTICLE_FIELD_BYTE_CAPS[field]) if value is not None else None
        for field, value in raw_text.items()
    }
    shortened_fields = {field for field, value in bounded_text.items() if value != raw_text[field]}
    article: dict[str, Any] = {
        "id": int(raw_article["id"]),
        **bounded_text,
        "body_truncated": "body" in shortened_fields,
    }
    result = cast(
        "GetNewsArticleResult",
        {"found": True, "article": article, "truncated": bool(shortened_fields)},
    )
    for field in _ARTICLE_REDUCTION_ORDER:
        if _structured_size(result) <= MCP_STRUCTURED_CONTENT_BYTES:
            break
        before = cast("str", article[field])
        after = _largest_fitting_prefix(result, article, field)
        if after != before:
            shortened_fields.add(field)
            result["truncated"] = True
            if field == "body":
                article["body_truncated"] = True
    if _structured_size(result) > MCP_STRUCTURED_CONTENT_BYTES:
        message = "Article metadata cannot fit MCP structured response limit"
        raise ValueError(message)
    return result


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
    cursor: SourceCursor | None = None,
) -> SourceListResult:
    """Page through searchable sources in canonical order.

    Use limit 1..25 and an optional canonical ASCII-decimal cursor of at most 20 digits.
    Continue from next_cursor until it is null; every server-generated cursor is accepted.
    Whole compact records fit a 4,800-byte budget; truncation means the size budget
    ended a page early. Exact slug and category values are always returned. Sources
    with invalid filter values are omitted, while display-only name and kind values
    are capped at 120 characters and shortened further only when JSON escaping requires
    it, so every searchable slug remains reachable.
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
    offset = int(cursor) if cursor is not None else 0
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


@mcp.tool(auth=require_scopes("ask"))
async def ask_news(
    question: AskQuestion,
    corpus: AskCorpus = "saved_and_read",
) -> AskNewsResult:
    """Answer a question over the authenticated owner's news corpus."""
    from news_dashboard.assistant import service as assistant_service

    user_id = _current_user_id()
    result: dict[str, Any] | None = None
    try:
        with fail_after(MCP_ASK_FOREGROUND_TIMEOUT_SECONDS):
            result = await to_thread.run_sync(
                lambda: assistant_service.ask(
                    question,
                    include_all=corpus == "all_visible",
                    user_id=user_id,
                    execution_policy=MCP_ASK_EXECUTION_POLICY,
                ),
                abandon_on_cancel=True,
            )
        response = shape_ask_result(result)
        trace_id = response["trace_id"]
        if trace_id is not None:
            _record_ask_result(
                trace_id,
                citation_count=len(response["citations"]),
                truncated=response["truncated"],
                status="ok",
            )
        return response
    except Exception as exc:
        trace_id = _safe_trace_id(result)
        if trace_id is not None:
            _record_ask_result(
                trace_id,
                citation_count=0,
                truncated=False,
                status="error",
            )
        raise _public_ask_error(exc) from None


@mcp.tool(auth=require_scopes("read"))
def get_news_article(article_id: PositiveArticleId) -> GetNewsArticleResult:
    """Return one article visible to the authenticated token owner."""
    article = fetch_and_cache_body(article_id, user_id=_current_user_id())
    if article is None:
        return {"found": False, "article": None, "truncated": False}
    return _bounded_news_article(article)


@mcp.tool(auth=require_scopes("briefings"))
async def list_briefings(
    limit: BriefingLimit = 10,
    offset: BriefingOffset = 0,
) -> BriefingListResult:
    """List complete saved briefings owned by the authenticated token user."""
    user_id = _current_user_id()
    rows = await to_thread.run_sync(
        partial(
            briefing_service.list_briefings,
            limit=limit + 1,
            offset=offset,
            user_id=user_id,
            status="complete",
        )
    )
    return build_briefing_list_result(rows, offset=offset, requested_limit=limit)


@mcp.tool(auth=require_scopes("briefings"))
async def get_briefing(briefing_id: BriefingId) -> BriefingGetResult:
    """Get one complete saved briefing owned by the authenticated token user."""
    user_id = _current_user_id()
    row = await to_thread.run_sync(
        partial(
            briefing_service.get_briefing,
            briefing_id,
            user_id=user_id,
            status="complete",
        )
    )
    if row is None:
        raise ToolError(_BRIEFING_NOT_FOUND_MESSAGE)
    return build_briefing_get_result(row)


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
    content = result.get("content")
    if (
        isinstance(content, list)
        and len(content) == 1
        and isinstance(content[0], dict)
        and content[0].get("type") == "text"
    ):
        if content[0].get("text") == _BRIEFING_NOT_FOUND_MESSAGE:
            return body
        public_error = _verified_public_ask_error(content[0].get("text"))
        if public_error is not None:
            content[0]["text"] = public_error
        else:
            result["content"] = [{"type": "text", "text": _INTERNAL_ERROR_MESSAGE}]
    else:
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


class _ExactMcpHostOrigin:
    """Reject untrusted routing headers before FastMCP authentication runs."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: tuple[str, ...],
        allowed_origins: tuple[str, ...],
    ) -> None:
        self.app = app
        self.allowed_hosts = frozenset(allowed_hosts)
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {name.lower(): value for name, value in scope["headers"]}
        host = headers.get(b"host", b"").decode("latin-1")
        if host not in self.allowed_hosts:
            await PlainTextResponse("Misdirected Request", status_code=421)(scope, receive, send)
            return

        origin_value = headers.get(b"origin")
        if origin_value is not None:
            origin = origin_value.decode("latin-1")
            if origin not in self.allowed_origins:
                await PlainTextResponse("Forbidden", status_code=403)(scope, receive, send)
                return

        await self.app(scope, receive, send)


def create_mcp_http_app(server: FastMCP[Any], *, config: McpHttpConfig) -> StarletteWithLifespan:
    """Build the guarded MCP ASGI application mounted by FastAPI."""
    http_app = server.http_app(
        path="/",
        stateless_http=True,
        transport="http",
        host_origin_protection=True,
        allowed_hosts=list(config.allowed_hosts),
        allowed_origins=list(config.allowed_origins),
    )
    http_app.add_middleware(_RequireMcpEnabled)
    http_app.add_middleware(_SanitizeMcpResponses)
    http_app.add_middleware(
        _ExactMcpHostOrigin,
        allowed_hosts=config.allowed_hosts,
        allowed_origins=config.allowed_origins,
    )
    return http_app


mcp_http_app = create_mcp_http_app(mcp, config=McpHttpConfig.from_environment())
