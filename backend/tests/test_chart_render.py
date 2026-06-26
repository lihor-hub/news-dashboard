import shutil
import subprocess
from pathlib import Path

import pytest

HELM_BIN = shutil.which("helm")
CHART_DIR = Path(__file__).resolve().parents[2] / "helm" / "news-dashboard"


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_default() -> None:
    assert HELM_BIN is not None
    res = subprocess.run(  # noqa: S603
        [
            HELM_BIN,
            "template",
            "news-dashboard",
            str(CHART_DIR),
            "--set",
            "app.auth.sessionSecret=dummy-session-secret",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"helm template failed: {res.stderr}"
    output = res.stdout
    assert "NEWS_DASHBOARD_DB" not in output
    # Check that it renders standard postgres config
    assert "name: POSTGRES_HOST" in output
    assert "value: news-dashboard-postgres" in output


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_external_postgres() -> None:
    assert HELM_BIN is not None
    res = subprocess.run(  # noqa: S603
        [
            HELM_BIN,
            "template",
            "news-dashboard",
            str(CHART_DIR),
            "--set",
            "app.auth.sessionSecret=dummy-session-secret",
            "--set",
            "postgresql.enabled=false",
            "--set",
            "app.postgresExternal.host=ext-postgres.internal",
            "--set",
            "app.postgresExternal.database=ext_db",
            "--set",
            "app.postgresExternal.username=ext_user",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"helm template failed: {res.stderr}"
    output = res.stdout
    assert "NEWS_DASHBOARD_DB" not in output
    assert "name: POSTGRES_HOST" in output
    assert 'value: "ext-postgres.internal"' in output
    assert "name: POSTGRES_DB" in output
    assert 'value: "ext_db"' in output
    assert "name: POSTGRES_USER" in output
    assert 'value: "ext_user"' in output


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_external_database_url() -> None:
    assert HELM_BIN is not None
    res = subprocess.run(  # noqa: S603
        [
            HELM_BIN,
            "template",
            "news-dashboard",
            str(CHART_DIR),
            "--set",
            "app.auth.sessionSecret=dummy-session-secret",
            "--set",
            "postgresql.enabled=false",
            "--set",
            "app.databaseUrl.existingSecret=my-db-secret",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"helm template failed: {res.stderr}"
    output = res.stdout
    assert "NEWS_DASHBOARD_DB" not in output
    assert "name: DATABASE_URL" in output
    assert "name: my-db-secret" in output


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_fails_without_postgres_config() -> None:
    assert HELM_BIN is not None
    res = subprocess.run(  # noqa: S603
        [
            HELM_BIN,
            "template",
            "news-dashboard",
            str(CHART_DIR),
            "--set",
            "app.auth.sessionSecret=dummy-session-secret",
            "--set",
            "postgresql.enabled=false",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    assert (
        "External PostgreSQL configuration is required when postgresql.enabled=false" in res.stderr
    )
