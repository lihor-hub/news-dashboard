from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from news_dashboard import chatgpt_auth


def _credentials() -> dict[str, object]:
    return {
        "client_id": "oaiapp_test",
        "subject": "user-test",
        "issuer": "https://auth.openai.com",
        "access_token": "old-token",
        "refresh_token": "old-refresh",
        "id_token": "identity",
        "scopes": ["chatgpt.tokens.use.direct"],
        "expires_at": time.time() + 3600,
    }


def test_credentials_are_written_with_owner_only_permissions(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    chatgpt_auth.save_credentials(path, _credentials())
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())["access_token"] == _credentials()["access_token"]


def test_refresh_rotates_tokens_atomically(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    record = _credentials()
    record["expires_at"] = time.time() - 1
    chatgpt_auth.save_credentials(path, record)
    replacement = {
        "access_token": "new-token",
        "refresh_token": "new-refresh",
        "expires_in": 3600,
        "scope": "chatgpt.tokens.use.direct offline_access",
    }
    with patch("news_dashboard.chatgpt_auth.token_request", return_value=replacement) as request:
        assert chatgpt_auth.access_token(path) == "new-token"
        assert chatgpt_auth.access_token(path) == "new-token"
    request.assert_called_once()
    assert request.call_args.args[0]["client_id"] == "oaiapp_test"
    saved = json.loads(path.read_text())
    assert saved["refresh_token"] == replacement["refresh_token"]
    assert saved["subject"] == "user-test"


def test_missing_plan_scope_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    record = _credentials()
    record["scopes"] = ["openid"]
    chatgpt_auth.save_credentials(path, record)
    with pytest.raises(chatgpt_auth.ChatGPTAuthError, match="permission"):
        chatgpt_auth.access_token(path)


def test_failed_refresh_keeps_saved_credentials(tmp_path: Path) -> None:
    path = tmp_path / "credentials.json"
    record = _credentials()
    record["expires_at"] = 0
    chatgpt_auth.save_credentials(path, record)
    before = path.read_bytes()
    with (
        patch(
            "news_dashboard.chatgpt_auth.token_request",
            side_effect=chatgpt_auth.ChatGPTAuthError("refresh failed"),
        ),
        pytest.raises(chatgpt_auth.ChatGPTAuthError),
    ):
        chatgpt_auth.access_token(path)
    assert path.read_bytes() == before


def test_callback_requires_matching_state_and_issued_client_id() -> None:
    with pytest.raises(chatgpt_auth.ChatGPTAuthError, match="state"):
        chatgpt_auth.validate_callback(
            {"state": ["wrong"], "code": ["code"]},
            state="expected",
            client_id="dynamic_agent_client",
        )
    with pytest.raises(chatgpt_auth.ChatGPTAuthError, match="client"):
        chatgpt_auth.validate_callback(
            {"state": ["expected"], "code": ["code"]},
            state="expected",
            client_id="dynamic_agent_client",
        )
    with pytest.raises(chatgpt_auth.ChatGPTAuthError, match="client"):
        chatgpt_auth.validate_callback(
            {"state": ["expected"], "code": ["code"], "client_id": ["oaiapp_other"]},
            state="expected",
            client_id="oaiapp_saved",
        )


@pytest.mark.parametrize("invalid", ["signature", "issuer", "audience", "nonce", "expiry"])
def test_identity_validation_rejects_untrusted_tokens(invalid: str) -> None:
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims: dict[str, object] = {
        "sub": "user-test",
        "iss": "https://auth.openai.com",
        "aud": "oaiapp_test",
        "exp": time.time() + 3600,
        "iat": time.time(),
        "nonce": "expected",
    }
    field, value = {
        "issuer": ("iss", "https://wrong.invalid"),
        "audience": ("aud", "wrong-client"),
        "nonce": ("nonce", "wrong-nonce"),
        "expiry": ("exp", time.time() - 60),
        "signature": ("sub", "user-test"),
    }[invalid]
    claims[field] = value
    encoded = jwt.encode(claims, key, algorithm="RS256")
    public_key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
        if invalid == "signature"
        else key.public_key()
    )
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    discovery = MagicMock()
    discovery.json.return_value = {
        "issuer": "https://auth.openai.com",
        "jwks_uri": "https://auth.openai.com/jwks",
    }
    with (
        patch("httpx.get", return_value=discovery),
        patch("jwt.PyJWKClient") as jwks,
    ):
        jwks.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key=public_key)
        with pytest.raises(chatgpt_auth.ChatGPTAuthError, match=r"validation|nonce"):
            chatgpt_auth._verified_identity({"id_token": encoded}, "oaiapp_test", "expected")


def test_concurrent_requests_refresh_rotating_session_once(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "credentials.json"
    record = _credentials()
    record["expires_at"] = 0
    chatgpt_auth.save_credentials(path, record)
    replacement = {
        "access_token": "new",
        "refresh_token": "rotated",
        "expires_in": 3600,
        "scope": "chatgpt.tokens.use.direct offline_access",
    }
    with (
        patch("news_dashboard.chatgpt_auth.token_request", return_value=replacement) as refresh,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        tokens = list(pool.map(lambda _: chatgpt_auth.access_token(path), range(2)))
    assert tokens == ["new", "new"]
    refresh.assert_called_once()
