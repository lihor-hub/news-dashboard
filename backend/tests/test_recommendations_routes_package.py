"""Structural tests for the ``recommendations_routes`` feature-module package.

These guard the router layout (see the feature-module ADR) and ensure the
refactor stays behaviour-preserving: every ``/api/recommendations*`` route
remains mounted on the app with its original path.
"""

from __future__ import annotations

from news_dashboard.main import app


def test_recommendations_routes_package_modules_import() -> None:
    """router is importable from the recommendations_routes package."""
    from fastapi import APIRouter

    from news_dashboard.recommendations_routes.router import router

    assert isinstance(router, APIRouter)


def test_recommendations_routes_stay_mounted() -> None:
    """The refactor must not drop or rename any recommendations route.

    Routers are mounted lazily (as ``_IncludedRouter`` objects) rather than
    flattened into ``app.routes``, so assert against the resolved OpenAPI paths.
    """
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/recommendations/health",
        "/api/recommendations/recalculate",
        "/api/recommendations/recalculate-mine",
    }
    missing = expected - paths
    assert not missing, f"missing routes after refactor: {sorted(missing)}"
