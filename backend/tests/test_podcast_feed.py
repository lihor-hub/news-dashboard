"""Unit tests for the podcast feed token and RSS-generation helpers (#654)."""

from __future__ import annotations

import pytest

from news_dashboard import podcast_feed


def test_token_roundtrip_verifies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("news_dashboard.auth.get_podcast_feed_token_version", lambda _uid: 1)
    token = podcast_feed.make_feed_token(7, 1)
    assert podcast_feed.verify_feed_token(token) == 7


def test_token_rejected_after_version_bump(monkeypatch: pytest.MonkeyPatch) -> None:
    token = podcast_feed.make_feed_token(7, 1)
    monkeypatch.setattr("news_dashboard.auth.get_podcast_feed_token_version", lambda _uid: 2)
    assert podcast_feed.verify_feed_token(token) is None


def test_token_rejects_garbage() -> None:
    assert podcast_feed.verify_feed_token("not-a-token") is None


def test_token_rejects_tampered_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("news_dashboard.auth.get_podcast_feed_token_version", lambda _uid: 1)
    token = podcast_feed.make_feed_token(7, 1)
    tampered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert podcast_feed.verify_feed_token(tampered) is None


def test_token_rejects_wrong_user_id_substitution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("news_dashboard.auth.get_podcast_feed_token_version", lambda _uid: 1)
    token = podcast_feed.make_feed_token(7, 1)
    replayed = token.replace("7.", "8.", 1)
    assert podcast_feed.verify_feed_token(replayed) is None


def test_missing_token_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOKEN_SECRET", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("TEST_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError):
        podcast_feed.make_feed_token(7, 1)


def test_build_feed_xml_includes_enclosure_and_self_link() -> None:
    token = "1.1.deadbeef"  # noqa: S105
    xml = podcast_feed.build_feed_xml(
        token=token,
        briefings=[
            {
                "id": 3,
                "created_at": "2026-06-13T12:00:00+00:00",
                "title": "Daily Brief",
                "summary": "A summary.",
                "audio_bytes": 1234,
            }
        ],
    )
    assert "<title>Daily Brief</title>" in xml
    assert 'length="1234"' in xml
    assert 'type="audio/mpeg"' in xml
    assert f"podcast.rss?token={token}" in xml
    assert f"/api/briefings/3/podcast-audio?token={token}" in xml


def test_build_feed_xml_handles_no_episodes() -> None:
    xml = podcast_feed.build_feed_xml(token="1.1.deadbeef", briefings=[])  # noqa: S106
    assert "<rss" in xml
    assert "<item>" not in xml
