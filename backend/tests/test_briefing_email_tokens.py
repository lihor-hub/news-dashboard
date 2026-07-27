"""Security contract for briefing-email unsubscribe tokens."""

from __future__ import annotations

import time

import pytest
from itsdangerous import URLSafeTimedSerializer

from news_dashboard.briefing_email.tokens import (
    make_unsubscribe_token,
    verify_unsubscribe_token,
)

_SALT = "news-dashboard-briefing-email-unsubscribe-v1"


def test_unsubscribe_token_round_trip() -> None:
    assert verify_unsubscribe_token(make_unsubscribe_token(42)) == 42


def test_unsubscribe_token_rejects_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "time", lambda: 1_700_000_006.0)
    token = make_unsubscribe_token(42)
    payload, timestamp, signature = token.split(".")
    replacement = "A" if payload[0] != "A" else "B"
    tampered_token = f"{replacement}{payload[1:]}.{timestamp}.{signature}"
    with pytest.raises(ValueError, match="Invalid unsubscribe token"):
        verify_unsubscribe_token(tampered_token)


def test_unsubscribe_token_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "time", lambda: 1_000.0)
    token = make_unsubscribe_token(42)
    monkeypatch.setattr(time, "time", lambda: 1_002.0)
    with pytest.raises(ValueError, match="Invalid unsubscribe token"):
        verify_unsubscribe_token(token, max_age_seconds=1)


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": 42, "action": "preview", "version": 1},
        {"user_id": 42, "action": "unsubscribe", "version": 2},
    ],
)
def test_unsubscribe_token_is_purpose_and_version_bound(payload: dict[str, object]) -> None:
    serializer = URLSafeTimedSerializer(
        "test-secret-key-not-for-production",
        salt=_SALT,
    )
    with pytest.raises(ValueError, match="Invalid unsubscribe token"):
        verify_unsubscribe_token(serializer.dumps(payload))


def test_token_payload_contains_no_email() -> None:
    token = make_unsubscribe_token(42)
    assert "reader@example.com" not in token
    assert verify_unsubscribe_token(token) == 42
