# ruff: noqa: S101
"""Chart render tests for wiring SMTP delivery configuration via app.email."""

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
    assert "- name: SMTP_USER\n" not in rendered
    assert "- name: SMTP_PASS\n" not in rendered
    assert "- name: SMTP_USERNAME\n" not in rendered
    assert "- name: SMTP_PASSWORD\n" not in rendered


def test_email_env_wired_from_existing_secret() -> None:
    rendered = _helm_template(["--set", "app.email.existingSecret=news-dashboard-email"])
    assert "- name: SMTP_USER\n" in rendered
    assert "- name: SMTP_PASS\n" in rendered
    assert "- name: SMTP_USERNAME\n" in rendered
    assert "- name: SMTP_PASSWORD\n" in rendered
    assert "news-dashboard-email" in rendered
    assert rendered.count('key: "SMTP_USERNAME"') == 2
    assert rendered.count('key: "SMTP_PASSWORD"') == 2


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
    assert "- name: SMTP_HOST\n" in rendered
    assert "- name: OTP_SMTP_HOST\n" in rendered
    assert 'value: "smtp.example.net"' in rendered
    assert "- name: SMTP_PORT\n" in rendered
    assert "- name: OTP_SMTP_PORT\n" in rendered
    assert 'value: "2525"' in rendered
    assert "- name: SMTP_FROM\n" in rendered
    assert "- name: OTP_SMTP_FROM\n" in rendered
    assert 'value: "noreply@example.net"' in rendered
    assert "- name: SMTP_TLS\n" in rendered
    assert "- name: OTP_SMTP_TLS\n" in rendered
    assert 'value: "starttls"' in rendered


def test_public_base_url_is_independent_of_keycloak() -> None:
    rendered = _helm_template(
        [
            "--set",
            "app.auth.keycloak.enabled=false",
            "--set",
            "app.publicBaseUrl=https://news.example.net",
        ]
    )
    assert "APP_BASE_URL" in rendered
    assert 'value: "https://news.example.net"' in rendered
    assert "NEWS_DASHBOARD_BASE_URL" not in rendered
    assert "KEYCLOAK_SERVER_URL" not in rendered
