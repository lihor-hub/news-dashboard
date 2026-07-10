"""Business logic for analytics and user administration."""

from __future__ import annotations

import secrets
from typing import Any


def admin_analytics(*, days: int) -> dict[str, Any]:
    from news_dashboard.analytics import admin_analytics as admin_analytics_impl

    return admin_analytics_impl(days=days)


def fetch_metrics(*, days: int) -> dict[str, Any]:
    from news_dashboard.ai_client import fetch_metrics as fetch_metrics_impl

    return fetch_metrics_impl(days=days)


def admin_quality_summary(*, days: int) -> dict[str, Any]:
    from news_dashboard.ai_evals import admin_quality_summary as quality_impl

    return quality_impl(days=days)


def admin_run_summary(*, limit: int) -> dict[str, Any]:
    from news_dashboard.learn_from_link.agent_runs import admin_run_summary as summary_impl

    return summary_impl(limit=limit)


def create_user(
    username: str, password: str, *, email: str | None, is_admin: bool
) -> dict[str, Any]:
    from news_dashboard.auth import create_user as create_user_impl

    return create_user_impl(username, password, email=email, is_admin=is_admin)


def list_users() -> list[dict[str, Any]]:
    from news_dashboard.auth import list_users as list_users_impl

    return list_users_impl()


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    from news_dashboard.auth import get_user_by_id as get_user_impl

    return get_user_impl(user_id)


def update_password(user_id: int, password: str) -> bool:
    from news_dashboard.auth import update_password as update_password_impl

    return update_password_impl(user_id, password)


def delete_user(user_id: int) -> bool:
    from news_dashboard.auth import delete_user as delete_user_impl

    return delete_user_impl(user_id)


def keycloak_enabled() -> bool:
    from news_dashboard.auth import keycloak_config

    return keycloak_config().enabled


async def generate_user(
    username: str,
    *,
    email: str | None,
    is_admin: bool,
) -> dict[str, Any]:
    """Create an account with a generated password for the active auth provider."""
    password = secrets.token_urlsafe(12)
    if keycloak_enabled():
        from news_dashboard.keycloak_admin import create_keycloak_user

        result = await create_keycloak_user(username, password, email=email)
        return {**result, "password": password, "provider": "keycloak"}
    user = create_user(username, password, email=email, is_admin=is_admin)
    return {**user, "password": password, "provider": "password", "temporary": False}


__all__ = [
    "admin_analytics",
    "admin_quality_summary",
    "admin_run_summary",
    "create_user",
    "delete_user",
    "fetch_metrics",
    "generate_user",
    "get_user_by_id",
    "keycloak_enabled",
    "list_users",
    "update_password",
]
