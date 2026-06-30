# ruff: noqa: S101
"""Chart render tests for the postgresql.backup CronJob."""

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


def test_backup_disabled_by_default() -> None:
    rendered = _helm_template([])
    assert "postgres-backup" not in rendered


def test_backup_disabled_explicitly() -> None:
    rendered = _helm_template(["--set", "postgresql.backup.enabled=false"])
    assert "postgres-backup" not in rendered


def test_backup_enabled_renders_cronjob() -> None:
    rendered = _helm_template(
        [
            "--set",
            "postgresql.backup.enabled=true",
            "--set",
            "postgresql.backup.hostPath=/mnt/backups",
        ]
    )
    assert "kind: CronJob" in rendered
    assert "postgres-backup" in rendered


def test_backup_uses_postgres_secret() -> None:
    rendered = _helm_template(
        [
            "--set",
            "postgresql.backup.enabled=true",
            "--set",
            "postgresql.backup.hostPath=/mnt/backups",
        ]
    )
    assert "POSTGRES_DB" in rendered
    assert "POSTGRES_USER" in rendered
    assert "POSTGRES_PASSWORD" in rendered
    assert "PGPASSWORD" in rendered


def test_backup_mounts_separate_volume() -> None:
    rendered = _helm_template(
        [
            "--set",
            "postgresql.backup.enabled=true",
            "--set",
            "postgresql.backup.hostPath=/mnt/backups",
        ]
    )
    assert "/mnt/backups" in rendered
    assert "postgres-backups" in rendered
    # Backup path must not overlap with live data directory
    assert "news-dashboard-postgres-data" not in rendered.split("postgres-backup")[1]


def test_backup_default_schedule() -> None:
    rendered = _helm_template(
        [
            "--set",
            "postgresql.backup.enabled=true",
            "--set",
            "postgresql.backup.hostPath=/mnt/backups",
        ]
    )
    assert "0 2 * * *" in rendered


def test_backup_custom_schedule() -> None:
    rendered = _helm_template(
        [
            "--set",
            "postgresql.backup.enabled=true",
            "--set",
            "postgresql.backup.hostPath=/mnt/backups",
            "--set",
            "postgresql.backup.schedule=30 3 * * 0",
        ]
    )
    assert "30 3 * * 0" in rendered


def test_backup_retention_days_in_command() -> None:
    rendered = _helm_template(
        [
            "--set",
            "postgresql.backup.enabled=true",
            "--set",
            "postgresql.backup.hostPath=/mnt/backups",
            "--set",
            "postgresql.backup.retentionDays=14",
        ]
    )
    assert "14" in rendered


def test_backup_pg_dump_custom_format() -> None:
    rendered = _helm_template(
        [
            "--set",
            "postgresql.backup.enabled=true",
            "--set",
            "postgresql.backup.hostPath=/mnt/backups",
        ]
    )
    assert "pg_dump -Fc" in rendered
