from __future__ import annotations

import hashlib
import hmac
import secrets

from anyio import to_thread
from fastmcp.server.auth import AccessToken, TokenVerifier

from news_dashboard.mcp import service

_RATE_LIMIT_KEY = secrets.token_bytes(32)


def _rate_limit_identity(token: str) -> str:
    digest = hmac.new(_RATE_LIMIT_KEY, token.encode(), hashlib.sha256).hexdigest()
    return f"mcp-rate:{digest}"


class NewsDashboardTokenVerifier(TokenVerifier):
    """Adapt News Dashboard's stored MCP tokens for FastMCP authentication."""

    async def verify_token(self, token: str) -> AccessToken | None:
        authenticated = await to_thread.run_sync(service.authenticate_token, token)
        if authenticated is None:
            return None
        token_id = int(authenticated["token_id"])
        user_id = int(authenticated["user_id"])
        scopes = sorted(str(scope) for scope in authenticated["scopes"])
        return AccessToken(
            token=token,
            client_id=f"mcp-token:{token_id}",
            subject=str(user_id),
            scopes=scopes,
            claims={
                "user_id": user_id,
                "token_id": token_id,
                "rate_limit_id": _rate_limit_identity(token),
            },
        )
