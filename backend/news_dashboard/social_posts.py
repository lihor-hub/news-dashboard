"""Helpers shared by social-feed ingestion and article presentation."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_NITTER_STATUS_PATH = re.compile(r"^/([^/]+)/status/(\d+)")


def canonical_x_status_url(url: str) -> str:
    """Normalize a Nitter/X status permalink to the publisher's canonical host."""
    match = _NITTER_STATUS_PATH.match(urlparse(url).path)
    if match is None:
        return url
    handle, status_id = match.groups()
    return f"https://x.com/{handle}/status/{status_id}"
