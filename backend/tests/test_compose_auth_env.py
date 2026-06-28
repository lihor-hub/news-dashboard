"""Verify that docker-compose.yml supplies auth env vars for local dev (issue #478).

A fresh ``docker compose up --build`` must be login-ready: the app service must
have SESSION_SECRET, BOOTSTRAP_ADMIN_USERNAME, and BOOTSTRAP_ADMIN_PASSWORD
either as explicit values or as ${VAR:-default} expressions with a non-empty
default, so a first-time user can log in without extra setup.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).parent.parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

_REQUIRED_AUTH_VARS = {
    "SESSION_SECRET",
    "BOOTSTRAP_ADMIN_USERNAME",
    "BOOTSTRAP_ADMIN_PASSWORD",
}

_COMPOSE_OVERRIDE_PATTERN = re.compile(r"^\$\{[A-Z_]+:-(.+)\}$")


def _resolve_default(value: object) -> str:
    """Return the effective default for a compose env value.

    - A plain string with no substitution is returned as-is.
    - A ``${VAR:-default}`` expression returns the default part.
    - Anything else (None, empty string) returns an empty string.
    """
    if not isinstance(value, str):
        return ""
    m = _COMPOSE_OVERRIDE_PATTERN.match(value.strip())
    if m:
        return m.group(1)
    return value


def test_compose_file_exists() -> None:
    assert COMPOSE_FILE.exists(), f"docker-compose.yml not found at {COMPOSE_FILE}"


def test_compose_app_service_has_auth_env_vars() -> None:
    """The news-dashboard service must declare all three auth env vars with defaults."""
    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    services = compose.get("services", {})
    assert "news-dashboard" in services, "news-dashboard service missing from compose"

    env = services["news-dashboard"].get("environment", {})
    if isinstance(env, list):
        env = dict(item.split("=", 1) if "=" in item else (item, "") for item in env)

    missing: list[str] = []
    empty: list[str] = []
    for var in sorted(_REQUIRED_AUTH_VARS):
        if var not in env:
            missing.append(var)
        elif not _resolve_default(env[var]):
            empty.append(var)

    assert not missing, f"Auth env vars not declared in compose: {missing}"
    assert not empty, f"Auth env vars have no default value in compose: {empty}"
