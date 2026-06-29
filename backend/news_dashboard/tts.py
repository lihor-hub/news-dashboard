"""Text-to-Speech generation for articles using the OpenAI TTS API.

Generates MP3 audio for an article and caches it at
DATA_DIR/audio/<article_id>.mp3.  Subsequent calls return the cached file
without hitting the API again.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = Path("/data")
_VOICE = "alloy"
_MODEL = "tts-1"
# Podcast audio uses the newer, more natural and steerable model and a pair of
# clearly distinct voices so the two co-hosts are easy to tell apart.
_PODCAST_MODEL = "gpt-4o-mini-tts"
_ALEX_VOICE = "onyx"
_TAYLOR_VOICE = "nova"
_MAX_CHARS = 4096


class TTSNotConfiguredError(Exception):
    """Raised when OPENAI_API_KEY is not set."""


def _tts_ai_config() -> tuple[str, str | None]:
    """Resolve the (api_key, base_url) for TTS audio synthesis (OpenAI only)."""
    from news_dashboard.ai_client import openai_config

    api_key, base_url = openai_config()
    if not api_key:
        msg = "OPENAI_API_KEY is not configured"
        raise TTSNotConfiguredError(msg)
    return api_key, base_url


def _script_ai_config() -> tuple[str, str | None]:
    """Resolve the (api_key, base_url) for podcast script (LLM chat) generation.

    Script generation is a chat-completion call that works on any OpenAI-compatible
    gateway, so it uses FREE_LLM_API_KEY. This is intentionally separate from
    ``_tts_ai_config`` because the free LLM gateway supports chat completions but
    not the ``audio/speech`` endpoint required for TTS audio synthesis.
    """
    from news_dashboard.ai_client import free_llm_config

    api_key, base_url = free_llm_config()
    if not api_key:
        msg = (
            "Podcast script generation requires an API key. Set FREE_LLM_API_KEY or OPENAI_API_KEY"
        )
        raise TTSNotConfiguredError(msg)
    return api_key, base_url


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
    api_key, base_url = _tts_ai_config()

    path = _audio_path(article_id, data_dir)

    if path.exists():
        logger.debug("TTS cache hit for article %d", article_id)
        return path

    text = _build_text(article)
    if not text.strip():
        msg = "article has no readable text"
        raise ValueError(msg)

    path.parent.mkdir(parents=True, exist_ok=True)

    from news_dashboard.ai_client import get_openai_client, tts_timeout_seconds

    client = get_openai_client(
        api_key=api_key, base_url=base_url, timeout_seconds=tts_timeout_seconds()
    )
    logger.info("Generating TTS audio for article %d (%d chars)", article_id, len(text))
    # audio/speech does not accept Langfuse trace kwargs, so TTS calls are
    # intentionally untraced. The wrapped client still routes through the same
    # factory but no span metadata is attached.
    with client.audio.speech.with_streaming_response.create(
        model=_MODEL, voice=_VOICE, input=text
    ) as response:
        response.stream_to_file(path)
    logger.info("TTS audio cached at %s", path)
    return path


def _podcast_audio_path(briefing_id: int, data_dir: Path | None = None) -> Path:
    base = data_dir if data_dir is not None else _data_dir()
    return base / "audio" / f"podcast-{briefing_id}.mp3"


def generate_podcast_audio(
    briefing_id: int,
    script: list[dict[str, str]],
    data_dir: Path | None = None,
) -> Path:
    """Return path to cached podcast MP3, generating it from script via OpenAI TTS if needed."""
    api_key, base_url = _tts_ai_config()

    path = _podcast_audio_path(briefing_id, data_dir)

    if path.exists():
        logger.debug("Podcast cache hit for briefing %d", briefing_id)
        return path

    if not script:
        msg = "podcast script is empty"
        raise ValueError(msg)

    path.parent.mkdir(parents=True, exist_ok=True)

    from news_dashboard.ai_client import get_openai_client, tts_timeout_seconds

    client = get_openai_client(
        api_key=api_key, base_url=base_url, timeout_seconds=tts_timeout_seconds()
    )

    combined_bytes = bytearray()
    for idx, entry in enumerate(script):
        voice = entry.get("voice", _ALEX_VOICE)
        text = entry.get("text", "")
        if not text.strip():
            continue

        logger.info(
            "Generating podcast TTS chunk %d/%d (%d chars, voice=%s)",
            idx + 1,
            len(script),
            len(text),
            voice,
        )

        chunk_path = path.parent / f"podcast-{briefing_id}-chunk-{idx}.mp3"
        try:
            with client.audio.speech.with_streaming_response.create(
                model=_PODCAST_MODEL, voice=voice, input=text
            ) as response:
                response.stream_to_file(chunk_path)

            combined_bytes.extend(chunk_path.read_bytes())
        finally:
            if chunk_path.exists():
                chunk_path.unlink()

    path.write_bytes(combined_bytes)
    logger.info("Podcast audio cached at %s", path)
    return path


_PODCAST_SYSTEM_PROMPT = (
    "You are a podcast script writer. Given a news briefing containing a title, summary, "
    "and several sections, rewrite the content into a natural, conversational dialogue script "
    "between two co-hosts, Alex and Taylor. Alex is a friendly and curious host, and "
    "Taylor is an insightful co-host. They alternate talking, explaining the news "
    "in an engaging and lively way.\n"
    "Produce a JSON object with a single key 'script' containing a list of dialogue turns. "
    "Each turn MUST be an object with these exact keys:\n"
    "  speaker — either 'Alex' or 'Taylor'\n"
    "  voice   — 'onyx' for Alex, 'nova' for Taylor\n"
    "  text    — the spoken text for this turn\n"
    "Ensure they talk about all the main topics in the sections. "
    "Return valid JSON only, no markdown wrapper."
)


def generate_podcast_script(briefing_content: dict[str, Any]) -> list[dict[str, str]]:
    """Generate a conversational podcast script from briefing content using LLM."""
    api_key, base_url = _script_ai_config()

    from news_dashboard.ai_client import chat_create, get_chat_client

    model = os.getenv("OPENAI_BRIEFING_MODEL", "gpt-4o-mini")
    client = get_chat_client(api_key=api_key, base_url=base_url)

    title = briefing_content.get("title", "")
    summary = briefing_content.get("summary", "")
    sections = briefing_content.get("sections", [])

    content_str = f"Podcast Title: {title}\nSummary: {summary}\n\nSegments:\n"
    for idx, sec in enumerate(sections):
        content_str += f"\nSegment {idx + 1}: {sec.get('title', '')}\n{sec.get('body', '')}\n"

    messages = [
        {"role": "system", "content": _PODCAST_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Please generate a podcast script for the following news:\n\n{content_str}",
        },
    ]

    response = chat_create(
        client,
        name="podcast-script-generation",
        tags=["podcast"],
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=2048,
    )

    text = response.choices[0].message.content or "{}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"AI returned invalid JSON: {exc}"
        raise ValueError(msg) from exc

    script = data.get("script", [])
    if not isinstance(script, list):
        msg = f"LLM returned invalid script format: {text}"
        raise TypeError(msg)

    valid_script = []
    for idx, item in enumerate(script):
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "")
        voice = str(item.get("voice") or "")
        txt = str(item.get("text") or "")

        if speaker.lower() == "alex":
            voice = _ALEX_VOICE
        elif speaker.lower() == "taylor":
            voice = _TAYLOR_VOICE
        else:
            speaker = "Alex" if idx % 2 == 0 else "Taylor"
            voice = _ALEX_VOICE if idx % 2 == 0 else _TAYLOR_VOICE

        if txt.strip():
            valid_script.append(
                {
                    "speaker": speaker,
                    "voice": voice,
                    "text": txt,
                }
            )

    if not valid_script:
        valid_script.append(
            {
                "speaker": "Alex",
                "voice": _ALEX_VOICE,
                "text": f"Welcome to the daily podcast. Today we are discussing: {summary}",
            }
        )

    return valid_script
