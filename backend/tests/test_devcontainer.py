"""Development-container isolation and lifecycle contracts (runtime verified in CI)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]  # PyYAML ships no inline typing.

ROOT = Path(__file__).resolve().parents[2]


def test_devcontainer_isolates_interpreter_and_frontend_dependencies() -> None:
    compose = yaml.safe_load(
        (ROOT / ".devcontainer/docker-compose.yml").read_text(encoding="utf-8")
    )
    app = compose["services"]["app"]
    assert "devcontainer-venv:/workspace/.venv" in app["volumes"]
    assert "devcontainer-node-modules:/workspace/node_modules" in app["volumes"]
    assert "ports" not in compose["services"]["db"]
    assert app["depends_on"]["db"]["condition"] == "service_healthy"


def test_devcontainer_rebuild_recovers_stale_venv_without_touching_host() -> None:
    config = json.loads((ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8"))
    script = ROOT / ".devcontainer/post-create.sh"
    assert config["postCreateCommand"] == "bash .devcontainer/post-create.sh"
    content = script.read_text(encoding="utf-8")
    assert content.index("mountpoint -q .venv") < content.index("venv --clear .venv")
    assert "/usr/local/bin/python -m venv --clear .venv" in content
    assert "--hook-type pre-push" in content
    assert config["remoteUser"] == "vscode"
    assert config["customizations"]["vscode"]["settings"]["python.defaultInterpreterPath"] == (
        "/workspace/.venv/bin/python"
    )
    compose = yaml.safe_load(
        (ROOT / ".devcontainer/docker-compose.yml").read_text(encoding="utf-8")
    )
    assert compose["services"]["app"]["environment"]["PGOPTIONS"] == (
        "-c max_parallel_workers_per_gather=0"
    )
    assert config["features"]["ghcr.io/devcontainers/features/node:1"]["version"] == "26"
