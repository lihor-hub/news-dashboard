from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
MCP_DOCS = (
    ROOT / "website/docs/configuration/mcp-server.md",
    ROOT / "website/docs/api/integrations.md",
    ROOT / "website/docs/api/authentication.md",
    ROOT / "website/docs/api/index.md",
)
TOOLS = (
    "list_latest_news",
    "list_news_sources",
    "search_news",
    "ask_news",
    "get_news_article",
    "list_briefings",
    "get_briefing",
)


def test_published_mcp_docs_cover_operational_and_client_contracts() -> None:
    combined = "\n".join(path.read_text() for path in MCP_DOCS)

    for tool in TOOLS:
        assert tool in combined
    for contract in (
        "MCP_SERVER_ENABLED=false",
        "MCP_ALLOWED_HOSTS",
        "MCP_ALLOWED_ORIGINS",
        "/api/mcp/health",
        "/metrics",
        "https://news.example.com/mcp/",
        "NEWS_DASHBOARD_MCP_URL",
        "NEWS_DASHBOARD_MCP_TOKEN",
        "Langfuse",
        "Keycloak",
    ):
        assert contract in combined


def test_published_mcp_docs_have_no_legacy_or_stale_availability_claims() -> None:
    combined = "\n".join(path.read_text().lower() for path in MCP_DOCS)

    for stale in (
        "/api/mcp/tools",
        "/api/mcp/rpc",
        "mcp question answering is planned",
        "tokens are read-only and disabled by default",
    ):
        assert stale not in combined

    assert "export MCP_TOKEN='ndmcp_" not in combined
    assert "read -rsp" in combined
