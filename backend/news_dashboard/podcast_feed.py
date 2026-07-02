"""Per-user podcast RSS feed for daily briefings.

Exposes a revocable, cookie-free feed URL so a standard podcast client can
subscribe to previously-generated briefing audio. Tokens are HMAC-signed
(same pattern as ``digest.py`` mark-read tokens) and bound to a per-user
version counter stored on ``users.podcast_feed_token_version`` — bumping the
counter instantly invalidates every token issued for the old version.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any

logger = logging.getLogger(__name__)

_TOKEN_SECRET_ENV_VARS = ("TOKEN_SECRET", "SESSION_SECRET", "TEST_SESSION_SECRET")


def _token_signing_secret() -> str | None:
    for env_var in _TOKEN_SECRET_ENV_VARS:
        secret = os.getenv(env_var)
        if secret:
            return secret
    return None


def _require_token_signing_secret() -> str:
    secret = _token_signing_secret()
    if secret is not None:
        return secret
    msg = "TOKEN_SECRET or SESSION_SECRET env var is required to sign podcast feed tokens."
    raise RuntimeError(msg)


def _token_signature(user_id: int, version: int, secret: str) -> str:
    msg = f"podcast-feed:{user_id}:{version}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:32]


def make_feed_token(user_id: int, version: int) -> str:
    """Return a signed token for the given user and token version."""
    signature = _token_signature(user_id, version, _require_token_signing_secret())
    return f"{user_id}.{version}.{signature}"


def verify_feed_token(token: str) -> int | None:
    """Return the owning user_id if the token is validly signed and not revoked."""
    from news_dashboard.auth import get_podcast_feed_token_version

    try:
        user_id_text, version_text, signature = token.split(".", 2)
        user_id = int(user_id_text)
        version = int(version_text)
    except ValueError:
        return None
    secret = _token_signing_secret()
    if secret is None:
        return None
    expected = _token_signature(user_id, version, secret)
    if not hmac.compare_digest(expected, signature):
        return None
    current_version = get_podcast_feed_token_version(user_id)
    if current_version is None or version != current_version:
        return None
    return user_id


def _base_url() -> str:
    return os.getenv("APP_BASE_URL", "http://localhost:8000")


def feed_url(token: str) -> str:
    return f"{_base_url()}/api/briefings/podcast.rss?token={token}"


def audio_url(briefing_id: int, token: str) -> str:
    return f"{_base_url()}/api/briefings/{briefing_id}/podcast-audio?token={token}"


def _rfc2822(value: Any) -> str | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return format_datetime(value)
    return None


def build_feed_xml(*, token: str, briefings: list[dict[str, Any]]) -> str:
    """Build a podcast RSS 2.0 (+ iTunes tags) document for the given briefings.

    Each entry in ``briefings`` must have ``id``, ``created_at``, ``title``,
    ``summary``, and ``audio_bytes`` (size in bytes of the already-generated
    MP3 for that briefing).
    """
    base = _base_url()
    itunes_ns = "http://www.itunes.org/dtds/podcast-1.0.dtd"
    atom_ns = "http://www.w3.org/2005/Atom"
    ET.register_namespace("itunes", itunes_ns)
    ET.register_namespace("atom", atom_ns)

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Your Daily Brief"
    ET.SubElement(channel, "link").text = base
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(
        channel, "description"
    ).text = "Your personal daily news briefing, delivered as a podcast."
    ET.SubElement(channel, f"{{{itunes_ns}}}author").text = "News Dashboard"
    ET.SubElement(channel, f"{{{itunes_ns}}}explicit").text = "false"
    atom_link = ET.SubElement(channel, f"{{{atom_ns}}}link")
    atom_link.set("href", feed_url(token))
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    for briefing in briefings:
        briefing_id = briefing["id"]
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = briefing.get("title") or f"Briefing #{briefing_id}"
        ET.SubElement(item, "description").text = briefing.get("summary") or ""
        pub_date = _rfc2822(briefing.get("created_at"))
        if pub_date:
            ET.SubElement(item, "pubDate").text = pub_date
        guid = ET.SubElement(item, "guid")
        guid.set("isPermaLink", "false")
        guid.text = f"briefing-{briefing_id}"
        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", audio_url(briefing_id, token))
        enclosure.set("length", str(briefing.get("audio_bytes") or 0))
        enclosure.set("type", "audio/mpeg")

    return ET.tostring(rss, encoding="unicode", xml_declaration=True)
