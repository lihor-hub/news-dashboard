from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_HELPER = ROOT / "scripts" / "deploy-local-k8s.sh"


def test_deploy_creates_namespace_before_secrets() -> None:
    workflow = CI_WORKFLOW.read_text()

    namespace_command = (
        "kubectl create namespace news-dashboard --dry-run=client -o yaml | kubectl apply -f -"
    )
    pull_command = "kubectl -n news-dashboard create secret docker-registry ghcr-pull-secret"
    ai_command = "kubectl -n news-dashboard create secret generic news-dashboard-ai"

    namespace_index = workflow.index(namespace_command)
    pull_index = workflow.index(pull_command)
    ai_index = workflow.index(ai_command)

    assert namespace_index < pull_index  # noqa: S101
    assert namespace_index < ai_index  # noqa: S101


def test_deploy_supports_public_ghcr_without_token() -> None:
    workflow = CI_WORKFLOW.read_text()
    public_image_message = (
        'echo "GHCR_TOKEN is empty; treating ${IMG}:${SHA} as a public GHCR image."'
    )
    empty_image_pull_arg = "pull_secret_helm_args=(--set-string image.pullSecretName=)"

    assert 'if [ -n "$GHCR_TOKEN" ]; then' in workflow  # noqa: S101
    assert public_image_message in workflow  # noqa: S101
    assert empty_image_pull_arg in workflow  # noqa: S101
    assert '"${pull_secret_helm_args[@]}"' in workflow  # noqa: S101


def test_deploy_keeps_private_ghcr_pull_secret_when_token_is_set() -> None:
    workflow = CI_WORKFLOW.read_text()

    token_branch_index = workflow.index('if [ -n "$GHCR_TOKEN" ]; then')
    docker_login_index = workflow.index(
        'echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_ACTOR" --password-stdin'
    )
    secret_index = workflow.index(
        "kubectl -n news-dashboard create secret docker-registry ghcr-pull-secret"
    )
    helm_arg_index = workflow.index(
        "pull_secret_helm_args=(--set-string image.pullSecretName=ghcr-pull-secret)"
    )
    no_token_index = workflow.index("else", token_branch_index)

    assert token_branch_index < docker_login_index < no_token_index  # noqa: S101
    assert token_branch_index < secret_index < no_token_index  # noqa: S101
    assert token_branch_index < helm_arg_index < no_token_index  # noqa: S101


def test_production_deploy_uses_cluster_ip_and_ingress() -> None:
    workflow = CI_WORKFLOW.read_text()
    helper = DEPLOY_HELPER.read_text()

    for source in (workflow, helper):
        assert "service.type=NodePort" not in source  # noqa: S101
        assert "service.nodePort=30088" not in source  # noqa: S101
        assert "values-production.yaml" in source  # noqa: S101


def test_public_smoke_check_uses_https_hostname() -> None:
    workflow = CI_WORKFLOW.read_text()
    helper = DEPLOY_HELPER.read_text()

    assert "http://localhost:30088" not in workflow  # noqa: S101
    assert "https://news.lihor.ro/api/health" in workflow  # noqa: S101
    assert "https://news.lihor.ro/api/health" in helper  # noqa: S101


def test_production_deploy_does_not_inherit_host_inventory() -> None:
    workflow = CI_WORKFLOW.read_text()
    helper = DEPLOY_HELPER.read_text()

    assert "192.168." not in workflow  # noqa: S101
    assert "ioachim-minipc" not in helper  # noqa: S101
    assert (  # noqa: S101
        "postgres_helm_args=(--set-string postgresql.persistence.hostPath=)" in workflow
    )
    assert (  # noqa: S101
        'POSTGRES_HELM_ARGS=(--set-string "postgresql.persistence.hostPath=")' in helper
    )


def test_mini_pc_deploy_requires_runtime_storage_path() -> None:
    workflow = CI_WORKFLOW.read_text()
    helper = DEPLOY_HELPER.read_text()

    assert 'if [ -z "$POSTGRES_HOST_PATH" ]; then' in workflow  # noqa: S101
    assert 'if [[ -z "${POSTGRES_HOST_PATH:-}" ]]; then' in helper  # noqa: S101
