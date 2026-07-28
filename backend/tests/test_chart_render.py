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


def _manifest_for_kind_and_name(output: str, kind: str, name: str) -> str:
    for manifest in output.split("---"):
        normalized = f"\n{manifest}\n"
        if f"\nkind: {kind}\n" in normalized and f"\n  name: {name}\n" in normalized:
            return manifest
    msg = f"Rendered chart did not include {kind}/{name}"
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
    assert "NEO4J_URI" not in output
    assert "news-dashboard-news-dashboard-neo4j" not in output
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
def test_helm_template_dify_chat_is_disabled_by_default() -> None:
    output = _render_chart()
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    assert "DIFY_CHAT_ENABLED" not in deployment_env
    assert "DIFY_CHAT_BASE_URL" not in deployment_env
    assert "DIFY_CHAT_APP_TOKEN" not in deployment_env
    assert "DIFY_CHAT_TITLE" not in deployment_env


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_enabled_dify_chat_uses_existing_secret() -> None:
    output = _render_chart(
        "app.dify.enabled=true",
        "app.dify.baseUrl=https://dify.example.test",
        "app.dify.title=Research Assistant",
        "app.dify.existingSecret=dify-chat-credentials",
        "app.dify.appTokenKey=CUSTOM_DIFY_APP_TOKEN",
    )
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    assert _env_entry(deployment_env, "DIFY_CHAT_ENABLED") == (
        '- name: DIFY_CHAT_ENABLED\n  value: "true"'
    )
    assert _env_entry(deployment_env, "DIFY_CHAT_BASE_URL") == (
        '- name: DIFY_CHAT_BASE_URL\n  value: "https://dify.example.test"'
    )
    assert _env_entry(deployment_env, "DIFY_CHAT_TITLE").rstrip() == (
        '- name: DIFY_CHAT_TITLE\n  value: "Research Assistant"'
    )
    app_token = _env_entry(deployment_env, "DIFY_CHAT_APP_TOKEN")
    assert 'name: "dify-chat-credentials"' in app_token
    assert 'key: "CUSTOM_DIFY_APP_TOKEN"' in app_token
    assert "DIFY_API_KEY" not in deployment_env


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
@pytest.mark.parametrize(
    ("set_value", "error"),
    [
        ("app.dify.enabled=true", "app.dify.baseUrl is required when app.dify.enabled=true"),
        (
            "app.dify.enabled=true,app.dify.baseUrl=https://dify.example.test",
            "app.dify.existingSecret is required when app.dify.enabled=true",
        ),
    ],
)
def test_helm_template_enabled_dify_chat_requires_complete_configuration(
    set_value: str, error: str
) -> None:
    assert HELM_BIN is not None
    res = subprocess.run(  # noqa: S603
        [
            HELM_BIN,
            "template",
            "news-dashboard",
            str(CHART_DIR),
            "--set",
            "app.auth.sessionSecret=dummy-session-secret",
            "--set-string",
            "postgresql.password=dummy-postgres-password-for-render-only",
            "--set",
            set_value,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert res.returncode != 0
    assert error in res.stderr


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_neo4j_can_use_existing_secret_and_claim() -> None:
    output = _render_chart(
        "neo4j.enabled=true",
        "neo4j.auth.existingSecret=graph-secret",
        "neo4j.auth.passwordKey=GRAPH_PASSWORD",
        "neo4j.persistence.enabled=true",
        "neo4j.persistence.existingClaim=graph-data",
    )
    deployment = _manifest_for_kind(output, "Deployment")
    deployment_env = _env_block(deployment)
    statefulset = _manifest_for_kind_and_name(
        output,
        "StatefulSet",
        "news-dashboard-news-dashboard-neo4j",
    )

    assert 'claimName: "graph-data"' in statefulset
    assert "stringData:\n  NEO4J_USER" not in output
    assert 'name: "graph-secret"' in _env_entry(deployment_env, "NEO4J_PASSWORD")
    assert 'key: "GRAPH_PASSWORD"' in _env_entry(deployment_env, "NEO4J_PASSWORD")


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_neo4j_disabled_by_default() -> None:
    output = _render_chart()
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    assert "-neo4j" not in output
    assert "NEO4J_URI" not in deployment_env
    assert "NEO4J_USER" not in deployment_env
    assert "NEO4J_PASSWORD" not in deployment_env
    assert "NEO4J_DATABASE" not in deployment_env


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_neo4j_enabled_renders_graph_service_and_app_env() -> None:
    output = _render_chart(
        "neo4j.enabled=true",
        "neo4j.image.repository=neo4j",
        "neo4j.image.tag=5-community",
        "neo4j.image.pullPolicy=Always",
        "neo4j.auth.user=graph_user",
        "neo4j.auth.password=dummy-neo4j-password-for-render-only",
        "neo4j.auth.passwordKey=GRAPH_PASSWORD",
        "neo4j.service.port=17687",
        "neo4j.persistence.size=8Gi",
        "neo4j.persistence.storageClassName=fast-storage",
        "neo4j.resources.requests.cpu=100m",
        "neo4j.resources.limits.memory=1Gi",
    )

    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))
    service = _manifest_for_kind_and_name(
        output,
        "Service",
        "news-dashboard-news-dashboard-neo4j",
    )
    statefulset = _manifest_for_kind_and_name(
        output,
        "StatefulSet",
        "news-dashboard-news-dashboard-neo4j",
    )
    secret = _manifest_for_kind_and_name(
        output,
        "Secret",
        "news-dashboard-news-dashboard-neo4j",
    )
    pvc = _manifest_for_kind_and_name(
        output,
        "PersistentVolumeClaim",
        "news-dashboard-news-dashboard-neo4j",
    )

    assert "port: 17687" in service
    assert "targetPort: bolt" in service
    assert 'image: "neo4j:5-community"' in statefulset
    assert "imagePullPolicy: Always" in statefulset
    assert "name: bolt" in statefulset
    assert "containerPort: 17687" in statefulset
    assert "GRAPH_PASSWORD:" in secret
    assert "NEO4J_AUTH:" in secret
    assert "storage: 8Gi" in pvc
    assert 'storageClassName: "fast-storage"' in pvc
    assert "cpu: 100m" in statefulset
    assert "memory: 1Gi" in statefulset

    assert _env_entry(deployment_env, "NEO4J_URI") == (
        '- name: NEO4J_URI\n  value: "bolt://news-dashboard-news-dashboard-neo4j:17687"'
    )
    assert _env_entry(deployment_env, "NEO4J_USER") == ('- name: NEO4J_USER\n  value: "graph_user"')
    neo4j_password = _env_entry(deployment_env, "NEO4J_PASSWORD")
    assert 'name: "news-dashboard-news-dashboard-neo4j"' in neo4j_password
    assert 'key: "GRAPH_PASSWORD"' in neo4j_password
    assert _env_entry(deployment_env, "NEO4J_DATABASE") == (
        '- name: NEO4J_DATABASE\n  value: "neo4j"'
    )


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_keycloak_auth_mode_injects_session_secret_and_keycloak_env() -> None:
    output = _render_chart()
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    session_secret = _env_entry(deployment_env, "SESSION_SECRET")
    assert "name: news-dashboard-news-dashboard-auth" in session_secret
    assert "key: SESSION_SECRET" in session_secret

    assert _env_entry(deployment_env, "KEYCLOAK_AUTH_ENABLED") == (
        '- name: KEYCLOAK_AUTH_ENABLED\n  value: "1"'
    )
    assert "KEYCLOAK_CLIENT_ID" in deployment_env
    assert "BOOTSTRAP_ADMIN_USERNAME" not in deployment_env
    assert "BOOTSTRAP_ADMIN_PASSWORD" not in deployment_env

    secret_manifest = _manifest_for_kind(output, "Secret")
    assert "KEYCLOAK_CLIENT_SECRET" in secret_manifest
    assert "KEYCLOAK_ADMIN_CLIENT_SECRET" in secret_manifest


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_local_password_auth_mode_omits_keycloak_env() -> None:
    output = _render_chart(
        "app.auth.keycloak.enabled=false",
        "app.auth.bootstrapAdmin.existingSecret=news-dashboard-bootstrap-admin",
    )
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    session_secret = _env_entry(deployment_env, "SESSION_SECRET")
    assert "key: SESSION_SECRET" in session_secret

    assert "KEYCLOAK_AUTH_ENABLED" not in deployment_env
    assert "KEYCLOAK_CLIENT_ID" not in deployment_env
    assert "KEYCLOAK_SERVER_URL" not in deployment_env

    bootstrap_username = _env_entry(deployment_env, "BOOTSTRAP_ADMIN_USERNAME")
    assert 'name: "news-dashboard-bootstrap-admin"' in bootstrap_username
    assert 'key: "BOOTSTRAP_ADMIN_USERNAME"' in bootstrap_username
    bootstrap_password = _env_entry(deployment_env, "BOOTSTRAP_ADMIN_PASSWORD")
    assert 'name: "news-dashboard-bootstrap-admin"' in bootstrap_password
    assert 'key: "BOOTSTRAP_ADMIN_PASSWORD"' in bootstrap_password

    secret_manifest = _manifest_for_kind(output, "Secret")
    assert "KEYCLOAK_CLIENT_SECRET" not in secret_manifest
    assert "KEYCLOAK_ADMIN_CLIENT_SECRET" not in secret_manifest


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_local_password_auth_mode_without_bootstrap_secret_omits_env() -> None:
    output = _render_chart("app.auth.keycloak.enabled=false")
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    assert "KEYCLOAK_AUTH_ENABLED" not in deployment_env
    assert "BOOTSTRAP_ADMIN_USERNAME" not in deployment_env
    assert "BOOTSTRAP_ADMIN_PASSWORD" not in deployment_env


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_fails_without_session_secret_in_local_password_mode() -> None:
    assert HELM_BIN is not None
    res = subprocess.run(  # noqa: S603
        [
            HELM_BIN,
            "template",
            "news-dashboard",
            str(CHART_DIR),
            "--set-string",
            "postgresql.password=dummy-postgres-password-for-render-only",
            "--set",
            "app.auth.keycloak.enabled=false",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    assert "app.auth.sessionSecret is required" in res.stderr


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_app_mounts_writable_data_dir() -> None:
    output = _render_chart()
    deployment = _manifest_for_kind(output, "Deployment")
    deployment_env = _env_block(deployment)

    assert _env_entry(deployment_env, "DATA_DIR") == '- name: DATA_DIR\n  value: "/data"'
    assert "readOnlyRootFilesystem: true" in deployment
    assert "name: app-data" in deployment
    assert 'mountPath: "/data"' in deployment
    assert "emptyDir: {}" in deployment


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_app_data_dir_can_use_persistent_volume_claim() -> None:
    output = _render_chart(
        "app.data.dir=/var/lib/news-dashboard",
        "app.data.persistence.enabled=true",
        "app.data.persistence.size=5Gi",
        "app.data.persistence.storageClassName=fast-storage",
    )
    deployment = _manifest_for_kind(output, "Deployment")
    pvc = _manifest_for_kind(output, "PersistentVolumeClaim")
    deployment_env = _env_block(deployment)

    assert _env_entry(deployment_env, "DATA_DIR") == (
        '- name: DATA_DIR\n  value: "/var/lib/news-dashboard"'
    )
    assert 'mountPath: "/var/lib/news-dashboard"' in deployment
    assert 'claimName: "news-dashboard-news-dashboard-data"' in deployment
    assert "name: news-dashboard-news-dashboard-data" in pvc
    assert "storage: 5Gi" in pvc
    assert 'storageClassName: "fast-storage"' in pvc


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_app_data_dir_can_use_existing_claim() -> None:
    output = _render_chart(
        "app.data.persistence.enabled=true",
        "app.data.persistence.existingClaim=audio-cache",
    )
    deployment = _manifest_for_kind(output, "Deployment")

    assert 'claimName: "audio-cache"' in deployment
    assert "name: news-dashboard-news-dashboard-data" not in output


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
def test_helm_template_newsletter_env_defaults_off() -> None:
    output = _render_chart()
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    assert "NEWSLETTER_IMAP_HOST" not in deployment_env
    assert "NEWSLETTER_IMAP_PORT" not in deployment_env
    assert "NEWSLETTER_IMAP_USERNAME" not in deployment_env
    assert "NEWSLETTER_IMAP_PASSWORD" not in deployment_env
    assert "NEWSLETTER_IMAP_FOLDER" not in deployment_env
    assert "NEWSLETTER_POLL_MINUTES" not in deployment_env
    assert "NEWSLETTER_MAX_MESSAGE_BYTES" not in deployment_env


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_newsletter_env_uses_existing_secret() -> None:
    output = _render_chart(
        "app.newsletter.imapHost=imap.example.test",
        "app.newsletter.imapPort=1993",
        "app.newsletter.imapFolder=Newsletters",
        "app.newsletter.pollMinutes=7",
        "app.newsletter.maxMessageBytes=1048576",
        "app.newsletter.existingSecret=newsletter-credentials",
        "app.newsletter.usernameKey=CUSTOM_IMAP_USERNAME",
        "app.newsletter.passwordKey=CUSTOM_IMAP_PASSWORD",
    )
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    assert _env_entry(deployment_env, "NEWSLETTER_IMAP_HOST") == (
        '- name: NEWSLETTER_IMAP_HOST\n  value: "imap.example.test"'
    )
    assert _env_entry(deployment_env, "NEWSLETTER_IMAP_PORT") == (
        '- name: NEWSLETTER_IMAP_PORT\n  value: "1993"'
    )
    assert _env_entry(deployment_env, "NEWSLETTER_IMAP_FOLDER") == (
        '- name: NEWSLETTER_IMAP_FOLDER\n  value: "Newsletters"'
    )
    assert _env_entry(deployment_env, "NEWSLETTER_POLL_MINUTES") == (
        '- name: NEWSLETTER_POLL_MINUTES\n  value: "7"'
    )
    assert _env_entry(deployment_env, "NEWSLETTER_MAX_MESSAGE_BYTES") == (
        '- name: NEWSLETTER_MAX_MESSAGE_BYTES\n  value: "1048576"'
    )
    username = _env_entry(deployment_env, "NEWSLETTER_IMAP_USERNAME")
    assert 'name: "newsletter-credentials"' in username
    assert 'key: "CUSTOM_IMAP_USERNAME"' in username
    password = _env_entry(deployment_env, "NEWSLETTER_IMAP_PASSWORD")
    assert 'name: "newsletter-credentials"' in password
    assert 'key: "CUSTOM_IMAP_PASSWORD"' in password


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_app_config_defaults_off() -> None:
    output = _render_chart()
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    assert "METRICS_ENABLED" not in deployment_env
    assert "ENABLE_API_DOCS" not in deployment_env
    assert "ANALYTICS_RETENTION_DAYS" not in deployment_env
    assert "CORS_ORIGINS" not in deployment_env


@pytest.mark.skipif(HELM_BIN is None, reason="helm binary not found on path")
def test_helm_template_app_config_optional_runtime_env() -> None:
    output = _render_chart(
        "app.config.metricsEnabled=true",
        "app.config.enableApiDocs=true",
        "app.config.analyticsRetentionDays=90",
        "app.config.corsOrigins=https://example.com",
    )
    deployment_env = _env_block(_manifest_for_kind(output, "Deployment"))

    assert _env_entry(deployment_env, "METRICS_ENABLED") == (
        '- name: METRICS_ENABLED\n  value: "true"'
    )
    assert _env_entry(deployment_env, "ENABLE_API_DOCS") == (
        '- name: ENABLE_API_DOCS\n  value: "true"'
    )
    assert _env_entry(deployment_env, "ANALYTICS_RETENTION_DAYS") == (
        '- name: ANALYTICS_RETENTION_DAYS\n  value: "90"'
    )
    assert _env_entry(deployment_env, "CORS_ORIGINS") == (
        '- name: CORS_ORIGINS\n  value: "https://example.com"'
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
