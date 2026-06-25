"""Tests for the /api/changelog endpoint."""

from __future__ import annotations

from textwrap import dedent
from unittest.mock import patch

from fastapi.testclient import TestClient

from news_dashboard.main import _parse_changelog, app


def _client() -> TestClient:
    app.dependency_overrides.clear()
    return TestClient(app, follow_redirects=False)


# ── _parse_changelog unit tests ───────────────────────────────────────────────


def test_parse_changelog_returns_entries() -> None:
    md = dedent("""\
        # Changelog

        ## 1.2.0
        - Feature A
        - Feature B

        ## 1.1.0
        - Bug fix C
    """)
    with patch("news_dashboard.main._CHANGELOG_FILE") as cf:
        cf.read_text.return_value = md
        entries = _parse_changelog()
    assert len(entries) == 2
    assert entries[0] == {"version": "1.2.0", "items": ["Feature A", "Feature B"]}
    assert entries[1] == {"version": "1.1.0", "items": ["Bug fix C"]}


def test_parse_changelog_returns_empty_on_oserror() -> None:
    with patch("news_dashboard.main._CHANGELOG_FILE") as cf:
        cf.read_text.side_effect = OSError("missing")
        entries = _parse_changelog()
    assert entries == []


def test_parse_changelog_ignores_non_bullet_lines() -> None:
    md = dedent("""\
        ## 2.0.0
        Some intro text.
        - Real item
    """)
    with patch("news_dashboard.main._CHANGELOG_FILE") as cf:
        cf.read_text.return_value = md
        entries = _parse_changelog()
    assert entries == [{"version": "2.0.0", "items": ["Real item"]}]


# ── /api/changelog endpoint ───────────────────────────────────────────────────


def test_changelog_endpoint_returns_version_and_entries() -> None:
    md = dedent("""\
        ## 9.9.9
        - New thing
    """)
    with (
        patch("news_dashboard.main._VERSION_FILE") as vf,
        patch("news_dashboard.main._CHANGELOG_FILE") as cf,
    ):
        vf.read_text.return_value = "9.9.9\n"
        cf.read_text.return_value = md
        resp = _client().get("/api/changelog")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == "9.9.9"
    assert body["entries"] == [{"version": "9.9.9", "items": ["New thing"]}]


def test_changelog_endpoint_version_falls_back_to_unknown() -> None:
    with (
        patch("news_dashboard.main._VERSION_FILE") as vf,
        patch("news_dashboard.main._CHANGELOG_FILE") as cf,
    ):
        vf.read_text.side_effect = OSError("missing")
        cf.read_text.return_value = "## 1.0.0\n- item\n"
        resp = _client().get("/api/changelog")
    assert resp.status_code == 200
    assert resp.json()["version"] == "unknown"


def test_changelog_endpoint_entries_empty_on_missing_file() -> None:
    with (
        patch("news_dashboard.main._VERSION_FILE") as vf,
        patch("news_dashboard.main._CHANGELOG_FILE") as cf,
    ):
        vf.read_text.return_value = "1.0.0\n"
        cf.read_text.side_effect = OSError("missing")
        resp = _client().get("/api/changelog")
    assert resp.status_code == 200
    assert resp.json()["entries"] == []
