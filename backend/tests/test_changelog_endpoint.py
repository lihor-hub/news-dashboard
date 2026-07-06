"""Tests for the /api/changelog endpoint."""

from __future__ import annotations

from textwrap import dedent
from unittest.mock import patch

from fastapi.testclient import TestClient

from news_dashboard.main import app
from news_dashboard.system.service import parse_changelog


def _client() -> TestClient:
    app.dependency_overrides.clear()
    return TestClient(app, follow_redirects=False)


# ── parse_changelog unit tests ────────────────────────────────────────────────


def test_parse_changelog_returns_entries() -> None:
    md = dedent("""\
        # Changelog

        ## 1.2.0
        - Feature A
        - Feature B

        ## 1.1.0
        - Bug fix C
    """)
    with patch("news_dashboard.system.service._CHANGELOG_FILE") as cf:
        cf.read_text.return_value = md
        entries = parse_changelog()
    assert len(entries) == 2
    assert entries[0] == {"version": "1.2.0", "date": None, "items": ["Feature A", "Feature B"]}
    assert entries[1] == {"version": "1.1.0", "date": None, "items": ["Bug fix C"]}


def test_parse_changelog_normalizes_keep_a_changelog_headings() -> None:
    md = dedent("""\
        # Changelog

        ## [1.22.0] — 2026-07-03
        - New feature

        ## [1.21.0] - 2026-06-26

        ### Added
        - Share articles
    """)
    with patch("news_dashboard.system.service._CHANGELOG_FILE") as cf:
        cf.read_text.return_value = md
        entries = parse_changelog()
    assert entries == [
        {"version": "1.22.0", "date": "2026-07-03", "items": ["New feature"]},
        {"version": "1.21.0", "date": "2026-06-26", "items": ["Share articles"]},
    ]


def test_parse_changelog_returns_empty_on_oserror() -> None:
    with patch("news_dashboard.system.service._CHANGELOG_FILE") as cf:
        cf.read_text.side_effect = OSError("missing")
        entries = parse_changelog()
    assert entries == []


def test_parse_changelog_ignores_non_bullet_lines() -> None:
    md = dedent("""\
        ## 2.0.0
        Some intro text.
        - Real item
    """)
    with patch("news_dashboard.system.service._CHANGELOG_FILE") as cf:
        cf.read_text.return_value = md
        entries = parse_changelog()
    assert entries == [{"version": "2.0.0", "date": None, "items": ["Real item"]}]


# ── /api/changelog endpoint ───────────────────────────────────────────────────


def test_changelog_endpoint_returns_version_and_entries() -> None:
    md = dedent("""\
        ## 9.9.9
        - New thing
    """)
    with patch("news_dashboard.system.service._CHANGELOG_FILE") as cf:
        cf.read_text.return_value = md
        resp = _client().get("/api/changelog")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == app.version
    assert body["entries"] == [{"version": "9.9.9", "date": None, "items": ["New thing"]}]


def test_changelog_endpoint_version_matches_app_version() -> None:
    with patch("news_dashboard.system.service._CHANGELOG_FILE") as cf:
        cf.read_text.return_value = "## 1.0.0\n- item\n"
        resp = _client().get("/api/changelog")
    assert resp.status_code == 200
    assert resp.json()["version"] == app.version


def test_changelog_endpoint_entries_empty_on_missing_file() -> None:
    with patch("news_dashboard.system.service._CHANGELOG_FILE") as cf:
        cf.read_text.side_effect = OSError("missing")
        resp = _client().get("/api/changelog")
    assert resp.status_code == 200
    assert resp.json()["entries"] == []
