from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from news_dashboard.main import app


def test_mcp_health_reports_disabled_without_touching_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("MCP_SERVER_ENABLED", "false")

    def unexpected_check() -> None:
        message = "disabled MCP health must not touch PostgreSQL"
        raise AssertionError(message)

    monkeypatch.setattr(service, "check_mcp_dependency", unexpected_check)

    response = TestClient(app).get("/api/mcp/health")

    assert response.status_code == 200
    assert response.json() == {"status": "disabled"}


def test_mcp_health_reports_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.mcp import service

    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    monkeypatch.setattr(service, "check_mcp_dependency", lambda: None)

    response = TestClient(app).get("/api/mcp/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_mcp_health_hides_dependency_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.mcp import service

    private_detail = "postgresql://private-user:private-password@database/internal"
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")

    def failed_check() -> None:
        raise RuntimeError(private_detail)

    monkeypatch.setattr(service, "check_mcp_dependency", failed_check)

    response = TestClient(app, raise_server_exceptions=False).get("/api/mcp/health")

    assert response.status_code == 503
    assert response.json() == {"status": "dependency_failure"}
    assert private_detail not in response.text


def test_mcp_metrics_have_only_fixed_cardinality_labels() -> None:
    from news_dashboard.metrics import (
        mcp_auth_attempts_total,
        mcp_rate_limits_total,
        mcp_response_limits_total,
        mcp_tool_calls_total,
        mcp_tool_duration_seconds,
    )

    assert tuple(mcp_auth_attempts_total._labelnames) == ("status",)
    assert tuple(mcp_tool_calls_total._labelnames) == ("tool", "status")
    assert tuple(mcp_tool_duration_seconds._labelnames) == ("tool", "status")
    assert tuple(mcp_rate_limits_total._labelnames) == ("status",)
    assert tuple(mcp_response_limits_total._labelnames) == ("tool",)


def test_token_verifier_records_one_metadata_only_auth_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from news_dashboard.mcp import auth
    from news_dashboard.metrics import mcp_auth_attempts_total

    bearer_token = "ndmcp_private-bearer"  # noqa: S105 -- synthetic test credential
    monkeypatch.setattr(
        "news_dashboard.mcp.auth.service.authenticate_token",
        lambda _token: {"token_id": 41, "user_id": 9, "scopes": {"search"}},
    )
    before = mcp_auth_attempts_total.labels(status="success")._value.get()
    caplog.set_level(logging.INFO, logger="news_dashboard.mcp")

    result = asyncio.run(auth.NewsDashboardTokenVerifier().verify_token(bearer_token))

    assert result is not None
    assert mcp_auth_attempts_total.labels(status="success")._value.get() == before + 1
    events = [
        record.getMessage() for record in caplog.records if "event=auth" in record.getMessage()
    ]
    assert events == ["mcp event=auth status=success token_id=41"]
    assert bearer_token not in caplog.text
    assert "user_id=9" not in caplog.text


def test_tool_telemetry_records_one_event_and_excludes_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from fastmcp.server.middleware import CallNext, MiddlewareContext
    from fastmcp.tools.base import ToolResult
    from mcp.types import CallToolRequestParams

    from news_dashboard.mcp.server import _SafeToolTelemetryMiddleware
    from news_dashboard.metrics import mcp_tool_calls_total

    private_content = "private prompt and article body"
    context = type(
        "Context",
        (),
        {
            "message": CallToolRequestParams(
                name="list_latest_news", arguments={"q": private_content}
            )
        },
    )()
    before = mcp_tool_calls_total.labels(tool="list_latest_news", status="success")._value.get()
    caplog.set_level(logging.INFO, logger="news_dashboard.mcp")

    async def call_next(_context: Any) -> ToolResult:
        return ToolResult(content=private_content)

    typed_context = cast("MiddlewareContext[CallToolRequestParams]", context)
    typed_next = cast("CallNext[CallToolRequestParams, ToolResult]", call_next)
    result = asyncio.run(_SafeToolTelemetryMiddleware().on_call_tool(typed_context, typed_next))

    assert result.is_error is False
    assert (
        mcp_tool_calls_total.labels(tool="list_latest_news", status="success")._value.get()
        == before + 1
    )
    events = [
        record.getMessage() for record in caplog.records if "event=tool" in record.getMessage()
    ]
    assert len(events) == 1
    assert "tool=list_latest_news status=success duration_ms=" in events[0]
    assert private_content not in caplog.text


def test_tool_telemetry_normalizes_unknown_tool_names(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from fastmcp.server.middleware import CallNext, MiddlewareContext
    from fastmcp.tools.base import ToolResult
    from mcp.types import CallToolRequestParams

    from news_dashboard.mcp.server import _SafeToolTelemetryMiddleware
    from news_dashboard.metrics import mcp_tool_calls_total

    private_tool_name = "private-user-controlled-tool-name"
    context = type(
        "Context",
        (),
        {"message": CallToolRequestParams(name=private_tool_name, arguments={})},
    )()
    before = mcp_tool_calls_total.labels(tool="unknown", status="success")._value.get()
    caplog.set_level(logging.INFO, logger="news_dashboard.mcp")

    async def call_next(_context: Any) -> ToolResult:
        return ToolResult(content="safe")

    typed_context = cast("MiddlewareContext[CallToolRequestParams]", context)
    typed_next = cast("CallNext[CallToolRequestParams, ToolResult]", call_next)
    asyncio.run(_SafeToolTelemetryMiddleware().on_call_tool(typed_context, typed_next))

    assert mcp_tool_calls_total.labels(tool="unknown", status="success")._value.get() == before + 1
    assert "tool=unknown" in caplog.text
    assert private_tool_name not in caplog.text


def test_rate_limit_short_circuit_records_one_metadata_only_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from fastmcp.server.middleware import CallNext, MiddlewareContext
    from fastmcp.server.middleware.rate_limiting import RateLimitError

    from news_dashboard.mcp import server
    from news_dashboard.metrics import mcp_rate_limits_total

    private_identity = "mcp-rate:private-bearer-derived-value"
    middleware = server._BoundedRateLimitingMiddleware()

    class ExhaustedBucket:
        async def consume(self) -> bool:
            return False

    monkeypatch.setattr(server, "_rate_limit_client_id", lambda _context: private_identity)
    monkeypatch.setattr(server, "_telemetry_token_id", lambda: 41)
    monkeypatch.setattr(middleware._buckets, "for_client", lambda _client_id: ExhaustedBucket())
    before = mcp_rate_limits_total.labels(status="limited")._value.get()
    caplog.set_level(logging.INFO, logger="news_dashboard.mcp")

    async def call_next(_context: Any) -> None:
        message = "rate-limited request must short-circuit"
        raise AssertionError(message)

    context = cast("MiddlewareContext[Any]", object())
    typed_next = cast("CallNext[Any, Any]", call_next)
    with pytest.raises(RateLimitError, match="Rate limit exceeded"):
        asyncio.run(middleware.on_request(context, typed_next))

    assert mcp_rate_limits_total.labels(status="limited")._value.get() == before + 1
    events = [
        record.getMessage()
        for record in caplog.records
        if "event=rate_limit" in record.getMessage()
    ]
    assert events == ["mcp event=rate_limit status=limited token_id=41"]
    assert private_identity not in caplog.text


def test_response_limit_records_one_metadata_only_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from fastmcp.server.middleware import CallNext, MiddlewareContext
    from fastmcp.tools.base import ToolResult
    from mcp.types import CallToolRequestParams

    from news_dashboard.mcp import server
    from news_dashboard.metrics import mcp_response_limits_total

    private_content = "private article body " * 100
    context = type(
        "Context",
        (),
        {"message": CallToolRequestParams(name="get_news_article", arguments={})},
    )()
    middleware = server._ObservedResponseLimitingMiddleware(max_size=200)
    monkeypatch.setattr(server, "_telemetry_token_id", lambda: 41)
    before = mcp_response_limits_total.labels(tool="get_news_article")._value.get()
    caplog.set_level(logging.INFO, logger="news_dashboard.mcp")

    async def call_next(_context: Any) -> ToolResult:
        return ToolResult(content=private_content)

    typed_context = cast("MiddlewareContext[CallToolRequestParams]", context)
    typed_next = cast("CallNext[CallToolRequestParams, ToolResult]", call_next)
    result = asyncio.run(middleware.on_call_tool(typed_context, typed_next))

    assert private_content not in str(result.content)
    assert mcp_response_limits_total.labels(tool="get_news_article")._value.get() == before + 1
    events = [
        record.getMessage()
        for record in caplog.records
        if "event=response_limit" in record.getMessage()
    ]
    assert events == ["mcp event=response_limit tool=get_news_article status=limited token_id=41"]
    assert private_content not in caplog.text
