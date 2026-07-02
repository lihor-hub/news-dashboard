from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from news_dashboard.db import connect
from news_dashboard.ingest import _ingest_source
from news_dashboard.sources import SourceDefinition


def _source(kind: str, url: str = "https://example.com/feed.xml") -> SourceDefinition:
    return SourceDefinition(
        slug=f"test-{kind}",
        name=f"Test {kind}",
        url=url,
        category="media",
        kind=kind,
        priority=50,
    )


def test_podcast_feed_ingests_enclosure_with_ai_summary(pg_clean: str) -> None:
    source = _source("podcast_feed")
    entries = [
        {
            "url": "https://example.com/episodes/1",
            "title": "Episode 1",
            "description": "Episode description",
            "date": "2026-07-01T12:00:00+00:00",
            "media_url": "https://cdn.example.com/episodes/1.mp3",
            "transcript": "The full podcast transcript explains the launch.",
        }
    ]
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="A concise media summary."))]
    )

    with connect(pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            (source.slug, source.name, source.url, source.category, source.kind, source.priority),
        )

    with (
        patch("news_dashboard.ingest._parse_media_feed_url", return_value=entries),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("test-key", None)),
        patch("news_dashboard.ai_client.get_chat_client", return_value=object()),
        patch("news_dashboard.ai_client.chat_create", return_value=response),
    ):
        outcome = _ingest_source(source, pg_clean)

    assert outcome.articles_new == 1
    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT url, summary, reason, tags, kind FROM articles WHERE source_slug=%s",
            (source.slug,),
        ).fetchone()
    assert row["url"] == "https://example.com/episodes/1"
    assert (
        row["summary"]
        == "A concise media summary.\n\nSource media: https://cdn.example.com/episodes/1.mp3"
    )
    assert row["reason"] == "Media episode from Test podcast_feed."
    assert row["tags"] == "media,podcast"
    assert row["kind"] == "podcast_feed"


def test_youtube_channel_ingests_caption_summary(pg_clean: str) -> None:
    source = _source(
        "youtube_channel",
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC123",
    )
    entries = [
        {
            "url": "https://www.youtube.com/watch?v=abc123",
            "title": "Video 1",
            "description": "Video description",
            "date": None,
            "media_url": "https://www.youtube.com/watch?v=abc123",
            "transcript": "Caption text from the video.",
        }
    ]
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="A summarized video."))]
    )

    with connect(pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            (source.slug, source.name, source.url, source.category, source.kind, source.priority),
        )

    with (
        patch("news_dashboard.ingest._parse_media_feed_url", return_value=entries),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("test-key", None)),
        patch("news_dashboard.ai_client.get_chat_client", return_value=object()),
        patch("news_dashboard.ai_client.chat_create", return_value=response),
    ):
        outcome = _ingest_source(source, pg_clean)

    assert outcome.articles_new == 1
    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT summary, tags FROM articles WHERE source_slug=%s",
            (source.slug,),
        ).fetchone()
    assert (
        row["summary"]
        == "A summarized video.\n\nSource media: https://www.youtube.com/watch?v=abc123"
    )
    assert row["tags"] == "media,video"


def test_media_ingest_falls_back_when_ai_disabled(pg_clean: str) -> None:
    source = _source("podcast_feed")
    entries = [
        {
            "url": "https://example.com/episodes/2",
            "title": "Episode 2",
            "description": "Only the public episode notes.",
            "date": None,
            "media_url": "https://cdn.example.com/episodes/2.mp3",
        }
    ]

    with connect(pg_clean) as conn:
        conn.execute(
            """
            INSERT INTO sources(slug, name, url, category, kind, priority, enabled)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            (source.slug, source.name, source.url, source.category, source.kind, source.priority),
        )

    with (
        patch("news_dashboard.ingest._parse_media_feed_url", return_value=entries),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("", None)),
        patch("news_dashboard.ai_client.chat_create") as chat_create,
    ):
        outcome = _ingest_source(source, pg_clean)

    assert outcome.articles_new == 1
    chat_create.assert_not_called()
    with connect(pg_clean) as conn:
        row = conn.execute(
            "SELECT summary, tags FROM articles WHERE source_slug=%s",
            (source.slug,),
        ).fetchone()
    assert (
        row["summary"]
        == "Only the public episode notes.\n\nSource media: https://cdn.example.com/episodes/2.mp3"
    )
    assert row["tags"] == "media,podcast"
