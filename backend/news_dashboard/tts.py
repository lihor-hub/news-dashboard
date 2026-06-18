"""Text-to-Speech generation for articles using the OpenAI TTS API.

Generates MP3 audio for an article and caches it at
DATA_DIR/audio/<article_id>.mp3.  Subsequent calls return the cached file
without hitting the API again.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = Path("/data")
_VOICE = "alloy"
_MODEL = "tts-1"
_MAX_CHARS = 4096


class TTSNotConfiguredError(Exception):
    """Raised when OPENAI_API_KEY is not set."""


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", str(_DEFAULT_DATA_DIR)))


def _audio_path(article_id: int, data_dir: Path | None = None) -> Path:
    base = data_dir if data_dir is not None else _data_dir()
    return base / "audio" / f"{article_id}.mp3"


def _build_text(article: dict[str, Any]) -> str:
    title = str(article.get("title") or "")
    body = str(article.get("body") or "")
    summary = str(article.get("summary") or "")
    # Prefer full body; fall back to summary when body is absent or too short.
    content = body if len(body) > len(summary) else summary
    text = f"{title}.\n\n{content}" if title else content
    return text[:_MAX_CHARS]


def generate_audio(
    article_id: int,
    article: dict[str, Any],
    data_dir: Path | None = None,
) -> Path:
    """Return path to cached MP3, generating it via OpenAI TTS if needed.

    Raises TTSNotConfiguredError when OPENAI_API_KEY is absent.
    Raises RuntimeError on API failure.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        msg = "OPENAI_API_KEY is not configured"
        raise TTSNotConfiguredError(msg)

    path = _audio_path(article_id, data_dir)

    if path.exists():
        logger.debug("TTS cache hit for article %d", article_id)
        return path

    text = _build_text(article)
    if not text.strip():
        msg = "article has no readable text"
        raise ValueError(msg)

    path.parent.mkdir(parents=True, exist_ok=True)

    from openai import OpenAI  # lazy import — optional dep at import time

    client = OpenAI(api_key=api_key)
    logger.info("Generating TTS audio for article %d (%d chars)", article_id, len(text))
    with client.audio.speech.with_streaming_response.create(
        model=_MODEL, voice=_VOICE, input=text
    ) as response:
        response.stream_to_file(path)
    logger.info("TTS audio cached at %s", path)
    return path
