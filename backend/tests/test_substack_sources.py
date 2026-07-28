"""Tests for guided Substack RSS source setup."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from news_dashboard.ingest.service import FeedFetchError
from news_dashboard.sources import service


@pytest.mark.parametrize(
    ("submitted_url", "expected_feed_url", "expected_name"),
    [
        (
            "https://pragmaticengineer.substack.com",
            "https://pragmaticengineer.substack.com/feed",
            "Pragmaticengineer",
        ),
        (
            "https://pragmaticengineer.substack.com/p/a-post?utm_source=post-email-title",
            "https://pragmaticengineer.substack.com/feed",
            "Pragmaticengineer",
        ),
        (
            "pragmaticengineer.substack.com/archive",
            "https://pragmaticengineer.substack.com/feed",
            "Pragmaticengineer",
        ),
    ],
)
def test_normalize_substack_feed_url_accepts_publication_and_post_links(
    submitted_url: str,
    expected_feed_url: str,
    expected_name: str,
) -> None:
    result = service.normalize_substack_feed_url(submitted_url)

    assert result.feed_url == expected_feed_url
    assert result.suggested_name == expected_name


@pytest.mark.parametrize(
    "submitted_url",
    [
        "",
        "https://example.com/feed",
        "https://substack.com/@writer",
        "ftp://writer.substack.com/feed",
        "https://evil.test/?next=writer.substack.com",
    ],
)
def test_normalize_substack_feed_url_rejects_non_publication_links(submitted_url: str) -> None:
    with pytest.raises(service.SubstackUrlError, match="Substack publication"):
        service.normalize_substack_feed_url(submitted_url)


def test_substack_preview_normalizes_post_link_and_returns_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_dashboard.auth import require_auth
    from news_dashboard.main import app
    from news_dashboard.sources import router as sources_router

    monkeypatch.setattr(
        sources_router,
        "preview_source_entries",
        lambda source: [
            {
                "title": "A useful post",
                "url": f"{source.url}/../p/useful",
                "date": None,
            }
        ],
    )
    app.dependency_overrides[require_auth] = lambda: {
        "id": 7,
        "username": "alice",
        "is_admin": False,
    }
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/sources/substack/preview",
                json={"url": "https://writer.substack.com/p/useful?utm_source=email"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 200
    assert response.json() == {
        "feed_url": "https://writer.substack.com/feed",
        "suggested_name": "Writer",
        "entry_count": 1,
        "items": [
            {
                "title": "A useful post",
                "url": "https://writer.substack.com/feed/../p/useful",
                "date": None,
            }
        ],
    }


def test_substack_preview_explains_invalid_publication_link() -> None:
    from news_dashboard.auth import require_auth
    from news_dashboard.main import app

    app.dependency_overrides[require_auth] = lambda: {"id": 7, "username": "alice"}
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/sources/substack/preview",
                json={"url": "https://example.com/not-substack"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 400
    assert response.json()["detail"] == "Enter a Substack publication or post link."


def test_substack_preview_explains_unreachable_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_dashboard.auth import require_auth
    from news_dashboard.main import app
    from news_dashboard.sources import router as sources_router

    def fail_preview(_source: object) -> list[dict[str, object]]:
        message = "The publication feed could not be reached."
        raise FeedFetchError(message)

    monkeypatch.setattr(sources_router, "preview_source_entries", fail_preview)
    app.dependency_overrides[require_auth] = lambda: {"id": 7, "username": "alice"}
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/sources/substack/preview",
                json={"url": "https://writer.substack.com"},
            )
    finally:
        app.dependency_overrides.pop(require_auth, None)

    assert response.status_code == 422
    assert response.json()["detail"] == "The publication feed could not be reached."
