"""Verify that docker-compose.yml supplies auth env vars for local dev (issue #478).

A fresh ``docker compose up --build`` must be login-ready: the app service must
have SESSION_SECRET, BOOTSTRAP_ADMIN_USERNAME, and BOOTSTRAP_ADMIN_PASSWORD
either as explicit values or as ${VAR:-default} expressions with a non-empty
default, so a first-time user can log in without extra setup.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import pytest
import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).parent.parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
COMPOSE_PROD_FILE = REPO_ROOT / "docker-compose.prod.yml"
COMPOSE_DEMO_FILE = REPO_ROOT / "docker-compose.demo.yml"

_REQUIRED_AUTH_VARS = {
    "SESSION_SECRET",
    "BOOTSTRAP_ADMIN_USERNAME",
    "BOOTSTRAP_ADMIN_PASSWORD",
}

_REQUIRED_GRAPH_VARS = {
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
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


def test_compose_prod_file_exists() -> None:
    assert COMPOSE_PROD_FILE.exists(), f"docker-compose.prod.yml not found at {COMPOSE_PROD_FILE}"


def test_compose_prod_persists_app_data_dir() -> None:
    """Production compose must persist generated audio and other app data."""
    compose = yaml.safe_load(COMPOSE_PROD_FILE.read_text())
    services = compose.get("services", {})
    assert "news-dashboard" in services, "news-dashboard service missing from prod compose"

    app_service = services["news-dashboard"]
    env = app_service.get("environment", {})
    if isinstance(env, list):
        env = dict(item.split("=", 1) if "=" in item else (item, "") for item in env)

    assert env.get("DATA_DIR") == "/data", "prod compose must set DATA_DIR=/data"
    assert "news-dashboard-data" in compose.get("volumes", {}), (
        "prod compose must declare news-dashboard-data volume"
    )
    assert "news-dashboard-data:/data" in app_service.get("volumes", []), (
        "prod compose must mount news-dashboard-data at /data"
    )


def _compose_env_map(compose_path: Path) -> dict[str, object]:
    compose = yaml.safe_load(compose_path.read_text())
    services = compose.get("services", {})
    assert "news-dashboard" in services, f"news-dashboard service missing from {compose_path.name}"
    env = services["news-dashboard"].get("environment", {})
    if isinstance(env, list):
        env = dict(item.split("=", 1) if "=" in item else (item, "") for item in env)
    assert isinstance(env, dict), f"environment in {compose_path.name} must be a mapping or list"
    return cast("dict[str, object]", env)


def test_compose_file_enables_neo4j_for_app() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    services = compose.get("services", {})

    assert "neo4j" in services, "neo4j service missing from local compose"
    env = _compose_env_map(COMPOSE_FILE)
    missing = _REQUIRED_GRAPH_VARS - set(env)
    assert not missing, f"Neo4j env vars not declared in local compose: {sorted(missing)}"
    assert env["NEO4J_URI"] == "bolt://neo4j:7687"
    assert env["NEO4J_USER"] == "neo4j"
    assert _resolve_default(env["NEO4J_PASSWORD"]), "NEO4J_PASSWORD must have a local default"
    assert env["NEO4J_DATABASE"] == "neo4j"


def test_compose_prod_file_enables_neo4j_for_app() -> None:
    compose = yaml.safe_load(COMPOSE_PROD_FILE.read_text())
    services = compose.get("services", {})

    assert "neo4j" in services, "neo4j service missing from prod compose"
    env = _compose_env_map(COMPOSE_PROD_FILE)
    missing = _REQUIRED_GRAPH_VARS - set(env)
    assert not missing, f"Neo4j env vars not declared in prod compose: {sorted(missing)}"
    assert env["NEO4J_URI"] == "bolt://neo4j:7687"
    assert env["NEO4J_USER"] == "neo4j"
    neo4j_password = str(env["NEO4J_PASSWORD"])
    assert neo4j_password.startswith("${NEO4J_")
    assert neo4j_password.endswith(" is required}")
    assert env["NEO4J_DATABASE"] == "neo4j"


def test_compose_demo_file_exists() -> None:
    assert COMPOSE_DEMO_FILE.exists(), f"docker-compose.demo.yml not found at {COMPOSE_DEMO_FILE}"


def test_compose_demo_app_service_has_demo_mode_and_session_secret() -> None:
    """The demo compose file must enable DEMO_MODE and supply SESSION_SECRET."""
    compose = yaml.safe_load(COMPOSE_DEMO_FILE.read_text())
    services = compose.get("services", {})
    assert "news-dashboard" in services, "news-dashboard service missing from demo compose"

    env = services["news-dashboard"].get("environment", {})
    if isinstance(env, list):
        env = dict(item.split("=", 1) if "=" in item else (item, "") for item in env)

    assert _resolve_default(env.get("DEMO_MODE")) in ("1", "true", "yes", "on"), (
        "DEMO_MODE must be enabled in docker-compose.demo.yml"
    )
    assert _resolve_default(env.get("SESSION_SECRET")), (
        "SESSION_SECRET must have a value in docker-compose.demo.yml"
    )


def _assert_app_healthcheck_uses_no_extra_tools(compose_file: Path) -> None:
    """The news-dashboard service healthcheck must not rely on curl/wget.

    The production image (python:3.14-slim) does not install curl or wget, so
    the healthcheck must use the Python standard library to probe /api/ready.
    """
    compose = yaml.safe_load(compose_file.read_text())
    services = compose.get("services", {})
    assert "news-dashboard" in services, "news-dashboard service missing from compose"

    healthcheck = services["news-dashboard"].get("healthcheck")
    assert healthcheck is not None, (
        f"news-dashboard service in {compose_file.name} has no healthcheck"
    )

    test = healthcheck.get("test")
    assert isinstance(test, list), f"healthcheck.test in {compose_file.name} must be a list"
    assert test, f"healthcheck.test in {compose_file.name} must be non-empty"
    assert test[0] == "CMD", (
        f"healthcheck.test in {compose_file.name} must use exec form (CMD), not CMD-SHELL"
    )

    command = " ".join(test)
    assert "curl" not in command, f"healthcheck in {compose_file.name} must not depend on curl"
    assert "wget" not in command, f"healthcheck in {compose_file.name} must not depend on wget"
    assert "/api/ready" in command, f"healthcheck in {compose_file.name} must probe /api/ready"
    assert "127.0.0.1" in command, (
        f"healthcheck in {compose_file.name} must probe the local container"
    )

    for field in ("interval", "timeout", "retries", "start_period"):
        assert field in healthcheck, f"healthcheck in {compose_file.name} is missing '{field}'"


def test_compose_app_healthcheck_configured() -> None:
    _assert_app_healthcheck_uses_no_extra_tools(COMPOSE_FILE)


def test_compose_prod_app_healthcheck_configured() -> None:
    _assert_app_healthcheck_uses_no_extra_tools(COMPOSE_PROD_FILE)


def test_compose_demo_app_healthcheck_configured() -> None:
    _assert_app_healthcheck_uses_no_extra_tools(COMPOSE_DEMO_FILE)


@pytest.mark.parametrize("compose_file", [COMPOSE_FILE, COMPOSE_PROD_FILE, COMPOSE_DEMO_FILE])
def test_compose_mcp_is_default_enabled_on_existing_app_listener(compose_file: Path) -> None:
    compose = yaml.safe_load(compose_file.read_text())
    app = compose["services"]["news-dashboard"]
    environment = app["environment"]

    assert environment["MCP_SERVER_ENABLED"] == "${MCP_SERVER_ENABLED:-true}"
    assert environment["MCP_ALLOWED_HOSTS"] == (
        "${MCP_ALLOWED_HOSTS:-localhost:8080,127.0.0.1:8080,[::1]:8080}"
    )
    assert environment["MCP_ALLOWED_ORIGINS"] == (
        "${MCP_ALLOWED_ORIGINS:-http://localhost:8080,http://127.0.0.1:8080,http://[::1]:8080}"
    )
    assert list(app["ports"]) == ["8080:8080"]
    assert "mcp" not in compose["services"]
