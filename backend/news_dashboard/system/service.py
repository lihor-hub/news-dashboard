"""Business logic for health/readiness checks, metrics, and changelog parsing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from news_dashboard.db import connect, init_db
from news_dashboard.error_tracking import frontend_error_tracking_dsn

_CHANGELOG_FILE = Path(__file__).resolve().parents[3] / "CHANGELOG.md"

# "## 1.2.3" or Keep a Changelog style "## [1.2.3] — 2026-07-03" (em dash or
# hyphen). The version must come out bare: the frontend What's New popup
# matches entry.version against the app version exactly.
_CHANGELOG_HEADING = re.compile(r"^##\s+\[?(?P<version>[^\]\s]+)\]?(?:\s*[—-]\s*(?P<date>\S+))?")

# Defense in depth: the release pipeline sanitizes generated notes before they
# reach CHANGELOG.md, but reject any bullet that still looks like leaked model
# reasoning rather than a genuine release note.
_LEAKED_REASONING_RE = re.compile(
    r"</?think>|^(the user wants|i'll |i should|i need to|let me |as an ai)",
    re.IGNORECASE,
)


def check_health() -> None:
    init_db()


def check_readiness() -> None:
    with connect() as conn:
        conn.execute("SELECT 1")


def graph_status() -> dict[str, str]:
    """Report optional Neo4j availability without making readiness depend on it."""
    from news_dashboard.graph_store import GraphUnavailableError, graph_store_from_env

    try:
        graph_store = graph_store_from_env()
    except GraphUnavailableError as exc:
        return {"status": "unavailable", "detail": str(exc)}
    if graph_store is None:
        return {"status": "disabled"}
    try:
        graph_store.verify_connectivity()
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}
    else:
        return {"status": "ok"}
    finally:
        close = getattr(graph_store, "close", None)
        if callable(close):
            close()


def public_config() -> dict[str, Any]:
    """Public, non-sensitive runtime config the SPA needs before login.

    ``sentry_dsn`` is a Sentry/GlitchTip DSN, which is designed to be
    exposed to clients — it only lets a client *send* events, not read data.
    """
    return {"sentry_dsn": frontend_error_tracking_dsn()}


def parse_changelog() -> list[dict[str, object]]:
    try:
        text = _CHANGELOG_FILE.read_text()
    except OSError:
        return []
    entries: list[dict[str, object]] = []
    current_items: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            m = _CHANGELOG_HEADING.match(line)
            current_items = []
            entries.append(
                {
                    "version": m.group("version") if m else line[3:].strip(),
                    "date": m.group("date") if m else None,
                    "items": current_items,
                }
            )
        elif line.startswith("- ") and entries:
            item = line[2:].strip()
            if not _LEAKED_REASONING_RE.search(item):
                current_items.append(item)
    return entries
