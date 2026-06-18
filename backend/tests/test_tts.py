"""Unit tests for news_dashboard.tts.

All OpenAI calls are mocked so these run without a live API key or network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from news_dashboard.tts import TTSNotConfiguredError, _build_text, generate_audio

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
        patch("openai.OpenAI", return_value=mock_client),
    ):
        path = generate_audio(42, _ARTICLE, data_dir=tmp_path)

    assert path.exists()
    assert path.read_bytes() == b"fake-mp3-data"
    mock_client.audio.speech.with_streaming_response.create.assert_called_once()
    call_kwargs = mock_client.audio.speech.with_streaming_response.create.call_args
    assert call_kwargs.kwargs["model"] == "tts-1"
    assert call_kwargs.kwargs["voice"] == "alloy"
    assert "Test Article Title" in call_kwargs.kwargs["input"]


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
