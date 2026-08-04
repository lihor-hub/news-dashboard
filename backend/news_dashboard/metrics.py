"""Optional Prometheus metrics.

Gated by the ``METRICS_ENABLED`` env var (off by default). When disabled,
`/metrics` is not served. Labels never carry article content, URLs, emails,
or other PII — only coarse, fixed identifiers like job names, HTTP methods,
route templates, and outcome status.
"""

from __future__ import annotations

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

registry = CollectorRegistry()

http_requests_total = Counter(
    "news_dashboard_http_requests_total",
    "Total HTTP requests handled.",
    ["method", "path", "status"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "news_dashboard_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
    registry=registry,
)

ingest_runs_total = Counter(
    "news_dashboard_ingest_runs_total",
    "Scheduled/manual ingest runs, labeled by outcome.",
    ["status"],
    registry=registry,
)

ingest_articles_new_total = Counter(
    "news_dashboard_ingest_articles_new_total",
    "New articles discovered across all ingest runs.",
    registry=registry,
)

scheduler_job_runs_total = Counter(
    "news_dashboard_scheduler_job_runs_total",
    "Background scheduler job runs, labeled by job name and outcome.",
    ["job_name", "status"],
    registry=registry,
)

source_health_checks_total = Counter(
    "news_dashboard_source_health_checks_total",
    "Per-source-fetch ingest outcomes, labeled by outcome only (no source"
    " identity, since source names/slugs may be user-defined for private feeds).",
    ["status"],
    registry=registry,
)

mcp_auth_attempts_total = Counter(
    "news_dashboard_mcp_auth_attempts_total",
    "MCP authentication attempts by bounded outcome.",
    ["status"],
    registry=registry,
)

mcp_tool_calls_total = Counter(
    "news_dashboard_mcp_tool_calls_total",
    "MCP tool calls by catalog tool and bounded outcome.",
    ["tool", "status"],
    registry=registry,
)

mcp_tool_duration_seconds = Histogram(
    "news_dashboard_mcp_tool_duration_seconds",
    "MCP tool execution duration by catalog tool and bounded outcome.",
    ["tool", "status"],
    registry=registry,
)

mcp_rate_limits_total = Counter(
    "news_dashboard_mcp_rate_limits_total",
    "MCP requests rejected by the bounded rate limiter.",
    ["status"],
    registry=registry,
)

mcp_response_limits_total = Counter(
    "news_dashboard_mcp_response_limits_total",
    "MCP tool responses truncated at the transport response limit.",
    ["tool"],
    registry=registry,
)


def metrics_enabled() -> bool:
    return os.getenv("METRICS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def render_metrics() -> bytes:
    return generate_latest(registry)


__all__ = [
    "CONTENT_TYPE_LATEST",
    "http_request_duration_seconds",
    "http_requests_total",
    "ingest_articles_new_total",
    "ingest_runs_total",
    "mcp_auth_attempts_total",
    "mcp_rate_limits_total",
    "mcp_response_limits_total",
    "mcp_tool_calls_total",
    "mcp_tool_duration_seconds",
    "metrics_enabled",
    "render_metrics",
    "scheduler_job_runs_total",
    "source_health_checks_total",
]
