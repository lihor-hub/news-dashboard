"""Application version read from the VERSION file baked into the image."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


@lru_cache(maxsize=1)
def read_app_version() -> str:
    """Return the running app version from the VERSION file baked into the image."""
    try:
        return _VERSION_FILE.read_text().strip() or "unknown"
    except OSError:
        return "unknown"
