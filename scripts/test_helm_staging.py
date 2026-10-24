# ruff: noqa: S101
"""Rendered-manifest contracts for the staging (PR preview backend) Helm values."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "news-dashboard"
STAGING_VALUES = CHART / "values-staging.yaml"
PRODUCTION_VALUES = CHART / "values-production.yaml"
STAGING_HOST = "stage.news.lihor.ro"


def render_chart(*arguments: str) -> list[dict[str, object]]:
    """Render the chart with the secrets needed only for manifest rendering."""
    command = [
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
    result = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def find_kind(rendered: list[dict[str, object]], kind: str) -> dict[str, object]:
    return next(resource for resource in rendered if resource["kind"] == kind)


def app_env(rendered: list[dict[str, object]]) -> dict[str, object]:
    deployment = find_kind(rendered, "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    return {item["name"]: item.get("value") for item in container["env"]}


def test_staging_ingress_serves_stage_host_over_tls() -> None:
    ingress = find_kind(render_chart("-f", str(STAGING_VALUES)), "Ingress")
    assert ingress["spec"]["ingressClassName"] == "traefik"
    assert ingress["spec"]["rules"][0]["host"] == STAGING_HOST
    assert ingress["spec"]["tls"] == [
        {"secretName": "news-dashboard-stage-tls", "hosts": [STAGING_HOST]}
    ]


def test_staging_runs_read_only_demo_with_local_auth() -> None:
    env = app_env(render_chart("-f", str(STAGING_VALUES)))
    assert env["DEMO_MODE"] == "true"
    assert env["APP_BASE_URL"] == f"https://{STAGING_HOST}"
    assert "KEYCLOAK_AUTH_ENABLED" not in env


def test_staging_trusts_only_this_projects_vercel_preview_origins() -> None:
    env = app_env(render_chart("-f", str(STAGING_VALUES)))
    pattern = env["CSRF_TRUSTED_ORIGIN_REGEX"]
    assert isinstance(pattern, str)
    assert pattern.startswith("https://news-dashboard-")
    assert pattern.endswith(r"\.vercel\.app")


def test_staging_postgres_never_mounts_a_host_path() -> None:
    rendered = render_chart("-f", str(STAGING_VALUES))
    statefulset = find_kind(rendered, "StatefulSet")
    volumes = statefulset["spec"]["template"]["spec"]["volumes"]
    assert all("hostPath" not in volume for volume in volumes)


def test_default_and_production_renders_keep_demo_and_preview_origins_off() -> None:
    for arguments in ((), ("-f", str(PRODUCTION_VALUES))):
        env = app_env(render_chart(*arguments))
        assert "DEMO_MODE" not in env
        assert "CSRF_TRUSTED_ORIGIN_REGEX" not in env
