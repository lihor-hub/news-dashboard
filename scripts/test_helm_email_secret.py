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


def test_otp_smtp_generic_env_absent_by_default() -> None:
    rendered = _helm_template([])
    assert "OTP_SMTP_HOST" not in rendered
    assert "OTP_SMTP_PORT" not in rendered
    assert "OTP_SMTP_FROM" not in rendered
    assert "OTP_SMTP_TLS" not in rendered


def test_otp_smtp_generic_env_wired_from_values() -> None:
    rendered = _helm_template(
        [
            "--set",
            "app.email.smtpHost=smtp.example.net",
            "--set-string",
            "app.email.smtpPort=2525",
            "--set",
            "app.email.smtpFrom=noreply@example.net",
            "--set",
            "app.email.smtpTlsMode=starttls",
        ]
    )
    assert "OTP_SMTP_HOST" in rendered
    assert "smtp.example.net" in rendered
    assert "OTP_SMTP_PORT" in rendered
    assert '"2525"' in rendered
    assert "OTP_SMTP_FROM" in rendered
    assert "noreply@example.net" in rendered
    assert "OTP_SMTP_TLS" in rendered
    assert "starttls" in rendered
