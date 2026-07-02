import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

HELM_BIN = shutil.which("helm")
CHART_DIR = Path(__file__).resolve().parents[2] / "helm" / "news-dashboard"


def _render_chart(*set_values: str) -> str:
    assert HELM_BIN is not None
    args = [
        HELM_BIN,
        "template",
        "news-dashboard",
        str(CHART_DIR),
        "--set",
        "app.auth.sessionSecret=dummy-session-secret",
        "--set-string",
        "postgresql.password=dummy-postgres-password-for-render-only",
    ]
    for value in set_values:
        args.extend(("--set", value))

    res = subprocess.run(  # noqa: S603
        args,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"helm template failed: {res.stderr}"
    return res.stdout


def _manifest_for_kind(output: str, kind: str) -> str:
    for manifest in output.split("---"):
        if f"\nkind: {kind}\n" in f"\n{manifest}\n":
            return manifest
    msg = f"Rendered chart did not include {kind}"
    raise AssertionError(msg)


def _env_block(manifest: str) -> str:
    lines = manifest.splitlines()
    env_index = next(index for index, line in enumerate(lines) if line.strip() == "env:")
    env_indent = len(lines[env_index]) - len(lines[env_index].lstrip())
    block: list[str] = []
    for line in lines[env_index + 1 :]:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped and indent <= env_indent:
            break
        block.append(line)
    return "\n".join(block)


def _env_entry(env: str, name: str) -> str:
    lines = env.splitlines()
    needle = f"- name: {name}"
    start = next(index for index, line in enumerate(lines) if line.strip() == needle)
    entry_indent = len(lines[start]) - len(lines[start].lstrip())
    entry: list[str] = [lines[start]]
    for line in lines[start + 1 :]:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("- name: ") and indent == entry_indent:
            break
        entry.append(line)
    return textwrap.dedent("\n".join(entry))


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_default() -> None:
    output = _render_chart()
    assert "NEWS_DASHBOARD_DB" not in output
    # Check that it renders standard postgres config
    assert "name: POSTGRES_HOST" in output
    assert 'value: "news-dashboard-news-dashboard-postgres"' in output
    assert "concurrencyPolicy: Forbid" in output
    assert "startingDeadlineSeconds: 1800" in output
    assert "activeDeadlineSeconds: 3600" in output
    assert "backoffLimit: 1" in output
    assert "successfulJobsHistoryLimit: 2" in output
    assert "failedJobsHistoryLimit: 3" in output


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_ingest_cronjob_operational_overrides() -> None:
    output = _render_chart(
        "ingestCronJob.concurrencyPolicy=Replace",
        "ingestCronJob.startingDeadlineSeconds=900",
        "ingestCronJob.activeDeadlineSeconds=1200",
        "ingestCronJob.backoffLimit=2",
        "ingestCronJob.ttlSecondsAfterFinished=86400",
    )
    assert "concurrencyPolicy: Replace" in output
    assert "startingDeadlineSeconds: 900" in output
    assert "activeDeadlineSeconds: 1200" in output
    assert "backoffLimit: 2" in output
    assert "ttlSecondsAfterFinished: 86400" in output


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_ingest_cronjob_receives_ai_env() -> None:
    output = _render_chart(
        "app.ai.existingSecret=ai-credentials",
        "app.ai.openaiApiKeyKey=CUSTOM_OPENAI_API_KEY",
        "app.ai.freeLlmApiKeyKey=CUSTOM_FREE_LLM_API_KEY",
        "app.ai.freeLlmBaseUrl=https://llm.example.test/v1",
        "app.ai.briefingModel=briefing-model",
        "app.ai.langfuse.host=https://langfuse.example.test",
        "app.ai.langfuse.publicKeyKey=CUSTOM_LANGFUSE_PUBLIC_KEY",
        "app.ai.langfuse.secretKeyKey=CUSTOM_LANGFUSE_SECRET_KEY",
    )
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))
    cronjob_env = _env_block(_manifest_for_kind(output, "CronJob"))

    ai_env_names = [
        "OPENAI_API_KEY",
        "FREE_LLM_API_KEY",
        "FREE_LLM_BASE_URL",
        "OPENAI_BRIEFING_MODEL",
        "LANGFUSE_HOST",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ]
    for name in ai_env_names:
        assert _env_entry(cronjob_env, name) == _env_entry(deployment_env, name)


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_app_and_ingest_receive_sentry_env() -> None:
    output = _render_chart(
        "app.sentry.existingSecret=sentry-credentials",
        "app.sentry.dsnKey=CUSTOM_SENTRY_DSN",
        "app.sentry.frontendDsnKey=CUSTOM_SENTRY_DSN_FRONTEND",
        "app.sentry.environment=production",
        "app.sentry.release=news-dashboard@abc123",
    )
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))
    cronjob_env = _env_block(_manifest_for_kind(output, "CronJob"))

    for name in ("SENTRY_DSN", "SENTRY_ENVIRONMENT", "SENTRY_RELEASE"):
        assert _env_entry(cronjob_env, name) == _env_entry(deployment_env, name)

    sentry_dsn = _env_entry(deployment_env, "SENTRY_DSN")
    assert 'name: "sentry-credentials"' in sentry_dsn
    assert 'key: "CUSTOM_SENTRY_DSN"' in sentry_dsn
    frontend_sentry_dsn = _env_entry(deployment_env, "SENTRY_DSN_FRONTEND")
    assert 'name: "sentry-credentials"' in frontend_sentry_dsn
    assert 'key: "CUSTOM_SENTRY_DSN_FRONTEND"' in frontend_sentry_dsn
    assert _env_entry(deployment_env, "SENTRY_ENVIRONMENT") == (
        '- name: SENTRY_ENVIRONMENT\n  value: "production"'
    )
    assert _env_entry(deployment_env, "SENTRY_RELEASE") == (
        '- name: SENTRY_RELEASE\n  value: "news-dashboard@abc123"'
    )


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_external_postgres() -> None:
    output = _render_chart(
        "postgresql.enabled=false",
        "app.postgresExternal.host=ext-postgres.internal",
        "app.postgresExternal.database=ext_db",
        "app.postgresExternal.username=ext_user",
    )
    assert "NEWS_DASHBOARD_DB" not in output
    assert "name: POSTGRES_HOST" in output
    assert 'value: "ext-postgres.internal"' in output
    assert "name: POSTGRES_DB" in output
    assert 'value: "ext_db"' in output
    assert "name: POSTGRES_USER" in output
    assert 'value: "ext_user"' in output


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_external_database_url() -> None:
    output = _render_chart(
        "postgresql.enabled=false",
        "app.databaseUrl.existingSecret=my-db-secret",
    )
    assert "NEWS_DASHBOARD_DB" not in output
    assert "name: DATABASE_URL" in output
    assert 'name: "my-db-secret"' in output


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


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_fails_without_bundled_postgres_password() -> None:
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
    assert res.returncode != 0
    assert "postgresql.password is required when postgresql.enabled=true" in res.stderr


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_fails_with_empty_bundled_postgres_password() -> None:
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
            "postgresql.password=",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    assert "postgresql.password is required when postgresql.enabled=true" in res.stderr
