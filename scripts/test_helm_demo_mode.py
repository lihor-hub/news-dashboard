# ruff: noqa: S101
"""Rendered-manifest contracts for the opt-in app.config.demoMode chart value."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "news-dashboard"
PRODUCTION_VALUES = CHART / "values-production.yaml"


def helm_template_command(*arguments: str) -> list[str]:
    """Return a `helm template` command with render-only secrets."""
    return [
        "helm",
        "template",
        "release",
        str(CHART),
        "--set-string",
        "app.auth.sessionSecret=render-only-session-secret",
        "--set-string",
        "postgresql.password=render-only-postgres-password",
        "--set-string",
        f"image.digest=sha256:{'a' * 64}",
        *arguments,
    ]


def app_env(*arguments: str) -> dict[str, object]:
    result = subprocess.run(  # noqa: S603
        helm_template_command(*arguments), check=True, capture_output=True, text=True
    )
    rendered = [document for document in yaml.safe_load_all(result.stdout) if document]
    deployment = next(resource for resource in rendered if resource["kind"] == "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    return {item["name"]: item.get("value") for item in container["env"]}


def test_demo_mode_renders_demo_mode_env() -> None:
    assert app_env("--set", "app.config.demoMode=true")["DEMO_MODE"] == "true"


def test_default_and_production_renders_keep_demo_mode_off() -> None:
    for arguments in ((), ("-f", str(PRODUCTION_VALUES))):
        assert "DEMO_MODE" not in app_env(*arguments)


def test_production_render_rejects_demo_mode() -> None:
    result = subprocess.run(  # noqa: S603 — offline Helm rendering
        helm_template_command("-f", str(PRODUCTION_VALUES), "--set", "app.config.demoMode=true"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "must not be set in production" in result.stderr
