from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from news_dashboard.ai_client import ManagedPrompt
from news_dashboard.db import connect
from news_dashboard.ingest.service import _ingest_source
from news_dashboard.sources.service import SourceDefinition


def _chat_model(response: SimpleNamespace) -> MagicMock:
    model = MagicMock()
    model.invoke.return_value = AIMessage(content=response.choices[0].message.content)
    return model


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
    from langchain_core.callbacks import BaseCallbackHandler

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

    callback = BaseCallbackHandler()
    with (
        patch("news_dashboard.ingest.service._parse_media_feed_url", return_value=entries),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("test-key", None)),
        patch(
            "news_dashboard.ai_client.get_chat_model", return_value=_chat_model(response)
        ) as get_model,
        patch("news_dashboard.ai_client.langfuse_enabled", return_value=True),
        patch("langfuse.langchain.CallbackHandler", return_value=callback),
        patch("langfuse.propagate_attributes") as attributes,
    ):
        outcome = _ingest_source(source, pg_clean)

    assert outcome.articles_new == 1
    assert get_model.call_args.kwargs["max_tokens"] == 500
    assert get_model.call_args.kwargs["temperature"] == 0.2
    assert callback in get_model.return_value.invoke.call_args.kwargs["config"]["callbacks"]
    attributes.assert_called_once_with(
        tags=["ingest", "media"], trace_name="summarize-media-article"
    )
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
        patch("news_dashboard.ingest.service._parse_media_feed_url", return_value=entries),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("test-key", None)),
        patch("news_dashboard.ai_client.get_chat_model", return_value=_chat_model(response)),
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


def test_media_summary_uses_managed_chat_prompt() -> None:
    from news_dashboard.ingest.service import _MEDIA_SUMMARY_PROMPT, _media_summary

    managed = ManagedPrompt(
        text=None,
        messages=[{"role": "user", "content": "compiled media prompt"}],
        langfuse_prompt=object(),
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Managed summary"))]
    )
    entry = {"transcript": "Transcript", "media_url": "https://example.com/media"}

    with (
        patch("news_dashboard.ai_client.free_llm_config", return_value=("key", None)),
        patch("news_dashboard.ai_client.get_chat_client", return_value=object()),
        patch("news_dashboard.ai_client.get_prompt", return_value=managed) as get_prompt,
        patch("news_dashboard.ai_client.chat_create", return_value=response) as chat_create,
    ):
        summary = _media_summary("Title", "Description", entry)

    assert summary == "Managed summary\n\nSource media: https://example.com/media"
    get_prompt.assert_called_once_with(
        "summarize-media-article",
        fallback=_MEDIA_SUMMARY_PROMPT,
        prompt_type="chat",
        label="production",
        variables={
            "title": "Title",
            "description": "Description",
            "transcript": "Transcript",
        },
    )
    assert chat_create.call_args.kwargs["prompt"] is managed
    assert chat_create.call_args.kwargs["messages"] == managed.messages


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
        patch("news_dashboard.ingest.service._parse_media_feed_url", return_value=entries),
        patch("news_dashboard.ai_client.free_llm_config", return_value=("", None)),
        patch("news_dashboard.ai_client.get_chat_model") as get_chat_model,
    ):
        outcome = _ingest_source(source, pg_clean)

    assert outcome.articles_new == 1
    get_chat_model.assert_not_called()
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
