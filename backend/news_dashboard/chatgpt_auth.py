"""Operator-managed ChatGPT plan authorization for self-hosted installations.

Run ``python -m news_dashboard.chatgpt_auth login`` on the browser's machine.
Keep each registration in a separate protected credential file; select the
runtime account with CHATGPT_CREDENTIALS_FILE. No tokens enter the web UI.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tempfile
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import typer
from filelock import FileLock

_ISSUER = "https://auth.openai.com"
_RESOURCE = "https://api.openai.com/v1"
_PLAN_SCOPE = "chatgpt.tokens.use.direct"
_SCOPES = f"openid profile email offline_access resource.invoke {_PLAN_SCOPE}"
app = typer.Typer(help="Manage the selected self-hosted ChatGPT plan registration.")


class ChatGPTAuthError(RuntimeError):
    """Authorization is missing, invalid, expired, or cannot be renewed."""


def credentials_path() -> Path:
    """Return the selected registration's protected file."""
    configured = os.getenv("CHATGPT_CREDENTIALS_FILE")
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".config/news-dashboard/chatgpt.json"
    )


def save_credentials(path: Path, record: dict[str, Any]) -> None:
    """Replace a complete credential record atomically with Unix mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".chatgpt-")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(record, output)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_credentials(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_mode & 0o077:
            message = "ChatGPT credential file must have owner-only permissions (chmod 600)"
            raise ChatGPTAuthError(message)
        record = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        message = "ChatGPT credentials are unavailable; run the ChatGPT login command"
        raise ChatGPTAuthError(message) from exc
    if not isinstance(record, dict):
        message = "Invalid ChatGPT credential record"
        raise ChatGPTAuthError(message)
    return record


def token_request(form: dict[str, str]) -> dict[str, Any]:
    """Exchange/refresh without exposing provider response bodies or credentials."""
    try:
        response = httpx.post(f"{_ISSUER}/api/accounts/oauth/token", data=form, timeout=30)
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        message = "ChatGPT token exchange failed; retry sign-in if the session has expired"
        raise ChatGPTAuthError(message) from exc
    if not isinstance(result, dict):
        message = "Invalid ChatGPT token response"
        raise ChatGPTAuthError(message)
    return result


def _updated_tokens(record: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
    scopes = str(tokens.get("scope", "")).split()
    if _PLAN_SCOPE not in scopes:
        message = "ChatGPT plan permission was not granted; authorize plan usage during sign-in"
        raise ChatGPTAuthError(message)
    if not all(
        isinstance(tokens.get(key), str) and tokens[key]
        for key in ("access_token", "refresh_token")
    ):
        message = "ChatGPT token response is missing renewable credentials"
        raise ChatGPTAuthError(message)
    try:
        expires_in = float(tokens["expires_in"])
    except (KeyError, ValueError, TypeError) as exc:
        message = "ChatGPT token response is missing a valid expiry"
        raise ChatGPTAuthError(message) from exc
    if not 0 < expires_in <= 86400:
        message = "ChatGPT token response has an invalid expiry"
        raise ChatGPTAuthError(message)
    updated = {
        **record,
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "scopes": scopes,
        "expires_at": time.time() + expires_in,
    }
    if tokens.get("id_token"):
        updated["id_token"] = tokens["id_token"]
    return updated


def access_token(path: Path | None = None) -> str:
    """Load/renew the selected registration under a cross-process refresh lock."""
    path = path or credentials_path()
    if not path.is_file():
        message = "ChatGPT credentials are unavailable; run the ChatGPT login command"
        raise ChatGPTAuthError(message)
    with FileLock(str(path) + ".lock", mode=0o600, timeout=30):
        record = _read_credentials(path)
        if _PLAN_SCOPE not in record.get("scopes", []):
            message = "ChatGPT plan permission is missing"
            raise ChatGPTAuthError(message)
        if not record.get("client_id") or record["client_id"] == "dynamic_agent_client":
            message = "ChatGPT registration is missing its issued client ID"
            raise ChatGPTAuthError(message)
        if float(record.get("expires_at", 0)) <= time.time() + 60:
            tokens = token_request(
                {
                    "grant_type": "refresh_token",
                    "client_id": record["client_id"],
                    "refresh_token": record["refresh_token"],
                    "resource": _RESOURCE,
                }
            )
            record = _updated_tokens(record, tokens)
            save_credentials(path, record)
        token = record.get("access_token")
        if not isinstance(token, str) or not token:
            message = "ChatGPT credentials are missing an access token"
            raise ChatGPTAuthError(message)
        return token


def validate_callback(
    query: dict[str, list[str]], *, state: str, client_id: str
) -> tuple[str, str]:
    """Bind the callback to its transaction and retain the issued registration."""
    if query.get("state") != [state]:
        message = "ChatGPT callback state mismatch"
        raise ChatGPTAuthError(message)
    if query.get("error"):
        message = "ChatGPT authorization was denied"
        raise ChatGPTAuthError(message)
    issued = query.get("client_id", [client_id])[0]
    if issued == "dynamic_agent_client" or (client_id not in {"dynamic_agent_client", issued}):
        message = "ChatGPT callback is missing or changed the issued client ID"
        raise ChatGPTAuthError(message)
    code = query.get("code", [])
    if len(code) != 1 or not code[0]:
        message = "ChatGPT callback is missing its authorization code"
        raise ChatGPTAuthError(message)
    return code[0], issued


def _verified_identity(tokens: dict[str, Any], client_id: str, nonce: str) -> dict[str, Any]:
    import jwt

    try:
        discovery = httpx.get(f"{_ISSUER}/.well-known/openid-configuration", timeout=15)
        discovery.raise_for_status()
        configuration = discovery.json()
        jwks_uri = configuration["jwks_uri"]
        if (
            configuration.get("issuer") != _ISSUER
            or urlsplit(jwks_uri).hostname != "auth.openai.com"
            or not jwks_uri.startswith("https://")
        ):
            message = "Invalid OpenAI identity discovery document"
            raise ChatGPTAuthError(message)
        key = jwt.PyJWKClient(jwks_uri, timeout=15).get_signing_key_from_jwt(tokens["id_token"])
        claims = jwt.decode(
            tokens["id_token"],
            key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=_ISSUER,
            leeway=5,
            options={"require": ["sub", "exp", "iat", "nonce"]},
        )
    except (httpx.HTTPError, jwt.PyJWTError, KeyError, ValueError) as exc:
        message = "ChatGPT identity token validation failed"
        raise ChatGPTAuthError(message) from exc
    if not isinstance(claims.get("nonce"), str) or not secrets.compare_digest(
        claims["nonce"], nonce
    ):
        message = "ChatGPT identity nonce mismatch"
        raise ChatGPTAuthError(message)
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        message = "ChatGPT identity is missing its subject"
        raise ChatGPTAuthError(message)
    return claims


def _host_id(directory: Path) -> str:
    path = directory / "chatgpt-host.json"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(str(path) + ".lock", mode=0o600, timeout=30):
        if path.exists():
            return str(_read_credentials(path)["ext_agent_host_id"])
        host = f"urn:uuid:{uuid.uuid4()}"
        save_credentials(path, {"ext_agent_host_id": host})
        return host


def sign_in(path: Path, *, port: int = 1455) -> None:
    """Complete local loopback OAuth with PKCE and verified OpenID identity."""
    previous = _read_credentials(path) if path.exists() else {}
    client_id = previous.get("client_id", "dynamic_agent_client")
    host = _host_id(path.parent)
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    callback: dict[str, list[str]] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            accepted = parsed.path == "/auth/callback" and query.get("state") == [state]
            self.send_response(200 if accepted else 400)
            self.end_headers()
            self.wfile.write(
                b"Return to the News Dashboard terminal." if accepted else b"Invalid callback."
            )
            if accepted:
                callback.update(query)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - HTTPServer override
            """Suppress HTTP access logs containing OAuth codes."""

    with HTTPServer(("127.0.0.1", port), Handler) as server:
        server.timeout = 1
        redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
        params = {
            "client_id": client_id,
            "ext_agent_host_id": host,
            "response_type": "code",
            "redirect_uri": redirect,
            "scope": _SCOPES,
            "resource": _RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        if client_id == "dynamic_agent_client":
            params["agent_name_hint"] = "News Dashboard"
        url = f"{_ISSUER}/api/accounts/authorize?{urlencode(params)}"
        typer.echo("Continue with ChatGPT in your browser. If it does not open, visit:")
        typer.echo(url)
        webbrowser.open(url)
        deadline = time.monotonic() + 300
        while not callback and time.monotonic() < deadline:
            server.handle_request()
    if not callback:
        message = "ChatGPT sign-in timed out"
        raise ChatGPTAuthError(message)
    code, issued = validate_callback(callback, state=state, client_id=client_id)
    tokens = token_request(
        {
            "grant_type": "authorization_code",
            "client_id": issued,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect,
            "resource": _RESOURCE,
        }
    )
    claims = _verified_identity(tokens, issued, nonce)
    if previous and (
        previous.get("subject") != claims["sub"] or previous.get("issuer") != claims["iss"]
    ):
        message = "ChatGPT sign-in returned a different account; use a separate credential file"
        raise ChatGPTAuthError(message)
    record = _updated_tokens(
        {
            "client_id": issued,
            "issuer": claims["iss"],
            "subject": claims["sub"],
            "email": claims.get("email"),
            "ext_agent_host_id": host,
        },
        tokens,
    )
    with FileLock(str(path) + ".lock", mode=0o600, timeout=30):
        save_credentials(path, record)
    typer.echo(f"ChatGPT plan connected. Protected credentials saved to {path}.")


@app.command()
def login(
    credentials: Path | None = None,
    port: int = typer.Option(1455, min=1, max=65535),
) -> None:
    """Continue with ChatGPT; authorize this installation to use your plan."""
    sign_in(credentials or credentials_path(), port=port)


@app.command()
def models(credentials: Path | None = None) -> None:
    """List the selected account's current model catalog without exposing tokens."""
    response = httpx.get(
        f"{_RESOURCE}/models",
        headers={"Authorization": f"Bearer {access_token(credentials)}"},
        timeout=30,
    )
    response.raise_for_status()
    for model in response.json().get("models", []):
        if model.get("visibility") == "list":
            typer.echo(f"{model['slug']}  {model['display_name']}")


@app.command()
def logout(credentials: Path | None = None) -> None:
    """Revoke the renewable session and clear tokens; retain account/host identity."""
    path = credentials or credentials_path()
    with FileLock(str(path) + ".lock", mode=0o600, timeout=30):
        record = _read_credentials(path)
        response = httpx.get(f"{_ISSUER}/.well-known/openid-configuration", timeout=15)
        response.raise_for_status()
        endpoint = response.json()["revocation_endpoint"]
        if not endpoint.startswith(f"{_ISSUER}/"):
            message = "Invalid OpenAI revocation endpoint"
            raise ChatGPTAuthError(message)
        response = httpx.post(
            endpoint,
            data={
                "token": record["refresh_token"],
                "token_type_hint": "refresh_token",
                "client_id": record["client_id"],
            },
            timeout=30,
        )
        response.raise_for_status()
        for key in ("access_token", "refresh_token", "id_token", "scopes", "expires_at"):
            record.pop(key, None)
        save_credentials(path, record)
    typer.echo("ChatGPT session revoked and local tokens cleared.")


if __name__ == "__main__":
    try:
        app()
    except ChatGPTAuthError as exc:
        typer.echo(str(exc), err=True)
        raise SystemExit(1) from None
