"""Business logic for the opt-in A2A (Agent2Agent) protocol endpoint."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from news_dashboard.mcp.models import MAX_QUERY_LENGTH
from news_dashboard.version import read_app_version

if TYPE_CHECKING:
    from a2a.types import AgentCard

RPC_PATH = "/api/a2a"
SKILL_ID = "ask_news"


def a2a_enabled() -> bool:
    """Whether the opt-in A2A server is enabled. Disabled unless explicitly configured."""
    return (os.getenv("A2A_SERVER_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


def public_base_url() -> str:
    """Public base URL of this deployment, used in the published agent card.

    Follows the documented precedence: APP_BASE_URL, then NEWS_DASHBOARD_BASE_URL,
    then NEWS_DASHBOARD_URL.
    """
    for var in ("APP_BASE_URL", "NEWS_DASHBOARD_BASE_URL", "NEWS_DASHBOARD_URL"):
        value = (os.getenv(var) or "").strip()
        if value:
            return value.rstrip("/")
    return "http://localhost:8080"


def answer_question(query: str, *, user_id: int) -> dict[str, Any]:
    """Answer *query* via retrieval over the corpus visible to *user_id*.

    Raises ValueError for empty or oversized queries (bounds match the MCP limits).
    """
    text = (query or "").strip()
    if not text:
        message = "message must contain a non-empty text part"
        raise ValueError(message)
    if len(text) > MAX_QUERY_LENGTH:
        message = f"query must be at most {MAX_QUERY_LENGTH} characters"
        raise ValueError(message)
    from news_dashboard.assistant import service as assistant_service

    return assistant_service.ask(text, include_all=False, user_id=user_id)


def build_agent_card() -> AgentCard:
    """Build the A2A agent card advertising the read-only corpus Q&A skill.

    The endpoint serves protocol 1.0 with 0.3 backward compatibility, so both
    interface versions are advertised at the same URL.
    """
    from a2a.types import (
        AgentCapabilities,
        AgentCard,
        AgentInterface,
        AgentSkill,
        HTTPAuthSecurityScheme,
        SecurityScheme,
    )

    rpc_url = f"{public_base_url()}{RPC_PATH}"
    return AgentCard(
        name="News Dashboard Assistant",
        description=(
            "Answers questions over the token owner's news corpus using retrieval "
            "over their Starred + Done articles. Read-only: it cannot modify any "
            "dashboard state."
        ),
        version=read_app_version(),
        supported_interfaces=[
            AgentInterface(url=rpc_url, protocol_binding="JSONRPC", protocol_version="1.0"),
            AgentInterface(url=rpc_url, protocol_binding="JSONRPC", protocol_version="0.3"),
        ],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain", "application/json"],
        security_schemes={
            "bearer": SecurityScheme(
                http_auth_security_scheme=HTTPAuthSecurityScheme(
                    scheme="bearer",
                    description=(
                        "News Dashboard MCP/A2A token created under "
                        "Settings → AI clients (requires the 'ask' scope)."
                    ),
                )
            )
        },
        skills=[
            AgentSkill(
                id=SKILL_ID,
                name="Ask over news corpus",
                description=(
                    "Ask a question answered via retrieval over the token owner's "
                    "Starred + Done articles."
                ),
                tags=["news", "rag", "question-answering", "read-only"],
                examples=["What happened in AI infrastructure this week?"],
            )
        ],
    )


@lru_cache(maxsize=4)
def _agent_card_dict_for(base_url: str) -> dict[str, Any]:
    del base_url  # cache key only; build_agent_card re-reads the env itself
    from a2a.server.request_handlers.response_helpers import agent_card_to_dict

    return agent_card_to_dict(build_agent_card())


def agent_card_dict() -> dict[str, Any]:
    """Serialized agent card, cached per base URL (the only per-request variance)."""
    return _agent_card_dict_for(public_base_url())
