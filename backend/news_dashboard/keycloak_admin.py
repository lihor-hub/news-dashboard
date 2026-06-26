"""Keycloak Admin REST API helpers for provisioning users from the admin page.

When the dashboard runs behind Keycloak, local username/password login is
disabled, so a user created only in the local ``users`` table can never log in.
To actually onboard someone, the account must exist in Keycloak. This module
uses a service-account (client-credentials) token to call the Keycloak Admin
REST API and create the user, returning a one-time temporary password.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException

from news_dashboard.auth import keycloak_config

logger = logging.getLogger(__name__)

_TIMEOUT = 10.0


async def _admin_token(client: httpx.AsyncClient) -> str:
    config = keycloak_config()
    if not config.admin_client_secret:
        raise HTTPException(
            status_code=500,
            detail=(
                "Keycloak admin provisioning is not configured. Set "
                "KEYCLOAK_ADMIN_CLIENT_SECRET (and optionally KEYCLOAK_ADMIN_CLIENT_ID) "
                "for a client with the realm-management manage-users role."
            ),
        )
    token_url = f"{config.internal_realm_url}/protocol/openid-connect/token"
    response = await client.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": config.admin_client_id,
            "client_secret": config.admin_client_secret,
        },
        headers={"Accept": "application/json"},
    )
    if response.status_code >= 400:
        logger.error("Keycloak admin token request failed: %s", response.status_code)
        raise HTTPException(status_code=502, detail="Keycloak admin authentication failed")
    token = response.json().get("access_token")
    if not token:
        raise HTTPException(
            status_code=502,
            detail="Keycloak admin token response had no access token",
        )
    return str(token)


def _user_id_from_location(location: str) -> str | None:
    return location.rstrip("/").rsplit("/", 1)[-1] if location else None


async def create_keycloak_user(
    username: str,
    password: str,
    *,
    email: str | None = None,
    temporary: bool = True,
) -> dict[str, Any]:
    """Create a realm user with a (temporary) password via the Admin REST API.

    Returns the new Keycloak user id, username, and email. The plaintext
    ``password`` itself is supplied by the caller and returned to the admin once.
    """
    config = keycloak_config()
    if not config.enabled:
        raise HTTPException(status_code=400, detail="Keycloak authentication is disabled")
    users_url = f"{config.internal_server_url}/admin/realms/{config.realm}/users"
    body: dict[str, Any] = {
        "username": username,
        "enabled": True,
        "credentials": [{"type": "password", "value": password, "temporary": temporary}],
    }
    if email:
        body["email"] = email
        body["emailVerified"] = False

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        token = await _admin_token(client)
        response = await client.post(
            users_url,
            json=body,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )

    if response.status_code == 409:
        raise HTTPException(status_code=409, detail="A user with that username already exists")
    if response.status_code >= 400:
        logger.error("Keycloak user creation failed: %s %s", response.status_code, response.text)
        raise HTTPException(status_code=502, detail="Keycloak user creation failed")

    return {
        "id": _user_id_from_location(response.headers.get("Location", "")),
        "username": username,
        "email": email,
        "temporary": temporary,
    }
