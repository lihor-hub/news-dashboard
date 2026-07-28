"""Verify Compose forwards the optional Dify chat runtime configuration."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).parent.parent.parent
COMPOSE_FILES = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "docker-compose.prod.yml",
)

_DIFY_ENV_DEFAULTS = {
    "DIFY_CHAT_ENABLED": "${DIFY_CHAT_ENABLED:-false}",
    "DIFY_CHAT_BASE_URL": "${DIFY_CHAT_BASE_URL:-}",
    "DIFY_CHAT_APP_TOKEN": "${DIFY_CHAT_APP_TOKEN:-}",
    "DIFY_CHAT_TITLE": "${DIFY_CHAT_TITLE:-News Assistant}",
}


def _compose_environment(compose_file: Path) -> dict[str, object]:
    compose = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = compose.get("services", {})
    assert "news-dashboard" in services, f"news-dashboard service missing from {compose_file.name}"
    environment = services["news-dashboard"].get("environment", {})
    assert isinstance(environment, dict), f"environment in {compose_file.name} must be a mapping"
    return cast("dict[str, object]", environment)


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_compose_forwards_dify_chat_configuration_with_disabled_default(
    compose_file: Path,
) -> None:
    environment = _compose_environment(compose_file)

    for name, value in _DIFY_ENV_DEFAULTS.items():
        assert environment.get(name) == value
    assert "DIFY_API_KEY" not in environment
