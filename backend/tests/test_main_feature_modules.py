"""Whole-app guardrails for the feature-module migration tracked by issue #826."""

from __future__ import annotations

import ast
from pathlib import Path

from news_dashboard import main

EXPECTED_METHOD_PATHS = {
    ("GET", "/api/admin/ai/metrics"),
    ("GET", "/api/admin/ai/quality"),
    ("GET", "/api/admin/analytics"),
    ("GET", "/api/admin/learning-agent/runs"),
    ("GET", "/api/admin/users"),
    ("POST", "/api/admin/users"),
    ("POST", "/api/admin/users/generate"),
    ("DELETE", "/api/admin/users/{user_id}"),
    ("GET", "/api/admin/users/{user_id}"),
    ("PATCH", "/api/admin/users/{user_id}/password"),
    ("POST", "/api/agent/actions/plan"),
    ("GET", "/api/agent/actions/{run_id}"),
    ("POST", "/api/agent/actions/{run_id}/approve"),
    ("POST", "/api/agent/actions/{run_id}/cancel"),
    ("DELETE", "/api/ai-feedback"),
    ("GET", "/api/ai-feedback"),
    ("POST", "/api/ai-feedback"),
    ("GET", "/api/ai-stats/embedding-map"),
    ("GET", "/api/ai-stats/knowledge-graph"),
    ("GET", "/api/ai-stats/word-cloud"),
    ("GET", "/api/articles"),
    ("POST", "/api/articles/save-url"),
    ("GET", "/api/articles/topic-map"),
    ("GET", "/api/articles/{article_id}"),
    ("POST", "/api/articles/{article_id}/audio"),
    ("GET", "/api/articles/{article_id}/body"),
    ("POST", "/api/articles/{article_id}/body"),
    ("GET", "/api/articles/{article_id}/highlights"),
    ("POST", "/api/articles/{article_id}/highlights"),
    ("DELETE", "/api/articles/{article_id}/highlights/{highlight_id}"),
    ("GET", "/api/articles/{article_id}/insights"),
    ("PATCH", "/api/articles/{article_id}/later"),
    ("GET", "/api/articles/{article_id}/perspectives"),
    ("GET", "/api/articles/{article_id}/read"),
    ("POST", "/api/articles/{article_id}/share"),
    ("PATCH", "/api/articles/{article_id}/star"),
    ("PATCH", "/api/articles/{article_id}/state"),
    ("PATCH", "/api/articles/{article_id}/status"),
    ("GET", "/api/articles/{article_id}/tags"),
    ("POST", "/api/articles/{article_id}/tags"),
    ("DELETE", "/api/articles/{article_id}/tags/{tag_id}"),
    ("POST", "/api/ask"),
    ("GET", "/api/auth/config"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/logout"),
    ("GET", "/api/auth/me"),
    ("GET", "/api/auth/metadata"),
    ("POST", "/api/auth/otp/login"),
    ("POST", "/api/auth/otp/request"),
    ("GET", "/api/briefings"),
    ("POST", "/api/briefings"),
    ("GET", "/api/briefings/latest"),
    ("GET", "/api/briefings/podcast-feed-token"),
    ("POST", "/api/briefings/podcast-feed-token/regenerate"),
    ("GET", "/api/briefings/podcast.rss"),
    ("GET", "/api/briefings/{briefing_id}"),
    ("POST", "/api/briefings/{briefing_id}/chat"),
    ("GET", "/api/briefings/{briefing_id}/podcast"),
    ("POST", "/api/briefings/{briefing_id}/podcast"),
    ("GET", "/api/briefings/{briefing_id}/podcast-audio"),
    ("GET", "/api/changelog"),
    ("GET", "/api/config"),
    ("POST", "/api/events"),
    ("POST", "/api/feedback"),
    ("GET", "/api/goals"),
    ("POST", "/api/goals"),
    ("DELETE", "/api/goals/{goal_id}"),
    ("POST", "/api/greader/accounts/ClientLogin"),
    ("POST", "/api/greader/reader/api/0/edit-tag"),
    ("GET", "/api/greader/reader/api/0/stream/contents/{stream_id}"),
    ("POST", "/api/greader/reader/api/0/stream/items/contents"),
    ("GET", "/api/greader/reader/api/0/stream/items/ids"),
    ("GET", "/api/greader/reader/api/0/subscription/list"),
    ("GET", "/api/greader/reader/api/0/token"),
    ("GET", "/api/greader/reader/api/0/user-info"),
    ("GET", "/api/health"),
    ("GET", "/api/health/details"),
    ("POST", "/api/ingest"),
    ("GET", "/api/ingest/runs"),
    ("GET", "/api/ingest/runs/{run_id}"),
    ("GET", "/api/ingest/stream"),
    ("GET", "/api/learn/lessons"),
    ("POST", "/api/learn/lessons"),
    ("GET", "/api/learn/lessons/{lesson_id}"),
    ("GET", "/api/learn/lessons/{lesson_id}/generations"),
    ("GET", "/api/learn/lessons/{lesson_id}/podcast"),
    ("POST", "/api/learn/lessons/{lesson_id}/podcast"),
    ("POST", "/api/learn/lessons/{lesson_id}/questions"),
    ("POST", "/api/learn/lessons/{lesson_id}/regenerate"),
    ("POST", "/api/learn/lessons/{lesson_id}/relevance/feedback"),
    ("POST", "/api/learn/lessons/{lesson_id}/slides"),
    ("GET", "/api/learn/suggestions"),
    ("POST", "/api/learn/suggestions/dismiss"),
    ("GET", "/api/lesson-recaps"),
    ("POST", "/api/lesson-recaps/generate"),
    ("GET", "/api/lesson-recaps/latest"),
    ("GET", "/api/lesson-recaps/{recap_id}/podcast"),
    ("POST", "/api/lesson-recaps/{recap_id}/podcast"),
    ("GET", "/api/live"),
    ("POST", "/api/mcp/rpc"),
    ("GET", "/api/mcp/tools"),
    ("DELETE", "/api/notifications/subscribe"),
    ("POST", "/api/notifications/subscribe"),
    ("GET", "/api/onboarding/interests"),
    ("POST", "/api/onboarding/interests"),
    ("POST", "/api/onboarding/profile"),
    ("POST", "/api/onboarding/recommendations"),
    ("GET", "/api/onboarding/source-recommendations"),
    ("GET", "/api/onboarding/status"),
    ("GET", "/api/personalization/nudges"),
    ("POST", "/api/personalization/nudges/apply"),
    ("POST", "/api/personalization/nudges/dismiss"),
    ("GET", "/api/quizzes"),
    ("GET", "/api/quizzes/candidates"),
    ("POST", "/api/quizzes/generate"),
    ("GET", "/api/quizzes/latest"),
    ("POST", "/api/quizzes/{quiz_id}/submit"),
    ("GET", "/api/reading-list"),
    ("POST", "/api/reading-list"),
    ("POST", "/api/reading-list/import"),
    ("POST", "/api/reading-list/reorder"),
    ("DELETE", "/api/reading-list/{item_id}"),
    ("PATCH", "/api/reading-list/{item_id}"),
    ("GET", "/api/ready"),
    ("GET", "/api/recaps"),
    ("GET", "/api/recaps/latest"),
    ("GET", "/api/recommendations/health"),
    ("POST", "/api/recommendations/recalculate"),
    ("POST", "/api/recommendations/recalculate-mine"),
    ("POST", "/api/scheduler/interval"),
    ("GET", "/api/scheduler/job-runs"),
    ("POST", "/api/scheduler/pause"),
    ("POST", "/api/scheduler/resume"),
    ("GET", "/api/scheduler/status"),
    ("GET", "/api/search"),
    ("GET", "/api/search/saved"),
    ("POST", "/api/search/saved"),
    ("DELETE", "/api/search/saved/{search_id}"),
    ("PATCH", "/api/search/saved/{search_id}"),
    ("GET", "/api/settings/analytics"),
    ("PUT", "/api/settings/analytics"),
    ("GET", "/api/settings/notifications"),
    ("PUT", "/api/settings/notifications"),
    ("GET", "/api/shares"),
    ("GET", "/api/shares/sent"),
    ("GET", "/api/shares/unread_count"),
    ("GET", "/api/shares/{share_id}"),
    ("GET", "/api/shares/{share_id}/annotations"),
    ("POST", "/api/shares/{share_id}/annotations"),
    ("GET", "/api/shares/{share_id}/article"),
    ("POST", "/api/shares/{share_id}/article/body"),
    ("GET", "/api/shares/{share_id}/messages"),
    ("POST", "/api/shares/{share_id}/messages"),
    ("POST", "/api/shares/{share_id}/read"),
    ("POST", "/api/shares/{share_id}/revoke"),
    ("GET", "/api/sources"),
    ("POST", "/api/sources"),
    ("POST", "/api/sources/cleanup"),
    ("GET", "/api/sources/cleanup-suggestions"),
    ("GET", "/api/sources/export.opml"),
    ("GET", "/api/sources/health"),
    ("POST", "/api/sources/import"),
    ("POST", "/api/sources/preview"),
    ("DELETE", "/api/sources/{slug}"),
    ("PATCH", "/api/sources/{slug}/enabled"),
    ("GET", "/api/stats/article-counts"),
    ("GET", "/api/stats/articles-over-time"),
    ("GET", "/api/stats/category-mix"),
    ("GET", "/api/stats/ingested-vs-handled"),
    ("GET", "/api/stats/overview"),
    ("GET", "/api/stats/source-quality"),
    ("GET", "/api/stats/sources-volume"),
    ("GET", "/api/stats/triage-metrics"),
    ("GET", "/api/summary"),
    ("GET", "/api/tags"),
    ("POST", "/api/tags"),
    ("DELETE", "/api/tags/{tag_id}"),
    ("PATCH", "/api/tags/{tag_id}"),
    ("GET", "/api/tags/{tag_id}/articles"),
    ("GET", "/api/users"),
    ("DELETE", "/api/users/me"),
    ("GET", "/api/users/me/achievements"),
    ("GET", "/api/users/me/ai-memories"),
    ("POST", "/api/users/me/ai-memories"),
    ("POST", "/api/users/me/ai-memories/learn-from-reading"),
    ("DELETE", "/api/users/me/ai-memories/{memory_id}"),
    ("PATCH", "/api/users/me/ai-memories/{memory_id}"),
    ("GET", "/api/users/me/export"),
    ("GET", "/api/users/me/greader-tokens"),
    ("POST", "/api/users/me/greader-tokens"),
    ("DELETE", "/api/users/me/greader-tokens/{token_id}"),
    ("POST", "/api/users/me/import"),
    ("GET", "/api/users/me/mcp-tokens"),
    ("POST", "/api/users/me/mcp-tokens"),
    ("DELETE", "/api/users/me/mcp-tokens/{token_id}"),
    ("GET", "/api/users/me/reading-dna"),
    ("GET", "/api/users/me/recommendation-preferences"),
    ("PATCH", "/api/users/me/recommendation-preferences"),
    ("GET", "/api/users/me/streak"),
    ("GET", "/api/version"),
    ("GET", "/api/watchlists"),
    ("POST", "/api/watchlists"),
    ("GET", "/api/watchlists/nudges"),
    ("POST", "/api/watchlists/preview"),
    ("DELETE", "/api/watchlists/{watchlist_id}"),
    ("PATCH", "/api/watchlists/{watchlist_id}"),
    ("GET", "/auth/callback"),
    ("GET", "/auth/login"),
    ("GET", "/auth/logout"),
    ("GET", "/auth/register"),
    ("GET", "/metrics"),
}


def _is_route_decorator(decorator: ast.expr) -> bool:
    """Return whether *decorator* is an HTTP method call on a FastAPI router."""
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in {"delete", "get", "patch", "post", "put"}
    )


def test_main_contains_app_assembly_not_route_handlers() -> None:
    """The application entrypoint must assemble routers, not own HTTP domains."""
    source = Path(main.__file__).read_text()
    tree = ast.parse(source)
    decorated_routes = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_route_decorator(decorator) for decorator in node.decorator_list)
    ]
    request_models = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "BaseModel" for base in node.bases)
    ]

    assert decorated_routes == []
    assert request_models == []


def test_feature_module_migration_preserves_openapi_routes() -> None:
    """No method/path pair may disappear or change during the extraction."""
    methods = {"DELETE", "GET", "PATCH", "POST", "PUT"}
    actual = {
        (method.upper(), path)
        for path, operations in main.app.openapi()["paths"].items()
        for method in operations
        if method.upper() in methods
    }

    assert actual == EXPECTED_METHOD_PATHS
