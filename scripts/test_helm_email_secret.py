# ruff: noqa: S101
"""Chart render tests for wiring SMTP_USERNAME/SMTP_PASSWORD via app.email."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "helm" / "news-dashboard"


def _helm_template(extra_sets: list[str]) -> str:
    cmd = [
        "helm",
        "template",
        "test-release",
        str(CHART),
        "--set",
        "app.auth.sessionSecret=dummy-secret-for-test",
        "--set-string",
        "postgresql.password=dummy-postgres-password-for-render-only",
        *extra_sets,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603
    return result.stdout


def test_email_env_absent_by_default() -> None:
    rendered = _helm_template([])
    assert "SMTP_USERNAME" not in rendered
    assert "SMTP_PASSWORD" not in rendered


def test_email_env_wired_from_existing_secret() -> None:
    rendered = _helm_template(["--set", "app.email.existingSecret=news-dashboard-email"])
    assert "SMTP_USERNAME" in rendered
    assert "SMTP_PASSWORD" in rendered
    assert "news-dashboard-email" in rendered
