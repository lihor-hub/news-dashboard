"""Structural tests for the ``quizzes`` feature-module package.

These guard the router/service/models layout (see the feature-module ADR) and
ensure the refactor stays behaviour-preserving: every ``/api/quizzes*`` and
``/api/goals*`` route remains mounted on the app with its original path.
"""

from __future__ import annotations

from news_dashboard.main import app


def test_quizzes_package_modules_import() -> None:
    """router/service/models are importable from the quizzes package."""
    from fastapi import APIRouter

    from news_dashboard.quizzes import models, service
    from news_dashboard.quizzes.router import router

    assert isinstance(router, APIRouter)
    # Service keeps the public surface previously exposed by quiz.py.
    for name in (
        "create_goal",
        "list_goals",
        "delete_goal",
        "goal_alignment_adjustment",
        "get_quiz_candidate_articles",
        "generate_weekly_quiz",
        "get_latest_quiz",
        "list_quizzes",
        "submit_quiz",
    ):
        assert hasattr(service, name), name
    assert hasattr(models, "GoalCreateRequest")
    assert hasattr(models, "QuizSubmitRequest")


def test_quiz_and_goal_routes_stay_mounted() -> None:
    """The refactor must not drop or rename any quiz/goal route.

    Routers are mounted lazily (as ``_IncludedRouter`` objects) rather than
    flattened into ``app.routes``, so assert against the resolved OpenAPI paths.
    """
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/goals",
        "/api/goals/{goal_id}",
        "/api/quizzes",
        "/api/quizzes/candidates",
        "/api/quizzes/latest",
        "/api/quizzes/generate",
        "/api/quizzes/{quiz_id}/submit",
    }
    missing = expected - paths
    assert not missing, f"missing routes after refactor: {sorted(missing)}"


def test_legacy_quiz_module_is_gone() -> None:
    """quiz.py is fully replaced by the quizzes package."""
    import importlib.util

    assert importlib.util.find_spec("news_dashboard.quiz") is None
