"""Unit tests for news_dashboard.tts.

All OpenAI calls are mocked so these run without a live API key or network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from news_dashboard.tts import (
    TTSNotConfiguredError,
    _build_text,
    _script_ai_config,
    _tts_ai_config,
    generate_audio,
    generate_podcast_audio,
    generate_podcast_script,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

_ARTICLE: dict[str, Any] = {
    "id": 42,
    "title": "Test Article Title",
    "body": "This is the full article body text.",
    "summary": "Short summary.",
}

_ARTICLE_NO_BODY: dict[str, Any] = {
    "id": 43,
    "title": "No Body Article",
    "body": None,
    "summary": "Only a summary here.",
}

_ARTICLE_EMPTY: dict[str, Any] = {
    "id": 44,
    "title": "",
    "body": None,
    "summary": "",
}


# ── _build_text ───────────────────────────────────────────────────────────────


def test_build_text_prefers_body_over_summary() -> None:
    text = _build_text(_ARTICLE)
    assert "full article body text" in text
    assert "Short summary" not in text


def test_build_text_falls_back_to_summary_when_no_body() -> None:
    text = _build_text(_ARTICLE_NO_BODY)
    assert "Only a summary here" in text


def test_build_text_includes_title() -> None:
    text = _build_text(_ARTICLE)
    assert "Test Article Title" in text


def test_build_text_truncates_to_max_chars() -> None:
    long_article = {
        "id": 1,
        "title": "T",
        "body": "x" * 10_000,
        "summary": "",
    }
    text = _build_text(long_article)
    assert len(text) <= 4096


# ── generate_audio — no API key ───────────────────────────────────────────────


def test_generate_audio_raises_when_no_api_key(tmp_path: Path) -> None:
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("OPENAI_API_KEY", None)
        with pytest.raises(TTSNotConfiguredError):
            generate_audio(42, _ARTICLE, data_dir=tmp_path)


def test_tts_ai_config_uses_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://openai-base/v1")

    api_key, base_url = _tts_ai_config()

    assert api_key == "sk-openai"
    assert base_url == "http://openai-base/v1"


def test_tts_ai_config_uses_shared_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-shared")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://shared-gateway:9130/v1")

    api_key, base_url = _tts_ai_config()

    assert api_key == "sk-shared"
    assert base_url == "http://shared-gateway:9130/v1"


def test_tts_ai_config_no_base_url_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-shared")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    api_key, base_url = _tts_ai_config()

    assert api_key == "sk-shared"
    assert base_url is None


# ── generate_audio — cache miss (calls API) ───────────────────────────────────


def test_generate_audio_calls_openai_and_writes_file(tmp_path: Path) -> None:
    mock_response = MagicMock()

    def fake_stream(path: Path) -> None:
        path.write_bytes(b"fake-mp3-data")

    mock_response.stream_to_file.side_effect = fake_stream
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.audio.speech.with_streaming_response.create.return_value = mock_response

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client) as mock_factory,
    ):
        path = generate_audio(42, _ARTICLE, data_dir=tmp_path)

    assert path.exists()
    assert path.read_bytes() == b"fake-mp3-data"
    mock_client.audio.speech.with_streaming_response.create.assert_called_once()
    call_kwargs = mock_client.audio.speech.with_streaming_response.create.call_args
    assert call_kwargs.kwargs["model"] == "tts-1"
    assert call_kwargs.kwargs["voice"] == "alloy"
    assert "Test Article Title" in call_kwargs.kwargs["input"]
    mock_factory.assert_called_once_with(api_key="sk-test", timeout=120.0)


def test_generate_audio_uses_configured_gateway_base_url(tmp_path: Path) -> None:
    mock_response = MagicMock()

    def fake_stream(path: Path) -> None:
        path.write_bytes(b"fake-mp3-data")

    mock_response.stream_to_file.side_effect = fake_stream
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.audio.speech.with_streaming_response.create.return_value = mock_response

    with (
        patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_BASE_URL": "http://shared-gateway:9130/v1",
            },
        ),
        patch("openai.OpenAI", return_value=mock_client) as mock_factory,
    ):
        path = generate_audio(42, _ARTICLE, data_dir=tmp_path)

    assert path.exists()
    mock_factory.assert_called_once_with(
        api_key="sk-test", base_url="http://shared-gateway:9130/v1", timeout=120.0
    )


# ── generate_audio — cache hit (skips API) ────────────────────────────────────


def test_generate_audio_returns_cached_file_without_api_call(tmp_path: Path) -> None:
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    cached = audio_dir / "42.mp3"
    cached.write_bytes(b"cached-mp3")

    mock_client = MagicMock()

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        path = generate_audio(42, _ARTICLE, data_dir=tmp_path)

    assert path == cached
    mock_client.audio.speech.with_streaming_response.create.assert_not_called()


# ── generate_audio — empty article ────────────────────────────────────────────


def test_generate_audio_raises_for_empty_article(tmp_path: Path) -> None:
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        pytest.raises(ValueError, match="no readable text"),
    ):
        generate_audio(44, _ARTICLE_EMPTY, data_dir=tmp_path)


# ── generate_audio — creates audio directory if needed ───────────────────────


def test_generate_audio_creates_audio_directory(tmp_path: Path) -> None:
    mock_response = MagicMock()

    def fake_stream(path: Path) -> None:
        path.write_bytes(b"mp3")

    mock_response.stream_to_file.side_effect = fake_stream
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)
    mock_client = MagicMock()
    mock_client.audio.speech.with_streaming_response.create.return_value = mock_response

    data_dir = tmp_path / "nonexistent"
    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        path = generate_audio(42, _ARTICLE, data_dir=data_dir)

    assert path.parent.is_dir()
    assert path.exists()


# ── _script_ai_config ─────────────────────────────────────────────────────────


def test_script_ai_config_uses_free_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREE_LLM_API_KEY", "sk-free-llm")
    monkeypatch.setenv("FREE_LLM_BASE_URL", "http://free-gw:9130/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    api_key, base_url = _script_ai_config()

    assert api_key == "sk-free-llm"
    assert base_url == "http://free-gw:9130/v1"


def test_script_ai_config_falls_back_to_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-shared")
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("FREE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    api_key, base_url = _script_ai_config()

    assert api_key == "sk-shared"
    assert base_url is None


def test_script_ai_config_raises_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(TTSNotConfiguredError):
        _script_ai_config()


# ── generate_podcast_script ───────────────────────────────────────────────────


def test_generate_podcast_script() -> None:
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=(
                    '{"script": ['
                    '{"speaker": "Alex", "voice": "alloy", "text": "Hello!"}, '
                    '{"speaker": "Taylor", "voice": "shimmer", "text": "Hi Alex!"}'
                    "]}"
                )
            )
        )
    ]
    with (
        patch.dict("os.environ", {"FREE_LLM_API_KEY": "sk-free-llm"}),
        patch("news_dashboard.ai_client.chat_create", return_value=mock_response),
    ):
        script = generate_podcast_script(
            {
                "title": "Briefing",
                "summary": "Briefing Summary",
                "sections": [{"title": "S1", "body": "Body 1"}],
            }
        )
    assert len(script) == 2
    assert script[0]["speaker"] == "Alex"
    assert script[0]["voice"] == "alloy"
    assert script[0]["text"] == "Hello!"
    assert script[1]["speaker"] == "Taylor"
    assert script[1]["voice"] == "shimmer"
    assert script[1]["text"] == "Hi Alex!"


def test_generate_podcast_script_raises_when_no_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FREE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(TTSNotConfiguredError):
        generate_podcast_script({"title": "T", "summary": "S", "sections": []})


def test_generate_podcast_audio(tmp_path: Path) -> None:
    mock_response = MagicMock()
    written_chunks = []

    def fake_stream(path: Path) -> None:
        written_chunks.append(path.name)
        path.write_bytes(f"fake-mp3-chunk-{len(written_chunks)}".encode())

    mock_response.stream_to_file.side_effect = fake_stream
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.audio.speech.with_streaming_response.create.return_value = mock_response

    script = [
        {"speaker": "Alex", "voice": "alloy", "text": "Chunk 1 text"},
        {"speaker": "Taylor", "voice": "shimmer", "text": "Chunk 2 text"},
    ]

    with (
        patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}),
        patch("openai.OpenAI", return_value=mock_client),
    ):
        path = generate_podcast_audio(123, script, data_dir=tmp_path)

    assert path.exists()
    assert path.read_bytes() == b"fake-mp3-chunk-1fake-mp3-chunk-2"
    assert len(written_chunks) == 2
    for idx in range(2):
        chunk_file = tmp_path / "audio" / f"podcast-123-chunk-{idx}.mp3"
        assert not chunk_file.exists()
