"""Structural tests for the ``onboarding`` feature-module package.

These guard the router/service/models layout (see the feature-module ADR) and
ensure the refactor stays behaviour-preserving: every ``/api/onboarding*``
route remains mounted on the app with its original path.
"""

from __future__ import annotations

from news_dashboard.main import app


def test_onboarding_package_modules_import() -> None:
    """router/service/models are importable from the onboarding package."""
    from fastapi import APIRouter

    from news_dashboard.onboarding import models, service
    from news_dashboard.onboarding.router import router

    assert isinstance(router, APIRouter)
    for name in (
        "INTEREST_GROUPS",
        "interest_options",
        "source_recommendations",
        "frontend_recommendations",
        "get_status",
        "get_interests",
        "save_profile",
        "save_interests",
        "UnknownGlobalSourcesError",
    ):
        assert hasattr(service, name), name
    assert hasattr(models, "OnboardingInterestsRequest")
    assert hasattr(models, "OnboardingRecommendationsRequest")
    assert hasattr(models, "OnboardingProfileRequest")


def test_onboarding_routes_stay_mounted() -> None:
    """The refactor must not drop or rename any onboarding route.

    Routers are mounted lazily (as ``_IncludedRouter`` objects) rather than
    flattened into ``app.routes``, so assert against the resolved OpenAPI paths.
    """
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/onboarding/status",
        "/api/onboarding/interests",
        "/api/onboarding/recommendations",
        "/api/onboarding/profile",
        "/api/onboarding/source-recommendations",
    }
    missing = expected - paths
    assert not missing, f"missing routes after refactor: {sorted(missing)}"
