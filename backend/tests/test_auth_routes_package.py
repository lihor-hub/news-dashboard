"""Structural tests for the ``auth_routes`` feature-module package.

These guard the router layout (see the feature-module ADR) and ensure the
refactor stays behaviour-preserving: every ``/auth/*`` and ``/api/auth/*``
route remains mounted on the app with its original path. Unlike other
feature-module domains, business logic (session tokens, Keycloak exchange,
OTP persistence) stays in the existing ``news_dashboard.auth`` module rather
than moving into a ``service.py``, since that module is imported across the
rest of the codebase.
"""

from __future__ import annotations

from news_dashboard.main import app


def test_auth_routes_package_modules_import() -> None:
    """public_router/router are importable from the auth_routes package."""
    from fastapi import APIRouter

    from news_dashboard.auth_routes import models
    from news_dashboard.auth_routes.router import public_router, router

    assert isinstance(public_router, APIRouter)
    assert isinstance(router, APIRouter)
    assert hasattr(models, "LoginRequest")
    assert hasattr(models, "OTPRequestPayload")
    assert hasattr(models, "OTPLoginPayload")


def test_auth_routes_stay_mounted() -> None:
    """The refactor must not drop or rename any login/OTP/Keycloak/me route.

    Routers are mounted lazily (as ``_IncludedRouter`` objects) rather than
    flattened into ``app.routes``, so assert against the resolved OpenAPI paths.
    """
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/auth/config",
        "/api/auth/metadata",
        "/auth/login",
        "/auth/register",
        "/auth/callback",
        "/auth/logout",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/otp/request",
        "/api/auth/otp/login",
        "/api/auth/me",
    }
    missing = expected - paths
    assert not missing, f"missing routes after refactor: {sorted(missing)}"
