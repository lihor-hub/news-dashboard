"""HTTP wiring for the A2A endpoint: public agent card plus the JSON-RPC endpoint.

The JSON-RPC surface is served by the official ``a2a-sdk`` dispatcher, but auth
runs here first — in the FastAPI endpoint, off the event loop, and before the
SDK parses the request body — so unauthenticated calls get a plain 401/403.
The SDK server stack is built lazily on first use because the feature is
disabled by default and the imports are expensive.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.requests import Request
from starlette.responses import Response

from news_dashboard.a2a import service
from news_dashboard.mcp.router import authenticate_bearer

public_a2a_router = APIRouter()

_DISABLED_DETAIL = "A2A server is not enabled on this instance"
_AUTH_SCOPE_KEY = "nd_a2a_auth"


@public_a2a_router.get("/.well-known/agent-card.json")
def get_agent_card() -> dict[str, Any]:
    if not service.a2a_enabled():
        raise HTTPException(status_code=403, detail=_DISABLED_DETAIL)
    return service.agent_card_dict()


def _authenticate(authorization: str | None) -> dict[str, Any]:
    return authenticate_bearer(
        authorization,
        enabled=service.a2a_enabled(),
        disabled_detail=_DISABLED_DETAIL,
        required_scope="ask",
    )


@lru_cache(maxsize=1)
def _dispatcher_endpoint() -> Callable[[Request], Awaitable[Response]]:
    from a2a.server.context import ServerCallContext
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.routes import DefaultServerCallContextBuilder, create_jsonrpc_routes
    from a2a.server.tasks import InMemoryTaskStore

    from news_dashboard.a2a.executor import AssistantAgentExecutor

    class ScopeAuthContextBuilder(DefaultServerCallContextBuilder):
        """Copy the identity established by the endpoint's auth into the call context."""

        def build(self, request: Request) -> ServerCallContext:
            context = super().build(request)
            auth = request.scope.get(_AUTH_SCOPE_KEY)
            if isinstance(auth, dict):
                context.state["user_id"] = int(auth["user_id"])
            return context

    handler = DefaultRequestHandler(
        agent_executor=AssistantAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=service.build_agent_card(),
    )
    routes = create_jsonrpc_routes(
        handler,
        rpc_url=service.RPC_PATH,
        context_builder=ScopeAuthContextBuilder(),
        enable_v0_3_compat=True,
    )
    endpoint: Callable[[Request], Awaitable[Response]] = routes[0].endpoint
    return endpoint


@public_a2a_router.post(service.RPC_PATH)
async def a2a_jsonrpc(request: Request) -> Response:
    auth = await asyncio.to_thread(_authenticate, request.headers.get("authorization"))
    request.scope[_AUTH_SCOPE_KEY] = auth
    return await _dispatcher_endpoint()(request)
